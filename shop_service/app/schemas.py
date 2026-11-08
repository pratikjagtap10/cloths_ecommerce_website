"""Pydantic models: validate request bodies and shape responses.
Field names match frontend/src/types/index.ts."""
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AddItemIn(BaseModel):
    variant_id: int = Field(gt=0, examples=[2])
    quantity: int = Field(default=1, gt=0, le=20, examples=[1])


class UpdateItemIn(BaseModel):
    quantity: int = Field(gt=0, le=20, examples=[3])


class CartItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    variant_id: int
    product_name: str
    product_slug: str
    size: str
    color: str
    color_hex: str
    quantity: int
    unit_price: int


class CartOut(BaseModel):
    items: list[CartItemOut]
    subtotal: int


class AddressIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=100, examples=["Demo User"])
    phone: str = Field(examples=["9876543210"])
    line1: str = Field(min_length=5, max_length=200, examples=["12 MG Road"])
    city: str = Field(min_length=2, max_length=80, examples=["Pune"])
    state: str = Field(min_length=2, max_length=80, examples=["Maharashtra"])
    postal_code: str = Field(examples=["411001"])

    @field_validator("phone")
    @classmethod
    def valid_phone(cls, v: str) -> str:
        if not re.fullmatch(r"[6-9]\d{9}", v):
            raise ValueError("Enter a valid 10-digit mobile number")
        return v

    @field_validator("postal_code")
    @classmethod
    def valid_pin(cls, v: str) -> str:
        if not re.fullmatch(r"\d{6}", v):
            raise ValueError("PIN code must be 6 digits")
        return v


class CheckoutIn(BaseModel):
    address: AddressIn


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    amount: int
    status: str


class CheckoutOut(BaseModel):
    order: dict[str, Any]  # passed through from the core service as-is
    payment: PaymentOut


class ConfirmPaymentIn(BaseModel):
    success: bool = Field(default=True, description="true = simulate success, false = simulate failure")
