"""Evaluation harness: runs every labelled case through the REAL agent + LLM and computes metrics.

    python -m evaluation.run --sample 10 --sleep 1     # quick trial
    python -m evaluation.run                           # all 100 cases
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

# Safety checks BEFORE importing the app (which connects to the database at import time)
if not os.getenv("DATABASE_URL", "").endswith("_eval"):
    sys.exit("Refusing to run: DATABASE_URL must point to a database whose name ends with _eval")
if float(os.getenv("SIMULATE_FAILURE_RATE") or 0) != 0:
    sys.exit("Set SIMULATE_FAILURE_RATE=0 for evaluation runs (check your .env)")
if not os.getenv("LLM_API_KEY"):
    sys.exit("LLM_API_KEY is empty: the evaluation needs a real LLM")

import app.agent as agent_module  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models import Order, Refund, Ticket  # noqa: E402
from app.seed import seed  # noqa: E402

from .cases import CASES  # noqa: E402

REAL_ASK_LLM = agent_module.ask_llm
RESULTS_FILE = Path(__file__).parent / "results" / "latest.json"
NUMBER = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")


class LLMProbe:
    """Wraps the real LLM call so we can tell 'the agent behaved badly' from 'the LLM API failed'."""

    def __init__(self, real):
        self.real = real
        self.errors = []

    def __call__(self, messages, tools):
        try:
            return self.real(messages, tools)
        except Exception as e:
            self.errors.append(repr(e))
            raise


def reset_db():
    """Empty database + demo data + the extra orders the cases rely on."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed(db)
        today = date.today()
        db.add_all([
            Order(id=1005, customer_id=1, item="Desk Lamp", total=1299, status="confirmed", eta=today + timedelta(days=4)),
            Order(id=1006, customer_id=1, item="Phone Case", total=499, status="delivered", eta=today - timedelta(days=5)),
            Order(id=1007, customer_id=2, item="Yoga Mat", total=1599, status="processing", eta=today + timedelta(days=5)),
            Order(id=1008, customer_id=2, item="Water Bottle", total=799, status="shipped", eta=today + timedelta(days=2)),
            Order(id=1009, customer_id=2, item="Notebook Set", total=399, status="cancelled"),
        ])
        db.flush()
        db.add(Refund(order_id=1009, amount=399, status="completed", expected_date=today - timedelta(days=1)))
        db.commit()
    finally:
        db.close()


def norm(text):
    """Lowercase and unify typographic characters (LLMs love curly apostrophes and en dashes)."""
    return text.lower().replace("’", "'").replace("–", "-").replace("—", "-")


def numbers(text):
    return {f"{float(m.replace(',', '')):g}" for m in NUMBER.findall(text)}


def score(case, turns, orders, ticket_count):
    steps = [s for t in turns for s in t["steps"]]
    used = {s["tool"] for s in steps if s["status"] != "skipped"}
    expected = set(case["expect_tools"])
    reasons = []

    # 1. tool calling
    tools_ok = expected <= used and not any(s["status"] == "blocked" for s in steps)
    if case["strict"] and used - expected:
        tools_ok = False
    if not tools_ok:
        reasons.append(f"tools: expected {sorted(expected)}, used {sorted(used)}"
                       + (" (a blocked call happened)" if any(s["status"] == "blocked" for s in steps) else ""))

    # 2. database state (did the action really happen / not happen?)
    db_checked = bool(case["expect_orders"]) or case["expect_escalation"] is True
    db_ok = True
    for order_id, want in case["expect_orders"].items():
        if orders[order_id] != want:
            db_ok = False
            reasons.append(f"db: order {order_id} is '{orders[order_id]}', expected '{want}'")
    if case["expect_escalation"] is True and ticket_count == 0:
        db_ok = False
        reasons.append("db: no ticket was created")

    # 3. required / forbidden facts in the replies
    last_reply = norm(turns[-1]["reply"])
    all_replies = norm(" ".join(t["reply"] for t in turns))
    facts_ok = True
    for group in case["must_include"]:
        options = [group] if isinstance(group, str) else group
        if not any(norm(o) in last_reply for o in options):
            facts_ok = False
            reasons.append(f"reply missing any of {options}")
    for bad in case["must_not_include"]:
        if norm(bad) in all_replies:
            facts_ok = False
            reasons.append(f"reply contains forbidden text {bad!r}")

    # 4. hallucination: numbers in the reply that appear nowhere in the evidence
    evidence = " ".join(case["turns"]) + " " + json.dumps([[s["arguments"], s["result"]] for s in steps], default=str)
    unsupported = sorted(numbers(all_replies) - numbers(evidence))
    hallucinated = bool(unsupported)
    if hallucinated:
        reasons.append(f"hallucination: numbers not supported by any tool result: {unsupported}")

    # 5. escalation
    escalated = any(t["escalated"] for t in turns)
    expect_esc = case["expect_escalation"]
    esc_ok = expect_esc is None or escalated == expect_esc
    if not esc_ok:
        reasons.append("escalation: a ticket was created but should not have been" if escalated
                       else "escalation: should have created a ticket")

    return {
        "tools_ok": tools_ok, "db_checked": db_checked, "db_ok": db_ok, "facts_ok": facts_ok,
        "hallucinated": hallucinated, "escalated": escalated, "esc_ok": esc_ok,
        "expect_escalation": expect_esc,
        "resolved": tools_ok and db_ok and facts_ok and not hallucinated and esc_ok,
        "reasons": reasons,
        "tools_used": sorted(used),
        "tool_calls": len([s for s in steps if s["status"] != "skipped"]),
    }


