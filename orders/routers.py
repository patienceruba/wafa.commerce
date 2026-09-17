from fastapi import APIRouter, Depends, HTTPException, status, Query, Header
from sqlalchemy.orm import Session
from typing import Optional, List
import math

from config.database import get_db
from users.routers import get_current_user
from users.models import User
from orders.schemas import (
    OrderCreate,
    OrderUpdate,
    OrderResponse,
    OrderDetailResponse,
    PaginatedOrdersResponse,
    CartItemCreate,
    CartItemUpdate,
    CartResponse,
    CheckoutPreviewRequest,
    CheckoutPreviewResponse,
)
from orders.services import OrderService, CartService
from orders.promo_service import PromoCodeService
from orders.promo_models import PromoCode

router = APIRouter(prefix="/orders", tags=["orders"])


def get_order_service(db: Session = Depends(get_db)) -> OrderService:
    return OrderService(db)


def get_cart_service(db: Session = Depends(get_db)) -> CartService:
    return CartService(db)


def get_optional_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Helper to extract user if authorization token is provided, without blocking guest checkouts."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        from users.routers import oauth2_scheme, get_current_user_from_token
        token = authorization.split(" ")[1]
        return get_current_user_from_token(token, db)
    except Exception:
        return None


# ==========================================
# CHECKOUT & ORDER ENDPOINTS
# ==========================================

@router.post("/preview", response_model=CheckoutPreviewResponse)
def preview_checkout(
    request: CheckoutPreviewRequest,
    order_service: OrderService = Depends(get_order_service),
):
    """Preview order totals, calculate coupon discounts, estimated shipping, and taxes."""
    return order_service.preview_checkout(request)


@router.post("", response_model=OrderDetailResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=OrderDetailResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False)
def create_order(
    order_data: OrderCreate,
    current_user: Optional[User] = Depends(get_optional_user),
    order_service: OrderService = Depends(get_order_service),
):
    """Place a new order (supports both logged-in members and guest checkouts)."""
    user_id = current_user.id if current_user else None
    return order_service.create_order(order_data, user_id=user_id)


@router.get("", response_model=PaginatedOrdersResponse)
@router.get("/", response_model=PaginatedOrdersResponse, include_in_schema=False)
def list_orders(
    status: Optional[str] = None,
    payment_status: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    order_service: OrderService = Depends(get_order_service),
):
    """List orders for the authenticated user (or all if admin)."""
    user_id = None if current_user.role == "admin" else current_user.id
    items, total = order_service.get_orders(
        user_id=user_id,
        status_filter=status,
        payment_status_filter=payment_status,
        search=search,
        page=page,
        page_size=page_size,
    )
    pages = math.ceil(total / page_size) if total > 0 else 1
    return PaginatedOrdersResponse(
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        items=items,
    )


