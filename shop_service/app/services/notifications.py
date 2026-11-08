"""Fake notifications: they only write to the log. Swap in a real email/SMS
provider later without changing the callers."""
import logging

logger = logging.getLogger("notifications")


async def send_order_confirmation(email: str | None, order_id: int, amount: int) -> None:
    logger.info("[mock email] To: %s | Order #%s confirmed | Amount paid: Rs.%s", email or "unknown", order_id, amount)


async def notify_order_shipped(data: dict) -> None:
    logger.info(
        "[mock email] To: %s | Good news! Order #%s has been shipped.",
        data.get("email", "unknown"),
        data.get("order_id"),
    )