def run_case(case):
    reset_db()
    probe = LLMProbe(REAL_ASK_LLM)
    agent_module.ask_llm = probe
    db = SessionLocal()
    turns, orders, tickets, error = [], {}, 0, None
    start = time.perf_counter()
    try:
        for message in case["turns"]:
            turns.append(agent_module.run_agent(db, case["customer"], f"eval-{case['id']}", message))
        db.expire_all()
        orders = {oid: db.get(Order, oid).status for oid in case["expect_orders"]}
        tickets = db.query(Ticket).count()
    except Exception as e:
        error = repr(e)
    finally:
        db.close()
    latency = round(time.perf_counter() - start, 2)

    result = {"id": case["id"], "category": case["category"], "turns": case["turns"], "latency_s": latency,
              "infra_error": error or (probe.errors[0] if probe.errors else None)}
    if result["infra_error"]:
        return result
    result.update(score(case, turns, orders, tickets))
    result["replies"] = [t["reply"] for t in turns]
    return result


def pct(part, whole):
    return round(100 * part / whole, 1) if whole else 0.0


def report(results):
    valid = [r for r in results if not r["infra_error"]]
    infra = [r for r in results if r["infra_error"]]
    action = [r for r in valid if r["db_checked"]]

    metrics = {
        "total_cases": len(results),
        "valid_cases": len(valid),
        "infra_errors": len(infra),
        "resolution_rate": pct(sum(r["resolved"] for r in valid), len(valid)),
        "tool_calling_accuracy": pct(sum(r["tools_ok"] for r in valid), len(valid)),
        "hallucination_rate": pct(sum(r["hallucinated"] for r in valid), len(valid)),
        "human_escalation_rate": pct(sum(r["escalated"] for r in valid), len(valid)),
        "unnecessary_escalations": sum(1 for r in valid if r["escalated"] and r["expect_escalation"] is False),
        "missed_escalations": sum(1 for r in valid if not r["escalated"] and r["expect_escalation"] is True),
        "task_success_rate": pct(sum(r["db_ok"] for r in action), len(action)),
        "action_cases": len(action),
        "avg_latency_s": round(sum(r["latency_s"] for r in valid) / len(valid), 2) if valid else 0,
        "avg_tool_calls": round(sum(r["tool_calls"] for r in valid) / len(valid), 2) if valid else 0,
    }

    by_category = {}
    for r in valid:
        c = by_category.setdefault(r["category"], {"cases": 0, "resolved": 0})
        c["cases"] += 1
        c["resolved"] += int(r["resolved"])
    for c in by_category.values():
        c["resolution_rate"] = pct(c["resolved"], c["cases"])

    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_FILE.write_text(json.dumps({
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "model": os.getenv("LLM_MODEL"),
        "metrics": metrics,
        "by_category": by_category,
        "cases": results,
    }, indent=2, default=str), encoding="utf-8")

    m = metrics
    print("\n================ Checkr evaluation ================")
    print(f"Model: {os.getenv('LLM_MODEL')}")
    print(f"Cases run: {m['total_cases']}  (valid: {m['valid_cases']}, LLM/infra errors excluded: {m['infra_errors']})")
    print(f"Query resolution rate .... {m['resolution_rate']}%")
    print(f"Tool-calling accuracy .... {m['tool_calling_accuracy']}%")
    print(f"Hallucination rate ....... {m['hallucination_rate']}%")
    print(f"Human escalation rate .... {m['human_escalation_rate']}%  "
          f"(unnecessary: {m['unnecessary_escalations']}, missed: {m['missed_escalations']})")
    print(f"Task success rate ........ {m['task_success_rate']}%  (on {m['action_cases']} action cases)")
    print(f"Avg latency .............. {m['avg_latency_s']}s   Avg tool calls: {m['avg_tool_calls']}")
    print("\nBy category:")
    for name, c in sorted(by_category.items()):
        print(f"  {name:15} {c['resolved']:>3}/{c['cases']:<3} resolved  ({c['resolution_rate']}%)")

    failed = [r for r in valid if not r["resolved"]]
    if failed:
        print(f"\nFailed cases ({len(failed)}):")
        for r in failed:
            print(f"  - {r['id']}: {' | '.join(r['reasons'])}")
            print(f"      customer said: {r['turns'][-1]!r}")
            print(f"      agent replied: {r['replies'][-1][:150]!r}")
    if infra:
        print(f"\nExcluded because the LLM/infrastructure failed ({len(infra)}):")
        for r in infra[:5]:
            print(f"  - {r['id']}: {r['infra_error'][:150]}")
    print(f"\nFull results saved to {RESULTS_FILE}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, help="run only N cases, spread across the dataset")
    parser.add_argument("--category", help="run only one category, e.g. cancel")
    parser.add_argument("--sleep", type=float, default=0, help="seconds to wait between cases (free-tier rate limits)")
    args = parser.parse_args()

    cases = [c for c in CASES if not args.category or c["category"] == args.category]
    if args.sample:
        cases = cases[:: max(1, len(cases) // args.sample)][: args.sample]

    print(f"Model: {os.getenv('LLM_MODEL')} | messages/hour limit: {agent_module.MAX_MESSAGES_PER_HOUR} | cases: {len(cases)}")
    results = []
    try:
        for i, case in enumerate(cases, 1):
            r = run_case(case)
            results.append(r)
            label = "ERR " if r["infra_error"] else ("PASS" if r["resolved"] else "FAIL")
            print(f"[{i:3}/{len(cases)}] {label} {r['id']} ({r['latency_s']}s)", flush=True)
            time.sleep(args.sleep)
    except KeyboardInterrupt:
        print("\nInterrupted, reporting what finished so far...")
    finally:
        if results:
            report(results)


if __name__ == "__main__":
    main()