import datetime
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from fastapi import HTTPException, status

from orders.promo_models import PromoCode


class PromoCodeService:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self, active_only: bool = False) -> List[PromoCode]:
        query = self.db.query(PromoCode)
        if active_only:
            query = query.filter(PromoCode.is_active == True)
        return query.order_by(desc(PromoCode.created_at)).all()

    def get_by_code(self, code: str) -> Optional[PromoCode]:
        return self.db.query(PromoCode).filter(
            PromoCode.code == code.strip().upper()
        ).first()

    def validate(self, code: str, cart_subtotal: float = 0.0) -> dict:
        """Validate a promo code and return discount info, or raise 400."""
        promo = self.get_by_code(code)
        if not promo or not promo.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Promo code '{code.upper()}' is invalid or inactive."
            )

        # Check expiry
        if promo.expires_at:
            now = datetime.datetime.now(datetime.timezone.utc)
            if promo.expires_at.tzinfo is None:
                expires = promo.expires_at.replace(tzinfo=datetime.timezone.utc)
            else:
                expires = promo.expires_at
            if now > expires:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Promo code '{promo.code}' has expired."
                )

        # Check usage limit
        if promo.max_uses is not None and promo.used_count >= promo.max_uses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Promo code '{promo.code}' has reached its usage limit."
            )

        # Check min order
        if cart_subtotal < promo.min_order_amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Minimum order of ${promo.min_order_amount:.2f} required for code '{promo.code}'."
            )

        return {
            "code": promo.code,
            "description": promo.description,
            "discount_type": promo.discount_type,
            "discount_value": promo.discount_value,
            "is_valid": True,
        }

    def apply_and_increment(self, code: str) -> None:
        """Increment usage count after a successful order."""
        promo = self.get_by_code(code)
        if promo:
            promo.used_count = (promo.used_count or 0) + 1
            self.db.commit()

    def create(self, code: str, discount_value: float, discount_type: str = "percentage",
               description: str = "", min_order_amount: float = 0.0,
               max_uses: Optional[int] = None, expires_at=None) -> PromoCode:
        existing = self.get_by_code(code)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Promo code '{code.upper()}' already exists."
            )
        promo = PromoCode(
            code=code.strip().upper(),
            description=description,
            discount_type=discount_type,
            discount_value=discount_value,
            min_order_amount=min_order_amount,
            max_uses=max_uses,
            expires_at=expires_at,
        )
        self.db.add(promo)
        self.db.commit()
        self.db.refresh(promo)
        return promo

    def update_active(self, promo_id: int, is_active: bool) -> PromoCode:
        promo = self.db.query(PromoCode).filter(PromoCode.id == promo_id).first()
        if not promo:
            raise HTTPException(status_code=404, detail="Promo code not found")
        promo.is_active = is_active
        self.db.commit()
        self.db.refresh(promo)
        return promo

    def delete(self, promo_id: int) -> None:
        promo = self.db.query(PromoCode).filter(PromoCode.id == promo_id).first()
        if not promo:
            raise HTTPException(status_code=404, detail="Promo code not found")
        self.db.delete(promo)
        self.db.commit()
