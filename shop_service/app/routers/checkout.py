from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Payment
from ..schemas import CheckoutIn, CheckoutOut, PaymentOut
from ..security import CurrentUser, get_current_user
from ..services.core_client import CoreClient, get_core_client
from .cart import get_cart_for

router = APIRouter(prefix="/api/shop", tags=["checkout"])


@router.post("/checkout/", response_model=CheckoutOut, status_code=status.HTTP_201_CREATED, summary="Place an order")
async def checkout(
    body: CheckoutIn,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    core: CoreClient = Depends(get_core_client),
):
    """
    1. Read the user's cart (this service's database)
    2. Ask the core service to create the order. It re-checks stock and prices
       inside a database transaction and returns the order with status PENDING.
    3. Create a PENDING payment here and return both to the frontend.
    """
    cart = await get_cart_for(db, user.id)
    if cart is None or not cart.items:
        raise HTTPException(400, "Your cart is empty.")

    order = await core.create_order(
        {
            "user_id": user.id,
            "address": body.address.model_dump(),
            "items": [{"variant_id": i.variant_id, "quantity": i.quantity} for i in cart.items],
        }
    )

    payment = Payment(order_id=order["id"], user_id=user.id, amount=order["total"], status="PENDING")
    db.add(payment)
    await db.commit()
    await db.refresh(payment)
    return CheckoutOut(order=order, payment=PaymentOut.model_validate(payment))
