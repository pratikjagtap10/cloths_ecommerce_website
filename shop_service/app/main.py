"""
SHOP SERVICE (FastAPI): cart, checkout and payments.

Interactive API docs: http://localhost/api/shop/docs  (or :8001/api/shop/docs)
"""
import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import engine
from .errors import register_exception_handlers
from .routers import cart, checkout, health, payments
from .services.events import close_redis, listen_for_events

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Startup: subscribe to events from other services in the background
    listener = asyncio.create_task(listen_for_events()) if settings.enable_event_listener else None
    yield
    # Shutdown: stop the listener and close connections cleanly
    if listener:
        listener.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await listener
    await close_redis()
    await engine.dispose()


app = FastAPI(
    title="Threads Shop Service",
    description="Cart, checkout and (mock) payments for the Threads clothing store.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/shop/docs",
    openapi_url="/api/shop/openapi.json",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
register_exception_handlers(app)

app.include_router(health.router)
app.include_router(cart.router)
app.include_router(checkout.router)
app.include_router(payments.router)
