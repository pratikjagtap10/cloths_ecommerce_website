from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Cart, CartItem
from ..schemas import AddItemIn, CartItemOut, CartOut, UpdateItemIn
from ..security import CurrentUser, get_current_user
from ..services.core_client import CoreClient, get_core_client

router = APIRouter(prefix="/api/shop/cart", tags=["cart"])


async def get_cart_for(db: AsyncSession, user_id: int, create: bool = False) -> Cart | None:
    cart = await db.scalar(select(Cart).where(Cart.user_id == user_id))
    if cart is None and create:
        cart = Cart(user_id=user_id, items=[])
        db.add(cart)
        await db.flush()
    return cart


def to_cart_out(cart: Cart | None) -> CartOut:
    items = cart.items if cart else []
    return CartOut(
        items=[CartItemOut.model_validate(i) for i in items],
        subtotal=sum(i.unit_price * i.quantity for i in items),
    )


def _find_item(cart: Cart | None, item_id: int) -> CartItem:
    item = next((i for i in (cart.items if cart else []) if i.id == item_id), None)
    if item is None:
        raise HTTPException(404, "Cart item not found.")
    return item


@router.get("/", response_model=CartOut, summary="Get my cart")
async def get_cart(user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return to_cart_out(await get_cart_for(db, user.id))


@router.post("/items/", response_model=CartOut, summary="Add a product variant to my cart")
async def add_item(
    body: AddItemIn,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    core: CoreClient = Depends(get_core_client),
):
    # Synchronous call to the core service: current price + stock (core is the source of truth)
    variant = await core.get_variant(body.variant_id)
    if not variant["is_active"]:
        raise HTTPException(400, "This product is no longer available.")

    cart = await get_cart_for(db, user.id, create=True)
    existing = next((i for i in cart.items if i.variant_id == body.variant_id), None)
    new_quantity = (existing.quantity if existing else 0) + body.quantity
    if new_quantity > variant["stock"]:
        raise HTTPException(
            400, f"Only {variant['stock']} left in stock for {variant['color']} / {variant['size']}."
        )

    if existing:
        existing.quantity = new_quantity
        existing.unit_price = variant["price"]
    else:
        cart.items.append(
            CartItem(
                variant_id=variant["id"],
                quantity=body.quantity,
                unit_price=variant["price"],
                product_name=variant["product_name"],
                product_slug=variant["product_slug"],
                size=variant["size"],
                color=variant["color"],
                color_hex=variant["color_hex"],
            )
        )
    await db.commit()
    return to_cart_out(cart)


@router.patch("/items/{item_id}/", response_model=CartOut, summary="Change quantity of a cart item")
async def update_item(
    item_id: int,
    body: UpdateItemIn,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    core: CoreClient = Depends(get_core_client),
):
    cart = await get_cart_for(db, user.id)
    item = _find_item(cart, item_id)
    variant = await core.get_variant(item.variant_id)
    if body.quantity > variant["stock"]:
        raise HTTPException(400, f"Only {variant['stock']} left in stock.")
    item.quantity = body.quantity
    item.unit_price = variant["price"]
    await db.commit()
    return to_cart_out(cart)


@router.delete("/items/{item_id}/", response_model=CartOut, summary="Remove an item from my cart")
async def remove_item(
    item_id: int, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    cart = await get_cart_for(db, user.id)
    item = _find_item(cart, item_id)
    cart.items.remove(item)  # delete-orphan cascade deletes the row
    await db.commit()
    return to_cart_out(cart)
