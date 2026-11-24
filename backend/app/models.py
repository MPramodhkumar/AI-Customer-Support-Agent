from datetime import datetime

from sqlalchemy import JSON, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text

from .database import Base


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(200), unique=True, nullable=False)
    api_key = Column(String(100), unique=True, nullable=False)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    item = Column(String(200), nullable=False)
    total = Column(Float, nullable=False)
    status = Column(String(30), nullable=False, default="processing")
    eta = Column(Date, nullable=True)

class Refund(Base):
    __tablename__ = "refunds"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(String(30), nullable=False, default="initiated")  # initiated | processing | completed
    expected_date = Column(Date, nullable=True)


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    subject = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    priority = Column(String(10), nullable=False, default="medium")  # low | medium | high
    status = Column(String(20), nullable=False, default="open")      # open | in_progress | resolved
    created_at = Column(DateTime, default=datetime.utcnow)


class KBArticle(Base):
    __tablename__ = "kb_articles"

    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    session_id = Column(String(36), nullable=False, index=True)
    customer_id = Column(Integer, nullable=False)
    role = Column(String(20), nullable=False)  # user | assistant
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow) 

class ToolLog(Base):
    __tablename__ = "tool_logs"

    id = Column(Integer, primary_key=True)
    session_id = Column(String(36), index=True)
    customer_id = Column(Integer, index=True)
    tool_name = Column(String(50), nullable=False)
    arguments = Column(JSON)
    result = Column(JSON)
    status = Column(String(20), nullable=False)  # success | failed | skipped | blocked
    duration_ms = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    attempts = Column(Integer, default=1)