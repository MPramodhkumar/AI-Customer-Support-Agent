import os
import sys
from pathlib import Path

# These must be set BEFORE the app is imported (the app reads them at import time)
os.environ["TOOL_RETRY_BACKOFF"] = "0"        # no waiting between retries in tests
os.environ["SIMULATE_FAILURE_RATE"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

if not os.getenv("DATABASE_URL", "").endswith("_test"):
    pytest.exit("Refusing to run: DATABASE_URL must point to a database whose name ends with _test", returncode=2)

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.seed import seed  # noqa: E402
from fakes import ScriptedLLM  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    """Runs before EVERY test: empty database + demo data, so tests never affect each other."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    seed(db)
    db.close()


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def use_llm(monkeypatch):
    """use_llm(reply1, reply2, ...) swaps the real LLM for a scripted fake."""
    def _use(*replies):
        fake = ScriptedLLM(replies)
        monkeypatch.setattr("app.agent.ask_llm", fake)
        return fake
    return _use