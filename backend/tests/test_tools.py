import pytest

from app.models import Order, Refund, Ticket
from app.tools import (
    ToolError,
    cancel_order,
    check_refund_status,
    create_support_ticket,
    get_order_status,
    search_knowledge_base,
)


def test_get_order_status_own_order(db):
    result = get_order_status(db, 1, 1001)
    assert result["status"] == "shipped"
    assert result["item"] == "Wireless Earbuds"


def test_cannot_see_another_customers_order(db):
    with pytest.raises(ToolError) as e:
        get_order_status(db, 1, 1004)
    assert e.value.code == "order_not_found"


def test_someone_elses_order_looks_the_same_as_a_missing_one(db):
    with pytest.raises(ToolError) as other:
        get_order_status(db, 1, 1004)
    with pytest.raises(ToolError) as missing:
        get_order_status(db, 1, 9999)
    assert other.value.code == missing.value.code   # we never reveal that the order exists


def test_cancel_processing_order_creates_refund(db):
    result = cancel_order(db, 1, 1002)
    assert result["status"] == "cancelled"
    assert db.get(Order, 1002).status == "cancelled"
    assert db.query(Refund).filter(Refund.order_id == 1002).count() == 1


def test_cannot_cancel_shipped_order(db):
    with pytest.raises(ToolError) as e:
        cancel_order(db, 1, 1001)
    assert e.value.code == "not_cancellable"
    assert db.get(Order, 1001).status == "shipped"


def test_cannot_cancel_twice(db):
    cancel_order(db, 1, 1002)
    with pytest.raises(ToolError) as e:
        cancel_order(db, 1, 1002)
    assert e.value.code == "already_cancelled"


def test_cannot_cancel_another_customers_order(db):
    with pytest.raises(ToolError):
        cancel_order(db, 2, 1002)     # 1002 belongs to customer 1
    assert db.get(Order, 1002).status == "processing"


def test_check_refund_status(db):
    result = check_refund_status(db, 1, 1003)
    assert result["refund_status"] == "processing"


def test_no_refund_for_order_without_one(db):
    with pytest.raises(ToolError) as e:
        check_refund_status(db, 1, 1001)
    assert e.value.code == "no_refund"


def test_invalid_ticket_priority_falls_back_to_medium(db):
    result = create_support_ticket(db, 1, "Damaged item", "Box was broken", priority="URGENT!!!")
    assert result["priority"] == "medium"
    assert db.query(Ticket).count() == 1


def test_knowledge_base_finds_article(db):
    result = search_knowledge_base(db, 1, "what is your return policy")
    assert result["articles"][0]["title"] == "Return policy"


def test_knowledge_base_no_match(db):
    with pytest.raises(ToolError) as e:
        search_knowledge_base(db, 1, "xyzzy")
    assert e.value.code == "no_results"