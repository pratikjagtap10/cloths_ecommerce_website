"""
Idempotency-Key support for checkout (same idea as Stripe's API).

The client generates a unique key per checkout attempt and sends it in the
`Idempotency-Key` header. Retries of the SAME checkout reuse the key:

  first request         -> key claimed (IN_PROGRESS) -> order + payment created -> COMPLETED
  repeat (same key)     -> the stored order + CURRENT payment are returned, nothing new created
  repeat while running  -> 409 "already being processed" (client waits and retries)
  same key, other body  -> 422 (a key must never be reused for a different request)
  request failed        -> key released, so the client can retry with the same key

Keys are scoped per user, so two users can't collide or read each other's results.
"""
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import IdempotencyRecord

KEY_PATTERN = re.compile(r"^[A-Za-z0-9_\-]{8,100}$")
# If a request crashed mid-way, its IN_PROGRESS claim is considered abandoned after this
STALE_AFTER = timedelta(seconds=60)


class IdempotencyInProgress(HTTPException):
    def __init__(self):
        # Retry-After tells the client it's safe to retry the same request shortly
        super().__init__(
            409, "This checkout is already being processed. Please wait a moment.", headers={"Retry-After": "2"}
        )


def validate_key(key: str) -> str:
    if not KEY_PATTERN.fullmatch(key):
        raise HTTPException(400, "Idempotency-Key must be 8-100 letters, digits, '_' or '-'.")
    return key


def request_hash(body: dict) -> str:
    """Stable fingerprint of the request body (key order doesn't matter)."""
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


async def claim(db: AsyncSession, user_id: int, key: str, body_hash: str) -> IdempotencyRecord:
    """Claim the key for this request, or explain why we can't.

    Returns the record:
      * status IN_PROGRESS -> this request owns the key and must run the checkout
      * status COMPLETED   -> a previous identical request finished; replay its result
    Raises 422 (different body) or 409 (identical request still running).
    """
    record = IdempotencyRecord(user_id=user_id, key=key, request_hash=body_hash, status="IN_PROGRESS")
    db.add(record)
    try:
        await db.commit()  # the UNIQUE(user_id, key) constraint decides who wins a race
        return record
    except IntegrityError:
        await db.rollback()

    existing = await db.scalar(
        select(IdempotencyRecord).where(IdempotencyRecord.user_id == user_id, IdempotencyRecord.key == key)
    )
    if existing is None:  # released between our insert and select: just try again
        return await claim(db, user_id, key, body_hash)
    if existing.request_hash != body_hash:
        raise HTTPException(422, "This Idempotency-Key was already used for a different checkout request.")
    if existing.status == "COMPLETED":
        return existing

    created = _as_utc(existing.created_at)
    if created and datetime.now(timezone.utc) - created > STALE_AFTER:
        # The original request died before finishing: take over its claim
        existing.created_at = datetime.now(timezone.utc)
        await db.commit()
        return existing
    raise IdempotencyInProgress()


async def release(db: AsyncSession, user_id: int, key: str) -> None:
    """Forget a failed attempt so the same key can be retried."""
    await db.rollback()
    await db.execute(
        delete(IdempotencyRecord).where(
            IdempotencyRecord.user_id == user_id,
            IdempotencyRecord.key == key,
            IdempotencyRecord.status == "IN_PROGRESS",
        )
    )
    await db.commit()
