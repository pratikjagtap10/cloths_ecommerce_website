"""
python manage.py run_event_consumer

Long-running worker (the "core_worker" container). Subscribes to the Redis
events channel and runs the matching handler for each message.
"""
import logging
import time

import redis
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections

from events.bus import get_redis
from events.handlers import dispatch

logger = logging.getLogger("events.consumer")


class Command(BaseCommand):
    help = "Listen for events from other microservices (Redis Pub/Sub)."

    def handle(self, *args, **options):
        channel = settings.EVENTS_CHANNEL
        while True:  # reconnect forever if Redis restarts
            try:
                pubsub = get_redis().pubsub(ignore_subscribe_messages=True)
                pubsub.subscribe(channel)
                logger.info("Listening for events on Redis channel '%s'", channel)
                for message in pubsub.listen():
                    if message.get("type") != "message":
                        continue
                    try:
                        dispatch(message["data"])
                    except Exception:  # noqa: BLE001 - one bad event must not stop the worker
                        logger.exception("Failed to handle event %r", message["data"])
                    finally:
                        close_old_connections()
            except redis.ConnectionError:
                logger.warning("Redis unavailable, retrying in 3 seconds...")
                time.sleep(3)
