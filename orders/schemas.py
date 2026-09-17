from pydantic import BaseModel, Field, EmailStr
from datetime import datetime
from typing import Optional, List, Literal
from orders.models import OrderStatus, PaymentStatus, PaymentMethod


# --- Order Item Schemas ---

class OrderItemBase(BaseModel):
    product_id: Optional[int] = None
    product_name: str
    product_sku: Optional[str] = None
    product_img: Optional[str] = None
    selected_size: Optional[str] = None
    selected_color: Optional[str] = None
    unit_price: float = Field(..., gt=0)
    qty: int = Field(1, ge=1)


class OrderItemCreate(BaseModel):
    product_id: int
    selected_size: Optional[str] = None
    selected_color: Optional[str] = None
    qty: int = Field(1, ge=1)


class OrderItemResponse(OrderItemBase):
    id: int
    order_id: int
    total_price: float

    class Config:
        from_attributes = True


# --- Order Status History ---

class OrderStatusHistoryResponse(BaseModel):
    id: int
    order_id: int
    status: str
    comment: Optional[str] = None
    notify_customer: bool
    created_at: datetime

    class Config:
        from_attributes = True


# --- Core Order Schemas ---

class OrderCreate(BaseModel):
    customer_name: str = Field(..., min_length=2, max_length=150)
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    
    # Shipping Address
    shipping_address: str = Field(..., min_length=5, max_length=255)
    shipping_city: str = Field(..., min_length=2, max_length=100)
    shipping_state: Optional[str] = None
    shipping_zip: str = Field(..., min_length=2, max_length=30)
    shipping_country: str = "US"

    # Billing Address (Optional)
    billing_address: Optional[str] = None
    billing_city: Optional[str] = None
    billing_zip: Optional[str] = None

    # Payment & Items
    payment_method: str = PaymentMethod.CREDIT_CARD.value
    coupon_code: Optional[str] = None
    customer_notes: Optional[str] = None
    items: List[OrderItemCreate] = Field(..., min_items=1)


class OrderUpdate(BaseModel):
    status: Optional[str] = None
    payment_status: Optional[str] = None
    tracking_number: Optional[str] = None
    shipping_carrier: Optional[str] = None
    shipping_address: Optional[str] = None
    shipping_city: Optional[str] = None
    shipping_state: Optional[str] = None
    shipping_zip: Optional[str] = None
    admin_notes: Optional[str] = None
    status_comment: Optional[str] = Field(None, description="Comment to add into status history log")


class OrderResponse(BaseModel):
    id: int
    order_number: str
    user_id: Optional[int] = None
    customer_name: str
    customer_email: str
    customer_phone: Optional[str] = None
    
    shipping_address: str
    shipping_city: str
    shipping_state: Optional[str] = None
    shipping_zip: str
    shipping_country: str

    currency: str
    subtotal: float
    discount: float
    coupon_code: Optional[str] = None
    shipping_fee: float
    tax_amount: float
    total: float

    status: str
    payment_status: str
    payment_method: str
    tracking_number: Optional[str] = None
    shipping_carrier: Optional[str] = None
    customer_notes: Optional[str] = None

    created_at: datetime
    updated_at: datetime
    paid_at: Optional[datetime] = None
    shipped_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class OrderDetailResponse(OrderResponse):
    items: List[OrderItemResponse] = []
    status_history: List[OrderStatusHistoryResponse] = []

    class Config:
        from_attributes = True


class PaginatedOrdersResponse(BaseModel):
    total: int
    page: int
    page_size: int
    pages: int
    items: List[OrderResponse]


# --- Cart Schemas ---

class CartItemCreate(BaseModel):
    product_id: int
    selected_size: Optional[str] = None
    selected_color: Optional[str] = None
    qty: int = Field(1, ge=1)


class CartItemUpdate(BaseModel):
    qty: int = Field(..., ge=1)


class CartItemResponse(BaseModel):
    id: int
    cart_id: int
    product_id: int
    selected_size: Optional[str] = None
    selected_color: Optional[str] = None
    qty: int
    product_name: Optional[str] = None
    product_price: Optional[float] = None
    product_img: Optional[str] = None
    subtotal: Optional[float] = None

    class Config:
        from_attributes = True


class CartResponse(BaseModel):
    id: int
    user_id: Optional[int] = None
    session_token: Optional[str] = None
    items: List[CartItemResponse] = []
    total_items: int = 0
    subtotal: float = 0.0

    class Config:
        from_attributes = True


# --- Checkout Preview Schemas ---

class CheckoutPreviewRequest(BaseModel):
    items: List[OrderItemCreate]
    coupon_code: Optional[str] = None
    shipping_country: str = "US"


class CheckoutPreviewResponse(BaseModel):
    subtotal: float
    discount: float
    discount_percentage: float
    shipping_fee: float
    tax_amount: float
    total: float
    applied_coupon: Optional[str] = None
