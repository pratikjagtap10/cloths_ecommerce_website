"""
ASYNCHRONOUS microservice communication via Redis Pub/Sub.

  publish("payment.succeeded", {...})  -> the Django worker marks the order PAID
  listen_for_events()                  -> reacts to "order.shipped" from Django
"""
import asyncio
import json
import logging

import redis.asyncio as aioredis
from redis.exceptions import RedisError

from ..config import settings
from .notifications import notify_order_shipped

logger = logging.getLogger(__name__)

_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


async def publish(event_type: str, data: dict) -> bool:
    message = json.dumps({"type": event_type, "data": data})
    try:
        receivers = await get_redis().publish(settings.events_channel, message)
        logger.info("Published %s (%s receiver(s)): %s", event_type, receivers, data)
        return True
    except RedisError:
        # Simplification for the demo: in production use the "transactional outbox"
        # pattern so an event can never be lost.
        logger.exception("Could not publish %s", event_type)
        return False


async def _handle(raw: str) -> None:
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Ignoring malformed event: %r", raw)
        return
    if event.get("type") == "order.shipped":
        await notify_order_shipped(event.get("data") or {})


async def listen_for_events() -> None:
    """Background task started in main.py (lifespan). Reconnects if Redis restarts."""
    while True:
        try:
            pubsub = get_redis().pubsub(ignore_subscribe_messages=True)
            await pubsub.subscribe(settings.events_channel)
            logger.info("Listening for events on Redis channel '%s'", settings.events_channel)
            async for message in pubsub.listen():
                if message.get("type") == "message":
                    try:
                        await _handle(message["data"])
                    except Exception:  # noqa: BLE001
                        logger.exception("Failed to handle event")
        except asyncio.CancelledError:
            raise
        except (RedisError, OSError) as exc:
            logger.warning("Redis unavailable (%s), retrying in 3 seconds...", exc)
            await asyncio.sleep(3)
