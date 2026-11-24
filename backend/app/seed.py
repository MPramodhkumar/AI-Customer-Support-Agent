
#it creates sample customers and their orders so you can test your backend APIs without manually entering data.
from datetime import date, timedelta

from .models import Customer, KBArticle, Order, Refund


def seed(db):
    if db.query(Customer).count() > 0:
        return

    today = date.today()

    db.add_all([
        Customer(id=1, name="Aarav Sharma", email="aarav@example.com", api_key="key-aarav"),
        Customer(id=2, name="Priya Nair", email="priya@example.com", api_key="key-priya"),
    ])
    db.add_all([
        Order(id=1001, customer_id=1, item="Wireless Earbuds", total=2499, status="shipped", eta=today + timedelta(days=1)),
        Order(id=1002, customer_id=1, item="Running Shoes", total=3999, status="processing", eta=today + timedelta(days=5)),
        Order(id=1003, customer_id=1, item="Backpack", total=1899, status="cancelled"),
        Order(id=1004, customer_id=2, item="Coffee Maker", total=5499, status="delivered", eta=today - timedelta(days=3)),
    ])
    db.flush()  # make sure orders exist before refunds point to them

    db.add(Refund(order_id=1003, amount=1899, status="processing", expected_date=today + timedelta(days=3)))

    db.add_all([
        KBArticle(title="Return policy",
                  content="Items can be returned within 30 days of delivery if unused and in original packaging."),
        KBArticle(title="Shipping times",
                  content="Standard shipping takes 3-5 business days. Express shipping takes 1-2 business days."),
        KBArticle(title="Order cancellation policy",
                  content="Orders can be cancelled while in processing or confirmed status. Once shipped, they cannot be cancelled."),
        KBArticle(title="Refund timelines",
                  content="Refunds go to the original payment method within 5-7 business days after cancellation or return."),
    ])
    db.commit()