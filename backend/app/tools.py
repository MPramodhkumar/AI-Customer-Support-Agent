import re
import os
import random
from datetime import date, timedelta

from .models import KBArticle, Order, Refund, Ticket


class ToolError(Exception):
    """An expected failure (not found, not allowed...). The message is safe to show the customer."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message

class TransientToolError(Exception):
    """A temporary failure (service down, timeout). Worth retrying."""


def maybe_simulate_failure():
    """For demos: set SIMULATE_FAILURE_RATE=0.5 to make half of all tool calls fail."""
    rate = float(os.getenv("SIMULATE_FAILURE_RATE", "0"))
    if rate and random.random() < rate:
        raise TransientToolError("Simulated upstream failure")


def _get_own_order(db, customer_id, order_id):
    """Fetch an order, but only if it belongs to this customer."""
    order = db.get(Order, order_id)
    if order is None or order.customer_id != customer_id:
        # Same message for "doesn't exist" and "not yours" so we never leak other people's orders
        raise ToolError("order_not_found", f"No order #{order_id} found on your account.")
    return order


def get_order_status(db, customer_id, order_id):
    order = _get_own_order(db, customer_id, order_id)
    return {
        "order_id": order.id,
        "item": order.item,
        "status": order.status,
        "expected_delivery": order.eta.isoformat() if order.eta else None,
    }


def cancel_order(db, customer_id, order_id):
    order = _get_own_order(db, customer_id, order_id)

    if order.status == "cancelled":
        raise ToolError("already_cancelled", f"Order #{order.id} is already cancelled.")
    if order.status not in ("processing", "confirmed"):
        raise ToolError("not_cancellable", f"Order #{order.id} is {order.status} and can no longer be cancelled.")

    order.status = "cancelled"
    refund = Refund(order_id=order.id, amount=order.total, status="initiated",
                    expected_date=date.today() + timedelta(days=7))
    db.add(refund)
    db.commit()
    return {
        "order_id": order.id,
        "status": "cancelled",
        "refund_amount": refund.amount,
        "refund_expected_by": refund.expected_date.isoformat(),
    }


def check_refund_status(db, customer_id, order_id):
    order = _get_own_order(db, customer_id, order_id)
    refund = db.query(Refund).filter(Refund.order_id == order.id).first()
    if refund is None:
        raise ToolError("no_refund", f"There is no refund on record for order #{order.id}.")
    return {
        "order_id": order.id,
        "refund_amount": refund.amount,
        "refund_status": refund.status,
        "refund_expected_by": refund.expected_date.isoformat() if refund.expected_date else None,
    }


def create_support_ticket(db, customer_id, subject, description, priority="medium"):
    if priority not in ("low", "medium", "high"):
        priority = "medium"
    ticket = Ticket(customer_id=customer_id, subject=subject, description=description, priority=priority)
    db.add(ticket)
    db.commit()
    return {"ticket_id": ticket.id, "status": ticket.status, "priority": ticket.priority}


def search_knowledge_base(db, customer_id, query):
    words = [w for w in re.findall(r"[a-z]+", query.lower()) if len(w) > 2]
    results = []
    for article in db.query(KBArticle).all():
        text = (article.title + " " + article.content).lower()
        score = sum(1 for w in words if w in text)
        if score:
            results.append((score, article))
    if not results:
        raise ToolError("no_results", "No matching articles found.")
    results.sort(key=lambda r: -r[0])
    return {"articles": [{"title": a.title, "content": a.content} for _, a in results[:2]]}


# Registry: tool name -> function. The agent will use this in Step 5.
TOOLS = {
    "get_order_status": get_order_status,
    "cancel_order": cancel_order,
    "check_refund_status": check_refund_status,
    "create_support_ticket": create_support_ticket,
    "search_knowledge_base": search_knowledge_base,
}