from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, desc, or_
from fastapi import HTTPException, status

from users.models import User
from products.models import Product, Category
from products.services import generate_slug
from products.schemas import ProductCreate, ProductUpdate
from orders.models import Order, OrderItem, OrderStatus, PaymentStatus


class SellerService:
    def __init__(self, db: Session):
        self.db = db

    def _resolve_category_id(self, cat_name_or_id: Optional[Any], explicit_category_id: Optional[int] = None) -> Optional[int]:
        if cat_name_or_id:
            if isinstance(cat_name_or_id, int):
                return cat_name_or_id
            if isinstance(cat_name_or_id, str) and cat_name_or_id.isdigit():
                return int(cat_name_or_id)

            name_str = str(cat_name_or_id).strip()
            if name_str and name_str.lower() != "all":
                cat = (
                    self.db.query(Category)
                    .filter(
                        or_(
                            func.lower(Category.name) == name_str.lower(),
                            func.lower(Category.slug) == generate_slug(name_str),
                        )
                    )
                    .first()
                )
                if cat:
                    return cat.id

                new_cat = Category(
                    name=name_str,
                    slug=generate_slug(name_str),
                    is_active=True,
                )
                self.db.add(new_cat)
                self.db.commit()
                self.db.refresh(new_cat)
                return new_cat.id

        if explicit_category_id:
            return explicit_category_id
        return None

    def get_seller_dashboard(self, seller_id: int) -> Dict[str, Any]:
        """Aggregate seller-specific metrics: revenue, orders, inventory, rating."""
        # Total products owned by seller
        total_products = self.db.query(func.count(Product.id)).filter(Product.seller_id == seller_id, Product.is_active == True).scalar() or 0
        low_stock_count = self.db.query(func.count(Product.id)).filter(Product.seller_id == seller_id, Product.stock_quantity <= 5, Product.is_active == True).scalar() or 0

        # Orders that include seller's products
        order_items = (
            self.db.query(OrderItem)
            .join(Product, OrderItem.product_id == Product.id)
            .filter(Product.seller_id == seller_id)
            .all()
        )

        seller_revenue = sum(item.total_price for item in order_items)
        seller_orders_count = len(set(item.order_id for item in order_items))

        # Average rating of seller's products
        avg_rating = (
            self.db.query(func.avg(Product.rating))
            .filter(Product.seller_id == seller_id, Product.is_active == True)
            .scalar() or 5.0
        )

        # Recent seller order items
        recent_order_ids = [item.order_id for item in order_items][-6:]
        recent_orders = (
            self.db.query(Order)
            .filter(Order.id.in_(recent_order_ids))
            .order_by(desc(Order.created_at))
            .all()
        ) if recent_order_ids else []

        return {
            "seller_revenue": round(float(seller_revenue), 2),
            "seller_orders_count": seller_orders_count,
            "total_products": total_products,
            "low_stock_count": low_stock_count,
            "store_rating": round(float(avg_rating), 1),
            "recent_orders": recent_orders,
        }

    def get_seller_products(self, seller_id: int, search: Optional[str] = None) -> List[Product]:
        """Fetch all products listed by this seller."""
        query = (
            self.db.query(Product)
            .options(joinedload(Product.category))
            .filter(Product.seller_id == seller_id, Product.is_active == True)
        )
        if search:
            pattern = f"%{search.lower()}%"
            query = query.filter(func.lower(Product.name).like(pattern))
        return query.order_by(desc(Product.created_at)).all()

    def create_seller_product(self, seller_id: int, data: ProductCreate) -> Product:
        """Create a new product listing linked to the seller."""
        slug = data.slug or generate_slug(data.name)
        base_slug = slug
        count = 1
        while self.db.query(Product).filter(Product.slug == slug).first():
            slug = f"{base_slug}-{count}"
            count += 1

        product_dict = data.model_dump(exclude={"colors", "slug"})
        colors_data = [color.model_dump() for color in data.colors] if data.colors else []

        # Resolve category name string to category_id
        cat_name = product_dict.pop("cat", None)
        explicit_cat_id = product_dict.get("category_id")
        resolved_cat_id = self._resolve_category_id(cat_name, explicit_cat_id)
        if resolved_cat_id is not None:
            product_dict["category_id"] = resolved_cat_id

        product = Product(
            **product_dict,
            seller_id=seller_id,
            slug=slug,
            colors=colors_data,
        )
        self.db.add(product)
        self.db.commit()
        self.db.refresh(product)
        return product

    def update_seller_product(self, seller_id: int, product_id: int, data: ProductUpdate) -> Product:
        """Update a seller-owned product listing."""
        product = self.db.query(Product).filter(Product.id == product_id, Product.seller_id == seller_id).first()
        if not product:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found or unauthorized")

        update_dict = data.model_dump(exclude_unset=True)
        if "colors" in update_dict and update_dict["colors"] is not None:
            update_dict["colors"] = [
                c.model_dump() if hasattr(c, "model_dump") else c for c in update_dict["colors"]
            ]

        # Resolve category name string to category_id
        cat_name = update_dict.pop("cat", None)
        explicit_cat_id = update_dict.get("category_id")
        if cat_name is not None or explicit_cat_id is not None:
            resolved_cat_id = self._resolve_category_id(cat_name, explicit_cat_id)
            if resolved_cat_id is not None:
                update_dict["category_id"] = resolved_cat_id
                product.category_id = resolved_cat_id

        for key, value in update_dict.items():
            setattr(product, key, value)

        self.db.commit()
        self.db.refresh(product)
        return product

    def delete_seller_product(self, seller_id: int, product_id: int) -> bool:
        """Delete / unpublish seller's product."""
        product = self.db.query(Product).filter(Product.id == product_id, Product.seller_id == seller_id).first()
        if not product:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found or unauthorized")

        self.db.delete(product)
        self.db.commit()
        return True
