import asyncio
import os
import time

# Configure BEFORE the app is imported
os.environ["ENABLE_EVENT_LISTENER"] = "false"
os.environ["JWT_SECRET"] = "test-secret-that-is-long-enough-for-hs256"

import jwt  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app import models  # noqa: E402,F401
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.routers import payments  # noqa: E402
from app.services.core_client import CoreServiceError, get_core_client  # noqa: E402

VARIANTS = {
    1: {"id": 1, "product_id": 1, "product_name": "Basic Tee", "product_slug": "basic-tee", "size": "M",
        "color": "Black", "color_hex": "#000000", "sku": "T-1", "price": 500, "stock": 3, "is_active": True},
    2: {"id": 2, "product_id": 2, "product_name": "Linen Dress", "product_slug": "linen-dress", "size": "S",
        "color": "Beige", "color_hex": "#d6c7a1", "sku": "D-1", "price": 2500, "stock": 1, "is_active": True},
}


class FakeCore:
    """Stands in for the Django core service."""

    def __init__(self):
        self.down = False
        self.orders = []          # every create_order payload received
        self.by_key = {}          # idempotency_key -> order (like the real core service)
        self.next_id = 1003

    async def get_variant(self, variant_id):
        if self.down:
            raise CoreServiceError(503, "Catalog service is unavailable. Please try again shortly.")
        if variant_id not in VARIANTS:
            raise CoreServiceError(404, "Product variant not found.")
        return VARIANTS[variant_id]

    async def create_order(self, payload):
        if self.down:
            raise CoreServiceError(503, "Catalog service is unavailable. Please try again shortly.")
        self.orders.append(payload)
        key = payload.get("idempotency_key")
        if key and key in self.by_key:
            return self.by_key[key]
        subtotal = sum(VARIANTS[i["variant_id"]]["price"] * i["quantity"] for i in payload["items"])
        order = {"id": self.next_id, "user_id": payload["user_id"], "status": "PENDING", "subtotal": subtotal,
                 "shipping_fee": 0, "total": subtotal, "address": payload["address"], "items": []}
        self.next_id += 1
        if key:
            self.by_key[key] = order
        return order


@pytest.fixture
def fake_core():
    return FakeCore()


@pytest.fixture
def published(monkeypatch):
    events = []

    async def fake_publish(event_type, data):
        events.append((event_type, data))
        return True

    monkeypatch.setattr(payments, "publish", fake_publish)
    return events


@pytest.fixture
def client(tmp_path, fake_core):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}", poolclass=NullPool)

    async def create_tables():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(create_tables())
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_core_client] = lambda: fake_core
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def make_token(user_id=1, token_type="access", expires_in=300):
    payload = {"user_id": str(user_id), "token_type": token_type, "email": "jane@example.com",
               "exp": int(time.time()) + expires_in}
    return jwt.encode(payload, "test-secret-that-is-long-enough-for-hs256", algorithm="HS256")


@pytest.fixture
def auth():
    return {"Authorization": f"Bearer {make_token()}"}


ADDRESS = {"full_name": "Jane Doe", "phone": "9876543210", "line1": "12 MG Road",
           "city": "Pune", "state": "Maharashtra", "postal_code": "411001"}
