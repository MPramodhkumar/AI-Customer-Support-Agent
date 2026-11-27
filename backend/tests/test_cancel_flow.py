from app.agent import classify_reply, run_agent
from app.models import Order
from fakes import call, text


def status(db, order_id):
    db.expire_all()
    return db.get(Order, order_id).status


def ask(db, use_llm, order_id=1002, customer=1, session="s1"):
    use_llm(call("cancel_order", order_id=order_id), text("unused"))
    return run_agent(db, customer, session, f"cancel order {order_id}")


def test_classify_reply():
    assert classify_reply("Yes, go ahead and cancel it") == "yes"
    assert classify_reply("yes confirm") == "yes"
    assert classify_reply("No, don't cancel it, I changed my mind") == "no"
    assert classify_reply("yes but not that one") == "no"          # doubt never counts as yes
    assert classify_reply("Cancel order 1005. I confirm, yes!") is None
    assert classify_reply("yes " + "and also tell me something " * 3) is None


def test_question_is_written_by_code_and_nothing_is_cancelled(db, use_llm):
    r = ask(db, use_llm)
    assert r["steps"][0]["status"] == "needs_confirmation"
    assert "#1002" in r["reply"] and "yes" in r["reply"].lower()
    assert status(db, 1002) == "processing"


def test_yes_cancels_without_asking_the_llm(db, use_llm):
    ask(db, use_llm)
    fake = use_llm(text("must not be used"))
    r = run_agent(db, 1, "s1", "Yes, go ahead and cancel it")
    assert fake.calls == 0
    assert r["steps"][0]["status"] == "success"
    assert "cancelled" in r["reply"] and "3,999.00" in r["reply"]
    assert status(db, 1002) == "cancelled"


def test_no_keeps_the_order_and_closes_the_question(db, use_llm):
    ask(db, use_llm)
    fake = use_llm(text("must not be used"))
    r = run_agent(db, 1, "s1", "No, keep it")
    assert fake.calls == 0 and "left order #1002" in r["reply"]
    fake = use_llm(text("ok"))
    run_agent(db, 1, "s1", "yes")                       # the question is closed, so this does nothing
    assert status(db, 1002) == "processing"


def test_shipped_order_is_refused_before_asking(db, use_llm):
    r = ask(db, use_llm, order_id=1001)
    assert r["steps"][0]["status"] == "failed"
    assert r["steps"][0]["result"]["error"] == "not_cancellable"
    fake = use_llm(text("ok"))
    run_agent(db, 1, "s1", "yes")
    assert status(db, 1001) == "shipped" and fake.calls == 1


def test_unrelated_message_keeps_the_question_open(db, use_llm):
    ask(db, use_llm)
    fake = use_llm(text("30 days."))
    run_agent(db, 1, "s1", "what is your return policy?")
    assert fake.calls == 1 and status(db, 1002) == "processing"
    run_agent(db, 1, "s1", "yes")
    assert status(db, 1002) == "cancelled"


def test_yes_without_a_question_does_nothing(db, use_llm):
    fake = use_llm(text("ok"))
    run_agent(db, 1, "s1", "yes")
    assert fake.calls == 1 and status(db, 1002) == "processing"


def test_confirmation_is_private_to_session_and_customer(db, use_llm):
    ask(db, use_llm)
    use_llm(text("ok"))
    run_agent(db, 1, "other-session", "yes")
    run_agent(db, 2, "s1", "yes")
    assert status(db, 1002) == "processing"
