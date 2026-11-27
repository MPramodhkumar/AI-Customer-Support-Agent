import hashlib
import secrets
from datetime import date, timedelta

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from .agent import run_agent
from .database import Base, SessionLocal, engine, get_db
from .models import Customer, Order
from .seed import seed

from .agent import RateLimitExceeded

app = FastAPI(title="Checkr")

api_key_header = APIKeyHeader(name="X-API-Key")


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    # Add the nullable password field for databases created before account signup existed.
    if "password_hash" not in {column["name"] for column in inspect(engine).get_columns("customers")}:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE customers ADD COLUMN password_hash VARCHAR(256)"))
    db = SessionLocal()
    try:
        seed(db)
        if engine.dialect.name == "postgresql":
            for table in ("customers", "orders"):
                db.execute(text(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {table}), 1), true)"
                ))
            db.commit()
    finally:
        db.close()


def current_customer(key: str = Depends(api_key_header), db: Session = Depends(get_db)):
    """Who is calling? Look the customer up by their API key."""
    customer = db.query(Customer).filter(Customer.api_key == key).first()
    if customer is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return customer


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/me")
def me(customer: Customer = Depends(current_customer)):
    return {"id": customer.id, "name": customer.name, "email": customer.email}


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=36)
    message: str = Field(min_length=1, max_length=1000)  # also limits cost per request


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=8, max_length=200)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class OrderRequest(BaseModel):
    item: str = Field(min_length=1, max_length=200)
    price: float = Field(gt=0, le=1_000_000)


def _password_hash(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000).hex()
    return f"{salt}${digest}"


def _valid_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    salt, digest = stored.split("$", 1)
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000).hex()
    return secrets.compare_digest(actual, digest)


def _customer_payload(customer: Customer):
    return {"id": customer.id, "name": customer.name, "email": customer.email}


@app.get("/customers")
def customers(db: Session = Depends(get_db)):
    return [_customer_payload(c) for c in db.query(Customer).order_by(Customer.id).all()]


@app.get("/demo")
def demo_customer(db: Session = Depends(get_db)):
    """Public, isolated demo account for exploring the app without registration."""
    email = "robert.demo@checkr.local"
    customer = db.query(Customer).filter(Customer.email == email).first()
    if customer is None:
        customer = Customer(name="Robert Demo", email=email, api_key=secrets.token_urlsafe(32))
        db.add(customer)
        db.flush()
    if db.query(Order).filter(Order.customer_id == customer.id).count() == 0:
        if db.bind.dialect.name == "postgresql":
            db.execute(text("SELECT pg_advisory_xact_lock(72638104)"))
        first_id = (db.query(Order.id).order_by(Order.id.desc()).first() or (0,))[0] + 1
        db.add_all([
            Order(id=first_id, customer_id=customer.id, item="Wireless Headphones", total=3499,
                  status="confirmed", eta=date.today() + timedelta(days=3)),
            Order(id=first_id + 1, customer_id=customer.id, item="Everyday Backpack", total=2299,
                  status="delivered", eta=date.today() - timedelta(days=2)),
        ])
    db.commit()
    db.refresh(customer)
    return {**_customer_payload(customer), "api_key": customer.api_key, "is_demo": True}


@app.post("/users", status_code=201)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    email = req.email.strip().lower()
    if "@" not in email:
        raise HTTPException(status_code=422, detail="Enter a valid email address")
    if db.query(Customer).filter(Customer.email == email).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    customer = Customer(name=req.name.strip(), email=email, api_key=secrets.token_urlsafe(32),
                        password_hash=_password_hash(req.password))
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return {**_customer_payload(customer), "api_key": customer.api_key}


@app.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.email == req.email.strip().lower()).first()
    if customer is None or not _valid_password(req.password, customer.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return {**_customer_payload(customer), "api_key": customer.api_key}


@app.post("/orders", status_code=201)
def create_order(req: OrderRequest, customer: Customer = Depends(current_customer), db: Session = Depends(get_db)):
    # Serialize ID allocation on PostgreSQL; SQLite uses the same max+1 fallback for local development/tests.
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(72638104)"))
    order_id = (db.query(Order.id).order_by(Order.id.desc()).first() or (0,))[0] + 1
    order = Order(id=order_id, customer_id=customer.id, item=req.item.strip(), total=req.price, status="confirmed")
    db.add(order)
    db.commit()
    db.refresh(order)
    return {"id": order.id, "item": order.item, "price": order.total, "status": order.status}


@app.get("/orders")
def list_orders(customer: Customer = Depends(current_customer), db: Session = Depends(get_db)):
    return [{"id": o.id, "item": o.item, "price": o.total, "status": o.status}
            for o in db.query(Order).filter(Order.customer_id == customer.id).order_by(Order.id.desc()).all()]


@app.post("/orders/{order_id}/deliver")
def mark_order_delivered(order_id: int, customer: Customer = Depends(current_customer), db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id, Order.customer_id == customer.id).with_for_update().first()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found on your account")
    if order.status in ("cancelled", "delivered"):
        raise HTTPException(status_code=409, detail=f"Order is already {order.status}")
    order.status = "delivered"
    db.commit()
    return {"id": order.id, "item": order.item, "price": order.total, "status": order.status}


@app.post("/chat")
def chat(req: ChatRequest, customer: Customer = Depends(current_customer), db: Session = Depends(get_db)):
    try:
        return run_agent(db, customer.id, req.session_id, req.message)
    except RateLimitExceeded as e:
        raise HTTPException(status_code=429, detail=str(e))
