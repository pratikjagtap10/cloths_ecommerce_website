"""Maps incoming event types to the code that handles them."""
import json
import logging

from orders.services import mark_order_paid

logger = logging.getLogger(__name__)


def handle_payment_succeeded(data: dict) -> None:
    """Published by the FastAPI shop service after a successful payment."""
    mark_order_paid(int(data["order_id"]))


HANDLERS = {
    "payment.succeeded": handle_payment_succeeded,
}


def dispatch(raw_message: str) -> None:
    try:
        event = json.loads(raw_message)
    except (TypeError, json.JSONDecodeError):
        logger.warning("Ignoring malformed event: %r", raw_message)
        return

    event_type = event.get("type")
    handler = HANDLERS.get(event_type)
    if handler is None:
        logger.debug("No handler for %s - ignored", event_type)  # e.g. our own order.shipped
        return
    logger.info("Handling %s %s", event_type, event.get("data"))
    handler(event.get("data") or {})
