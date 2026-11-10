from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import IdempotencyRecord, Payment
from ..schemas import CheckoutIn, CheckoutOut, PaymentOut
from ..security import CurrentUser, get_current_user
from ..services import idempotency
from ..services.core_client import CoreClient, get_core_client
from .cart import get_cart_for

router = APIRouter(prefix="/api/shop", tags=["checkout"])


@router.post("/checkout/", response_model=CheckoutOut, status_code=status.HTTP_201_CREATED, summary="Place an order")
async def checkout(
    body: CheckoutIn,
    response: Response,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    core: CoreClient = Depends(get_core_client),
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        description="Unique per checkout attempt. Retries with the same key return the same order and payment.",
    ),
):
    """
    1. Read the user's cart (this service's database)
    2. Ask the core service to create the order. It re-checks stock and prices
       inside a database transaction and returns the order with status PENDING.
    3. Create a PENDING payment here and return both to the frontend.

    Send an `Idempotency-Key` header to make retries safe (slow network, double
    submit, page refresh): the same key never creates a second order or payment.
    """
    if idempotency_key is None:
        return await _place_order(body, user, db, core)

    key = idempotency.validate_key(idempotency_key)
    record = await idempotency.claim(db, user.id, key, idempotency.request_hash(body.model_dump()))

    if record.status == "COMPLETED":
        # Replay: same order, and the payment's CURRENT status (it may be paid by now)
        payment = await db.get(Payment, record.payment_id)
        response.headers["Idempotent-Replayed"] = "true"
        return CheckoutOut(order=record.order_json, payment=PaymentOut.model_validate(payment))

    try:
        # The core service gets its own key, so even a lost response between the
        # two services can't create a duplicate order there
        return await _place_order(body, user, db, core, order_key=f"shop-{user.id}-{key}", record=record)
    except Exception:
        await idempotency.release(db, user.id, key)
        raise


async def _place_order(
    body: CheckoutIn,
    user: CurrentUser,
    db: AsyncSession,
    core: CoreClient,
    order_key: str | None = None,
    record: IdempotencyRecord | None = None,
) -> CheckoutOut:
    cart = await get_cart_for(db, user.id)
    if cart is None or not cart.items:
        raise HTTPException(400, "Your cart is empty.")

    payload = {
        "user_id": user.id,
        "address": body.address.model_dump(),
        "items": [{"variant_id": i.variant_id, "quantity": i.quantity} for i in cart.items],
    }
    if order_key:
        payload["idempotency_key"] = order_key
    order = await core.create_order(payload)

    # If an earlier attempt for this same order already created a payment, reuse it
    payment = await db.scalar(
        select(Payment).where(Payment.order_id == order["id"], Payment.user_id == user.id).order_by(Payment.id)
    )
    if payment is None:
        payment = Payment(order_id=order["id"], user_id=user.id, amount=order["total"], status="PENDING")
        db.add(payment)
        await db.flush()  # assigns payment.id

    if record is not None:
        record.status = "COMPLETED"
        record.order_json = order
        record.payment_id = payment.id

    await db.commit()  # payment + COMPLETED record are saved together
    await db.refresh(payment)
    return CheckoutOut(order=order, payment=PaymentOut.model_validate(payment))
