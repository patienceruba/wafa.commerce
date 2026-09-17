from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel

from config.database import get_db
from users.routers import get_current_user
from users.models import User
from users.schemas import UserResponse
from orders.schemas import OrderResponse, OrderDetailResponse, OrderUpdate
from orders.services import OrderService
from products.schemas import ProductResponse, ProductCreate, ProductUpdate
from products.services import ProductService
from admin.services import AdminService

router = APIRouter(prefix="/admin", tags=["admin"])


def get_admin_service(db: Session = Depends(get_db)) -> AdminService:
    return AdminService(db)


def get_order_service(db: Session = Depends(get_db)) -> OrderService:
    return OrderService(db)


def get_product_service(db: Session = Depends(get_db)) -> ProductService:
    return ProductService(db)


def require_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """Ensure the user has administrative privileges."""
    if not (current_user.is_admin or current_user.role == "admin" or current_user.role == "owner"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required to access this resource",
        )
    return current_user


class UserRoleUpdateRequest(BaseModel):
    is_admin: Optional[bool] = None
    is_seller: Optional[bool] = None
    is_subcriber: Optional[bool] = None
    is_active: Optional[bool] = None


class OrderQuickStatusRequest(BaseModel):
    status: str
    payment_status: Optional[str] = None
    tracking_number: Optional[str] = None
    shipping_carrier: Optional[str] = None
    comment: Optional[str] = None


# ==========================================
# DASHBOARD STATS
# ==========================================

@router.get("/stats")
def get_dashboard_stats(
    admin_service: AdminService = Depends(get_admin_service),
):
    """Get aggregated metrics, revenue counters, and recent activity for the admin dashboard."""
    return admin_service.get_dashboard_stats()


# ==========================================
# USER & CUSTOMER MANAGEMENT
# ==========================================

@router.get("/users", response_model=List[UserResponse])
def list_users(
    search: Optional[str] = None,
    role: Optional[str] = None,
    admin_service: AdminService = Depends(get_admin_service),
):
    """List registered users with role status."""
    return admin_service.get_users(search=search, role=role)


@router.put("/users/{user_id}/roles", response_model=UserResponse)
def update_user_roles(
    user_id: int,
    data: UserRoleUpdateRequest,
    admin_service: AdminService = Depends(get_admin_service),
):
    """Toggle user role flags (is_admin, is_seller, is_subcriber, is_active)."""
    return admin_service.update_user_roles(
        user_id=user_id,
        is_admin=data.is_admin,
        is_seller=data.is_seller,
        is_subcriber=data.is_subcriber,
        is_active=data.is_active,
    )


# ==========================================
# ORDER FULFILLMENT & MANAGEMENT
# ==========================================

@router.get("/orders")
def list_all_orders(
    status: Optional[str] = None,
    payment_status: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    order_service: OrderService = Depends(get_order_service),
):
    """List all store orders across all customers with filtering."""
    items, total = order_service.get_orders(
        user_id=None,
        status_filter=status,
        payment_status_filter=payment_status,
        search=search,
        page=page,
        page_size=page_size,
    )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items,
    }


@router.put("/orders/{order_id}/status", response_model=OrderDetailResponse)
def quick_update_order_status(
    order_id: int,
    data: OrderQuickStatusRequest,
    order_service: OrderService = Depends(get_order_service),
):
    """Quick update order fulfillment status and tracking info."""
    update_payload = OrderUpdate(
        status=data.status,
        payment_status=data.payment_status,
        tracking_number=data.tracking_number,
        shipping_carrier=data.shipping_carrier,
        status_comment=data.comment or f"Order marked as {data.status} by Admin",
    )
    return order_service.update_order(order_id, update_payload)
