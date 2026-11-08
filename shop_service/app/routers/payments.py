import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Cart, CartItem, Payment
from ..schemas import ConfirmPaymentIn, PaymentOut
from ..security import CurrentUser, get_current_user
from ..services.events import publish
from ..services.notifications import send_order_confirmation

router = APIRouter(prefix="/api/shop/payments", tags=["payments"])


async def _get_own_payment(db: AsyncSession, payment_id: int, user: CurrentUser) -> Payment:
    payment = await db.get(Payment, payment_id)
    if payment is None or payment.user_id != user.id:
        raise HTTPException(404, "Payment not found.")
    return payment


@router.get("/{payment_id}/", response_model=PaymentOut, summary="Get a payment")
async def get_payment(
    payment_id: int, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await _get_own_payment(db, payment_id, user)


@router.post("/{payment_id}/confirm/", response_model=PaymentOut, summary="Confirm a MOCK payment")
async def confirm_payment(
    payment_id: int,
    body: ConfirmPaymentIn,
    background: BackgroundTasks,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Simulates a payment gateway callback.
      success=true  -> payment SUCCESS, cart cleared, "payment.succeeded" event
                       published (the Django worker then marks the order PAID),
                       confirmation email sent in the background
      success=false -> payment FAILED (the user can try again)
    """
    payment = await _get_own_payment(db, payment_id, user)
    if payment.status == "SUCCESS":
        return payment  # idempotent: paying twice does nothing

    if not body.success:
        payment.status = "FAILED"
        await db.commit()
        return payment

    payment.status = "SUCCESS"
    payment.provider_ref = f"MOCK-{uuid.uuid4().hex[:12].upper()}"
    await db.execute(
        delete(CartItem).where(CartItem.cart_id.in_(select(Cart.id).where(Cart.user_id == user.id)))
    )
    await db.commit()

    # Asynchronous communication: tell other services, don't wait for them
    await publish(
        "payment.succeeded",
        {"order_id": payment.order_id, "payment_id": payment.id, "user_id": user.id, "amount": payment.amount},
    )
    # Runs after the response has been sent
    background.add_task(send_order_confirmation, user.email, payment.order_id, payment.amount)
    return payment
