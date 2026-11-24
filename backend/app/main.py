from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .agent import run_agent
from .database import Base, SessionLocal, engine, get_db
from .models import Customer
from .seed import seed

from .agent import RateLimitExceeded, run_agent

app = FastAPI(title="Checkr")

api_key_header = APIKeyHeader(name="X-API-Key")


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed(db)
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


@app.post("/chat")
def chat(req: ChatRequest, customer: Customer = Depends(current_customer), db: Session = Depends(get_db)):
    try:
        return run_agent(db, customer.id, req.session_id, req.message)
    except RateLimitExceeded as e:
        raise HTTPException(status_code=429, detail=str(e))