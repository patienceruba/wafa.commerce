from sqlalchemy import Column, Integer, Float, String, Boolean, DateTime
from sqlalchemy.sql import func
from config.database import Base


class PromoCode(Base):
    """
    Promotional Coupon Code Model.
    Allows admins/sellers to create, deactivate and manage discount codes
    that customers can apply at checkout.
    """
    __tablename__ = "promo_codes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)   # e.g. "WAFA20"
    description = Column(String(255), nullable=True)                      # e.g. "20% Off All Tech"
    discount_type = Column(String(20), default="percentage", nullable=False)  # "percentage" | "fixed"
    discount_value = Column(Float, nullable=False)                         # 20 → 20% | 15 → $15 off
    min_order_amount = Column(Float, default=0.0, nullable=False)          # Minimum cart value to qualify
    max_uses = Column(Integer, nullable=True)                              # None = unlimited
    used_count = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)           # None = never expires
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<PromoCode(code='{self.code}', value={self.discount_value}, active={self.is_active})>"
