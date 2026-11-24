import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import datetime, timedelta

from .database import SessionLocal
from .llm import SYSTEM_PROMPT, ask_llm
from .models import Message, ToolLog
from .tool_schemas import TOOL_SCHEMAS
from .tools import TOOLS, ToolError, TransientToolError, create_support_ticket, maybe_simulate_failure

log = logging.getLogger("checkr.agent")

MAX_STEPS = 5          # max LLM round-trips per customer message
MAX_TOOL_CALLS = 6     # max tool executions per customer message
TOOL_TIMEOUT = float(os.getenv("TOOL_TIMEOUT", "8"))
TOOL_MAX_RETRIES = int(os.getenv("TOOL_MAX_RETRIES", "2"))
TOOL_RETRY_BACKOFF = float(os.getenv("TOOL_RETRY_BACKOFF", "0.4"))
MAX_MESSAGES_PER_HOUR = int(os.getenv("MAX_MESSAGES_PER_HOUR", "30"))

CONFIRM_REQUIRED = {"cancel_order"}   # tools that need a customer "yes" first

_pool = ThreadPoolExecutor(max_workers=8)


class RateLimitExceeded(Exception):
    pass


def check_rate_limit(db, customer_id):
    since = datetime.utcnow() - timedelta(hours=1)
    count = (
        db.query(Message)
        .filter(Message.customer_id == customer_id, Message.role == "user", Message.created_at >= since)
        .count()
    )
    if count >= MAX_MESSAGES_PER_HOUR:
        raise RateLimitExceeded(f"Message limit reached ({MAX_MESSAGES_PER_HOUR}/hour). Try again later.")


def log_tool(db, session_id, customer_id, name, args, status, result, duration_ms=0, attempts=0):
    db.add(ToolLog(
        session_id=session_id, customer_id=customer_id, tool_name=name, arguments=args,
        result=result, status=status, duration_ms=duration_ms, attempts=attempts,
    ))
    db.commit()


def _worker(customer_id, name, args):
    """Runs in a separate thread with its OWN database session."""
    db = SessionLocal()
    try:
        maybe_simulate_failure()
        return TOOLS[name](db, customer_id, **args)
    finally:
        db.close()


def run_tool(customer_id, name, args):
    """Run a tool with a timeout and retries. Returns (result_dict, attempts)."""
    attempts = 0
    for attempt in range(1, TOOL_MAX_RETRIES + 2):
        attempts = attempt
        try:
            result = _pool.submit(_worker, customer_id, name, args).result(timeout=TOOL_TIMEOUT)
            return result, attempts
        except ToolError as e:       # permanent failure: do NOT retry
            return {"error": e.code, "message": e.message}, attempts
        except TypeError:            # LLM sent wrong arguments
            return {"error": "invalid_arguments", "message": "Invalid tool arguments."}, attempts
        except (TransientToolError, FutureTimeout) as e:
            log.warning("tool %s attempt %d failed: %r", name, attempt, e)
            if attempt <= TOOL_MAX_RETRIES:
                time.sleep(TOOL_RETRY_BACKOFF * attempt)   # wait longer each time
        except Exception:
            log.exception("tool %s crashed", name)
            return {"error": "internal_error", "message": "The tool crashed unexpectedly."}, attempts
    return {"error": "service_unavailable",
            "message": "The service is temporarily unavailable. Please try again shortly."}, attempts


def was_confirmation_requested(db, session_id, customer_id, name, args, before):
    """True if an EARLIER request in this session already asked the customer to confirm this exact action."""
    rows = (
        db.query(ToolLog)
        .filter(
            ToolLog.session_id == session_id,
            ToolLog.customer_id == customer_id,
            ToolLog.tool_name == name,
            ToolLog.status == "needs_confirmation",
            ToolLog.created_at < before,
        )
        .all()
    )
    return any(r.arguments == args for r in rows)


def run_agent(db, customer_id, session_id, user_message):
    request_started = datetime.utcnow()
    check_rate_limit(db, customer_id)

    history = (
        db.query(Message)
        .filter(Message.session_id == session_id, Message.customer_id == customer_id)
        .order_by(Message.id.desc())
        .limit(10)
        .all()
    )
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += [{"role": m.role, "content": m.content} for m in reversed(history)]
    messages.append({"role": "user", "content": user_message})

    steps = []
    seen = set()
    tool_calls_used = 0
    escalated = False
    reply_text = None

    try:
        for _ in range(MAX_STEPS):
            reply = ask_llm(messages, TOOL_SCHEMAS)

            if not reply.tool_calls:
                reply_text = reply.content
                break

            messages.append({
                "role": "assistant",
                "content": reply.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in reply.tool_calls
                ],
            })

            for tc in reply.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                key = f"{name}:{json.dumps(args, sort_keys=True)}"
                duration_ms = 0
                attempts = 0

                if name not in TOOLS:
                    result, status = {"error": "unknown_tool", "message": "That tool does not exist."}, "blocked"
                elif key in seen:
                    result, status = {"error": "duplicate_call",
                                      "message": "Already called with these arguments. Use the earlier result."}, "skipped"
                elif tool_calls_used >= MAX_TOOL_CALLS:
                    result, status = {"error": "limit_reached",
                                      "message": "Tool call limit reached for this request."}, "blocked"
                elif name in CONFIRM_REQUIRED and not was_confirmation_requested(
                        db, session_id, customer_id, name, args, request_started):
                    result = {"error": "confirmation_required",
                              "message": "NOT executed yet. Ask the customer to explicitly confirm this action. "
                                         "Call this tool again only after they say yes."}
                    status = "needs_confirmation"
                else:
                    seen.add(key)
                    tool_calls_used += 1
                    start = time.perf_counter()
                    result, attempts = run_tool(customer_id, name, args)
                    duration_ms = int((time.perf_counter() - start) * 1000)
                    status = "failed" if "error" in result else "success"
                    if status == "success" and name == "create_support_ticket":
                        escalated = True

                log_tool(db, session_id, customer_id, name, args, status, result, duration_ms, attempts)
                steps.append({"tool": name, "arguments": args, "result": result, "status": status,
                              "duration_ms": duration_ms, "attempts": attempts})
                messages.append({"role": "tool", "tool_call_id": tc.id,
                                 "content": json.dumps(result, default=str)})
    except Exception:
        log.exception("Agent loop failed")
        db.rollback()
        reply_text = None

    if not reply_text:
        if not escalated:
            ticket = create_support_ticket(
                db, customer_id,
                subject="Automatic escalation: agent could not resolve request",
                description=f"Customer message: {user_message}",
                priority="high",
            )
            log_tool(db, session_id, customer_id, "create_support_ticket", {"auto": True}, "success", ticket)
            steps.append({"tool": "create_support_ticket", "arguments": {"auto": True},
                          "result": ticket, "status": "success", "duration_ms": 0, "attempts": 1})
            escalated = True
            reply_text = (f"I'm sorry, I couldn't resolve this myself. I've created ticket "
                          f"#{ticket['ticket_id']} and a human agent will contact you.")
        else:
            reply_text = "I've passed this to our human support team and they will follow up with you."

    db.add(Message(session_id=session_id, customer_id=customer_id, role="user", content=user_message))
    db.add(Message(session_id=session_id, customer_id=customer_id, role="assistant", content=reply_text))
    db.commit()

    return {"reply": reply_text, "steps": steps, "escalated": escalated}