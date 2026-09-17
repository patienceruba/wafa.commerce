from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from fastapi import HTTPException, status

from users.models import User
from products.models import Product, Category, Review
from orders.models import Order, OrderItem, OrderStatus, PaymentStatus


class AdminService:
    def __init__(self, db: Session):
        self.db = db

    def get_dashboard_stats(self) -> Dict[str, Any]:
        """Aggregate high-level key performance metrics across the store."""
        total_revenue = (
            self.db.query(func.sum(Order.total))
            .filter(Order.payment_status == PaymentStatus.PAID.value)
            .scalar() or 0.0
        )

        total_orders = self.db.query(func.count(Order.id)).scalar() or 0
        pending_orders = self.db.query(func.count(Order.id)).filter(Order.status == OrderStatus.PENDING.value).scalar() or 0
        processing_orders = self.db.query(func.count(Order.id)).filter(Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.PROCESSING.value])).scalar() or 0
        shipped_orders = self.db.query(func.count(Order.id)).filter(Order.status == OrderStatus.SHIPPED.value).scalar() or 0
        delivered_orders = self.db.query(func.count(Order.id)).filter(Order.status == OrderStatus.DELIVERED.value).scalar() or 0

        total_products = self.db.query(func.count(Product.id)).filter(Product.is_active == True).scalar() or 0
        low_stock_products = self.db.query(func.count(Product.id)).filter(Product.stock_quantity <= 5, Product.is_active == True).scalar() or 0
        total_users = self.db.query(func.count(User.id)).scalar() or 0

        recent_orders = (
            self.db.query(Order)
            .order_by(desc(Order.created_at))
            .limit(6)
            .all()
        )

        top_products = (
            self.db.query(Product)
            .filter(Product.is_active == True)
            .order_by(desc(Product.rating), desc(Product.reviews_count))
            .limit(5)
            .all()
        )

        return {
            "total_revenue": round(float(total_revenue), 2),
            "total_orders": total_orders,
            "pending_orders": pending_orders,
            "processing_orders": processing_orders,
            "shipped_orders": shipped_orders,
            "delivered_orders": delivered_orders,
            "total_products": total_products,
            "low_stock_products": low_stock_products,
            "total_users": total_users,
            "recent_orders": recent_orders,
            "top_products": top_products,
        }

    def get_users(self, search: Optional[str] = None, role: Optional[str] = None) -> List[User]:
        """Fetch all users with optional role and search filters."""
        query = self.db.query(User)
        if role:
            if role == "admin":
                query = query.filter((User.is_admin == True) | (User.role == "admin"))
            elif role == "seller":
                query = query.filter(User.is_seller == True)
            elif role == "subscriber":
                query = query.filter(User.is_subcriber == True)
        if search:
            pattern = f"%{search.lower()}%"
            query = query.filter(
                (func.lower(User.username).like(pattern))
                | (func.lower(User.email).like(pattern))
                | (func.lower(User.f_name).like(pattern))
                | (func.lower(User.l_name).like(pattern))
            )
        return query.order_by(desc(User.id)).all()

    def update_user_roles(
        self,
        user_id: int,
        is_admin: Optional[bool] = None,
        is_seller: Optional[bool] = None,
        is_subcriber: Optional[bool] = None,
        is_active: Optional[bool] = None,
    ) -> User:
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        if is_admin is not None:
            user.is_admin = is_admin
            if is_admin:
                user.role = "admin"
            elif user.role == "admin":
                user.role = "user"
        if is_seller is not None:
            user.is_seller = is_seller
        if is_subcriber is not None:
            user.is_subcriber = is_subcriber
        if is_active is not None:
            user.is_active = is_active

        self.db.commit()
        self.db.refresh(user)
        return user