@router.get("/{order_id_or_number}", response_model=OrderDetailResponse)
def get_order_details(
    order_id_or_number: str,
    current_user: Optional[User] = Depends(get_optional_user),
    order_service: OrderService = Depends(get_order_service),
):
    """Get full order details with ordered line items and status tracking history."""
    user_id = current_user.id if current_user and current_user.role != "admin" else None
    order = order_service.get_by_id_or_number(order_id_or_number, user_id=user_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order


@router.put("/{order_id}", response_model=OrderDetailResponse)
def update_order(
    order_id: int,
    order_data: OrderUpdate,
    current_user: User = Depends(get_current_user),
    order_service: OrderService = Depends(get_order_service),
):
    """Update order status, shipping carrier, tracking number, or notes."""
    return order_service.update_order(order_id, order_data)


# ==========================================
# SHOPPING CART ENDPOINTS
# ==========================================

@router.get("/cart/current", response_model=CartResponse)
def get_cart(
    session_token: Optional[str] = Header(None, alias="X-Session-Token"),
    current_user: Optional[User] = Depends(get_optional_user),
    cart_service: CartService = Depends(get_cart_service),
):
    """Get contents of user's shopping cart."""
    user_id = current_user.id if current_user else None
    return cart_service.get_cart_response(user_id=user_id, session_token=session_token)


@router.post("/cart/items", response_model=CartResponse, status_code=status.HTTP_201_CREATED)
def add_to_cart(
    item_data: CartItemCreate,
    session_token: Optional[str] = Header(None, alias="X-Session-Token"),
    current_user: Optional[User] = Depends(get_optional_user),
    cart_service: CartService = Depends(get_cart_service),
):
    """Add a product with selected size/color to the cart."""
    user_id = current_user.id if current_user else None
    return cart_service.add_to_cart(item_data, user_id=user_id, session_token=session_token)


@router.put("/cart/items/{item_id}", response_model=CartResponse)
def update_cart_item_quantity(
    item_id: int,
    item_data: CartItemUpdate,
    session_token: Optional[str] = Header(None, alias="X-Session-Token"),
    current_user: Optional[User] = Depends(get_optional_user),
    cart_service: CartService = Depends(get_cart_service),
):
    """Update quantity of a specific cart item."""
    user_id = current_user.id if current_user else None
    return cart_service.update_item_qty(item_id, item_data.qty, user_id=user_id, session_token=session_token)


@router.delete("/cart/items/{item_id}", response_model=CartResponse)
def remove_from_cart(
    item_id: int,
    session_token: Optional[str] = Header(None, alias="X-Session-Token"),
    current_user: Optional[User] = Depends(get_optional_user),
    cart_service: CartService = Depends(get_cart_service),
):
    """Remove an item from the cart."""
    user_id = current_user.id if current_user else None
    return cart_service.remove_item(item_id, user_id=user_id, session_token=session_token)


@router.delete("/cart/current", response_model=CartResponse)
def clear_cart(
    session_token: Optional[str] = Header(None, alias="X-Session-Token"),
    current_user: Optional[User] = Depends(get_optional_user),
    cart_service: CartService = Depends(get_cart_service),
):
    """Clear all items from the shopping cart."""
    user_id = current_user.id if current_user else None
    return cart_service.clear_cart(user_id=user_id, session_token=session_token)


def get_promo_service(db: Session = Depends(get_db)) -> PromoCodeService:
    return PromoCodeService(db)


# ==========================================
# PROMO CODE ENDPOINTS
# ==========================================

@router.get("/promos", tags=["promos"])
def list_promo_codes(
    active_only: bool = False,
    promo_service: PromoCodeService = Depends(get_promo_service),
):
    """List all promo codes. Public endpoint returns active codes only; pass active_only=false for admin view."""
    promos = promo_service.get_all(active_only=active_only)
    return [
        {
            "id": p.id,
            "code": p.code,
            "description": p.description,
            "discount_type": p.discount_type,
            "discount_value": p.discount_value,
            "min_order_amount": p.min_order_amount,
            "max_uses": p.max_uses,
            "used_count": p.used_count,
            "is_active": p.is_active,
            "expires_at": p.expires_at.isoformat() if p.expires_at else None,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in promos
    ]


@router.post("/promos/validate", tags=["promos"])
def validate_promo_code(
    body: dict,
    promo_service: PromoCodeService = Depends(get_promo_service),
):
    """Validate a promo code and return discount info. Used by checkout."""
    code = body.get("code", "")
    subtotal = float(body.get("subtotal", 0))
    return promo_service.validate(code, cart_subtotal=subtotal)


@router.post("/promos", status_code=status.HTTP_201_CREATED, tags=["promos"])
def create_promo_code(
    body: dict,
    current_user: User = Depends(get_current_user),
    promo_service: PromoCodeService = Depends(get_promo_service),
):
    """Create a new promo code. Admin/seller only."""
    if not (current_user.is_admin or current_user.is_seller or current_user.role in ['admin', 'owner', 'seller']):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Seller or Admin access required.")

    expires_at = None
    if body.get("expires_at"):
        import datetime
        try:
            expires_at = datetime.datetime.fromisoformat(body["expires_at"])
        except ValueError:
            pass

    promo = promo_service.create(
        code=body.get("code", ""),
        discount_value=float(body.get("discount_value", 0)),
        discount_type=body.get("discount_type", "percentage"),
        description=body.get("description", ""),
        min_order_amount=float(body.get("min_order_amount", 0)),
        max_uses=int(body["max_uses"]) if body.get("max_uses") else None,
        expires_at=expires_at,
    )
    return {"id": promo.id, "code": promo.code, "discount_value": promo.discount_value, "is_active": promo.is_active}


@router.patch("/promos/{promo_id}/toggle", tags=["promos"])
def toggle_promo_code(
    promo_id: int,
    body: dict,
    current_user: User = Depends(get_current_user),
    promo_service: PromoCodeService = Depends(get_promo_service),
):
    """Activate or deactivate a promo code."""
    if not (current_user.is_admin or current_user.is_seller or current_user.role in ['admin', 'owner', 'seller']):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Seller or Admin access required.")
    promo = promo_service.update_active(promo_id, bool(body.get("is_active", True)))
    return {"id": promo.id, "code": promo.code, "is_active": promo.is_active}


@router.delete("/promos/{promo_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["promos"])
def delete_promo_code(
    promo_id: int,
    current_user: User = Depends(get_current_user),
    promo_service: PromoCodeService = Depends(get_promo_service),
):
    """Delete a promo code permanently."""
    if not (current_user.is_admin or current_user.is_seller or current_user.role in ['admin', 'owner', 'seller']):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Seller or Admin access required.")
    promo_service.delete(promo_id)
    return None
