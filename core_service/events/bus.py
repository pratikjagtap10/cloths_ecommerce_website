"""
Asynchronous communication between microservices using Redis Pub/Sub.

Message format on the channel (default "events"):
    {"type": "payment.succeeded", "data": {"order_id": 1003, ...}}

Pub/Sub is fire-and-forget: if no subscriber is running when a message is sent,
the message is lost. That keeps this demo simple. Production systems usually use
Redis Streams, RabbitMQ or Kafka (messages are stored until processed).
"""
import json
import logging

import redis
from django.conf import settings

logger = logging.getLogger(__name__)


def get_redis() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


def publish(event_type: str, data: dict) -> bool:
    message = json.dumps({"type": event_type, "data": data})
    try:
        receivers = get_redis().publish(settings.EVENTS_CHANNEL, message)
        logger.info("Published %s to %s (%s receiver(s))", event_type, settings.EVENTS_CHANNEL, receivers)
        return True
    except redis.RedisError:
        logger.exception("Could not publish %s", event_type)
        return False
