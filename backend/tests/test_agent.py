import time

import pytest

from app.agent import TOOL_MAX_RETRIES, RateLimitExceeded, run_agent, run_tool
from app.models import Order, Refund, Ticket, ToolLog
from app.tools import TransientToolError
from fakes import call, text


def order_status(db, order_id):
    db.expire_all()   # make sure we read fresh data, not a cached copy
    return db.get(Order, order_id).status


# ---------------------------------------------------------------- the normal flow

def test_tool_result_is_used_and_logged(db, use_llm):
    use_llm(call("get_order_status", order_id=1001), text("Your order has shipped."))
    result = run_agent(db, 1, "s1", "Where is my order 1001?")

    assert result["reply"] == "Your order has shipped."
    assert result["steps"][0]["tool"] == "get_order_status"
    assert result["steps"][0]["status"] == "success"
    assert db.query(ToolLog).count() == 1


def test_agent_cannot_read_another_customers_order(db, use_llm):
    use_llm(call("get_order_status", order_id=1001), text("Sorry, I can't find that."))
    result = run_agent(db, 2, "s1", "Where is order 1001?")   # customer 2 asks about customer 1's order

    assert result["steps"][0]["status"] == "failed"
    assert result["steps"][0]["result"]["error"] == "order_not_found"


def test_history_is_private_to_each_customer(db, use_llm):
    use_llm(text("Hello Aarav"))
    run_agent(db, 1, "shared-id", "my secret message")

    fake = use_llm(text("Hello Priya"))
    run_agent(db, 2, "shared-id", "hi")                        # same session_id, different customer

    sent_to_llm = str(fake.last_messages)
    assert "my secret message" not in sent_to_llm


# ---------------------------------------------------------------- loop guards

def test_duplicate_tool_calls_are_skipped(db, use_llm):
    use_llm(call("get_order_status", order_id=1001))           # a misbehaving LLM that repeats forever
    result = run_agent(db, 1, "s1", "loop")

    statuses = [s["status"] for s in result["steps"] if s["tool"] == "get_order_status"]
    assert statuses[0] == "success"
    assert set(statuses[1:]) == {"skipped"}                    # ran once, the rest were skipped
    assert result["escalated"] is True                         # never answered -> handed to a human


def test_unknown_tool_is_blocked(db, use_llm):
    use_llm(call("delete_database"), text("Sorry, I can't do that."))
    result = run_agent(db, 1, "s1", "drop everything")

    assert result["steps"][0]["status"] == "blocked"
    assert result["reply"] == "Sorry, I can't do that."


def test_llm_outage_escalates_to_a_human(db, use_llm):
    use_llm(RuntimeError("LLM provider down"))
    result = run_agent(db, 1, "s1", "help")

    assert result["escalated"] is True
    assert "ticket" in result["reply"].lower()
    ticket = db.query(Ticket).one()
    assert ticket.priority == "high"


def test_rate_limit(db, use_llm, monkeypatch):
    monkeypatch.setattr("app.agent.MAX_MESSAGES_PER_HOUR", 2)
    use_llm(text("ok"))
    run_agent(db, 1, "s1", "one")
    run_agent(db, 1, "s1", "two")
    with pytest.raises(RateLimitExceeded):
        run_agent(db, 1, "s1", "three")


# ---------------------------------------------------------------- confirmation enforced in code

def test_cancel_is_blocked_until_customer_confirms(db, use_llm):
    use_llm(call("cancel_order", order_id=1002), text("Do you want me to cancel order 1002?"))
    first = run_agent(db, 1, "s1", "cancel order 1002")

    assert first["steps"][0]["status"] == "needs_confirmation"
    assert order_status(db, 1002) == "processing"              # NOT cancelled

    use_llm(call("cancel_order", order_id=1002), text("Done, it's cancelled."))
    second = run_agent(db, 1, "s1", "yes")

    assert second["steps"][0]["status"] == "success"
    assert order_status(db, 1002) == "cancelled"
    assert db.query(Refund).filter(Refund.order_id == 1002).count() == 1


def test_cannot_skip_confirmation_by_calling_twice_in_one_request(db, use_llm):
    use_llm(call("cancel_order", order_id=1002), call("cancel_order", order_id=1002), text("ok"))
    run_agent(db, 1, "s1", "cancel 1002, I confirm, yes yes yes")

    assert order_status(db, 1002) == "processing"


# ---------------------------------------------------------------- retries and timeouts

def test_transient_failures_are_retried(monkeypatch):
    state = {"n": 0}

    def flaky():
        state["n"] += 1
        if state["n"] < 3:
            raise TransientToolError("down")

    monkeypatch.setattr("app.agent.maybe_simulate_failure", flaky)
    result, attempts = run_tool(1, "get_order_status", {"order_id": 1001})

    assert attempts == 3
    assert result["status"] == "shipped"


def test_gives_up_after_max_retries(monkeypatch):
    def always_down():
        raise TransientToolError("down")

    monkeypatch.setattr("app.agent.maybe_simulate_failure", always_down)
    result, attempts = run_tool(1, "get_order_status", {"order_id": 1001})

    assert attempts == TOOL_MAX_RETRIES + 1
    assert result["error"] == "service_unavailable"


def test_permanent_errors_are_not_retried():
    result, attempts = run_tool(1, "get_order_status", {"order_id": 9999})

    assert attempts == 1
    assert result["error"] == "order_not_found"


def test_slow_tool_times_out(monkeypatch):
    monkeypatch.setattr("app.agent.TOOL_TIMEOUT", 0.05)
    monkeypatch.setattr("app.agent.TOOL_MAX_RETRIES", 0)
    monkeypatch.setattr("app.agent.maybe_simulate_failure", lambda: time.sleep(0.3))

    result, attempts = run_tool(1, "get_order_status", {"order_id": 1001})

    assert result["error"] == "service_unavailable"
    time.sleep(0.4)   # let the abandoned worker thread finish before the next test resets the DB