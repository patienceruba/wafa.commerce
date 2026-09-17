import re
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_, desc, asc
from fastapi import HTTPException, status

from products.models import Product, Category, ProductVariant, ProductImage, Review
from products.schemas import (
    ProductCreate,
    ProductUpdate,
    CategoryCreate,
    CategoryUpdate,
    ProductVariantCreate,
    ProductVariantUpdate,
    ReviewCreate,
)


def generate_slug(text: str) -> str:
    """Generate URL-friendly slug from text."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")


def sanitize_image_url(url: Optional[str]) -> Optional[str]:
    """Convert Unsplash webpage URLs to direct raw image URLs."""
    if not url or not isinstance(url, str):
        return url
    clean = url.strip()
    # If it's an Unsplash webpage URL (e.g. https://unsplash.com/photos/turned-on-laptop-on-table-HyTwtsk8XqA)
    unsplash_match = re.search(r"unsplash\.com/photos/(?:[\w-]+-)?([a-zA-Z0-9_-]+)", clean)
    if unsplash_match and not "images.unsplash.com" in clean:
        photo_id = unsplash_match.group(1)
        return f"https://unsplash.com/photos/{photo_id}/download?force=true&w=800"
    return clean


class CategoryService:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self, active_only: bool = True) -> List[Category]:
        query = self.db.query(Category)
        if active_only:
            query = query.filter(Category.is_active == True)
        return query.order_by(Category.name.asc()).all()

    def get_by_id(self, category_id: int) -> Optional[Category]:
        return self.db.query(Category).filter(Category.id == category_id).first()

    def get_by_slug(self, slug: str) -> Optional[Category]:
        return self.db.query(Category).filter(Category.slug == slug).first()

    def create(self, data: CategoryCreate) -> Category:
        slug = data.slug or generate_slug(data.name)
        # Ensure unique slug
        base_slug = slug
        count = 1
        while self.db.query(Category).filter(Category.slug == slug).first():
            slug = f"{base_slug}-{count}"
            count += 1

        category = Category(
            name=data.name,
            slug=slug,
            description=data.description,
            image_url=data.image_url,
            parent_id=data.parent_id,
            is_active=data.is_active,
        )
        self.db.add(category)
        self.db.commit()
        self.db.refresh(category)
        return category

    def update(self, category_id: int, data: CategoryUpdate) -> Category:
        category = self.get_by_id(category_id)
        if not category:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

        update_data = data.model_dump(exclude_unset=True)
        if "name" in update_data and not update_data.get("slug"):
            update_data["slug"] = generate_slug(update_data["name"])

        for key, value in update_data.items():
            setattr(category, key, value)

        self.db.commit()
        self.db.refresh(category)
        return category

    def delete(self, category_id: int) -> bool:
        category = self.get_by_id(category_id)
        if not category:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
        self.db.delete(category)
        self.db.commit()
        return True


class ProductService:
    def __init__(self, db: Session):
        self.db = db

    def get_products(
        self,
        category_id: Optional[int] = None,
        category_slug: Optional[str] = None,
        search: Optional[str] = None,
        brand: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        min_rating: Optional[float] = None,
        in_stock_only: bool = False,
        is_popular_only: bool = False,
        is_featured_only: bool = False,
        sort_by: str = "newest",  # 'newest', 'price_asc', 'price_desc', 'rating', 'popular'
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Product], int]:
        query = (
            self.db.query(Product)
            .options(
                joinedload(Product.category),
                joinedload(Product.images),
            )
            .filter(Product.is_active == True)
        )

        # Filters
        if category_id:
            query = query.filter(Product.category_id == category_id)
        elif category_slug:
            category = self.db.query(Category).filter(Category.slug == category_slug).first()
            if category:
                query = query.filter(Product.category_id == category.id)

        if brand:
            query = query.filter(func.lower(Product.brand) == brand.lower())

        if search:
            pattern = f"%{search.lower()}%"
            query = query.filter(
                or_(
                    func.lower(Product.name).like(pattern),
                    func.lower(Product.desc).like(pattern),
                    func.lower(Product.brand).like(pattern),
                )
            )

        if min_price is not None:
            query = query.filter(Product.price >= min_price)
        if max_price is not None:
            query = query.filter(Product.price <= max_price)
        if min_rating is not None:
            query = query.filter(Product.rating >= min_rating)
        if in_stock_only:
            query = query.filter(Product.in_stock == True, Product.stock_quantity > 0)
        if is_popular_only:
            query = query.filter(Product.is_popular == True)
        if is_featured_only:
            query = query.filter(Product.is_featured == True)

        # Total count before pagination
        total = query.count()

        # Sorting
        if sort_by == "price_asc":
            query = query.order_by(asc(Product.price))
        elif sort_by == "price_desc":
            query = query.order_by(desc(Product.price))
        elif sort_by == "rating":
            query = query.order_by(desc(Product.rating), desc(Product.reviews_count))
        elif sort_by == "popular":
            query = query.order_by(desc(Product.is_popular), desc(Product.reviews_count))
        else:  # newest
            query = query.order_by(desc(Product.created_at))

        # Pagination
        offset = (page - 1) * page_size
        items = query.offset(offset).limit(page_size).all()
        return items, total

    def get_by_id(self, product_id: int) -> Optional[Product]:
        return (
            self.db.query(Product)
            .options(
                joinedload(Product.category),
                joinedload(Product.reviews),
                joinedload(Product.variants),
                joinedload(Product.images),
            )
            .filter(Product.id == product_id)
            .first()
        )

    def get_by_slug(self, slug: str) -> Optional[Product]:
        return (
            self.db.query(Product)
            .options(
                joinedload(Product.category),
                joinedload(Product.reviews),
                joinedload(Product.variants),
                joinedload(Product.images),
            )
            .filter(Product.slug == slug)
            .first()
        )

    def _resolve_category_id(self, cat_name_or_id: Optional[Any], explicit_category_id: Optional[int] = None) -> Optional[int]:
        if cat_name_or_id:
            if isinstance(cat_name_or_id, int):
                return cat_name_or_id
            if isinstance(cat_name_or_id, str) and cat_name_or_id.isdigit():
                return int(cat_name_or_id)

            name_str = str(cat_name_or_id).strip()
            if name_str and name_str.lower() != "all":
                # Look up existing category by name or slug
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

                # Auto-create category if it does not exist
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

    def create(self, data: ProductCreate) -> Product:
        slug = data.slug or generate_slug(data.name)
        # Ensure unique slug
        base_slug = slug
        count = 1
        while self.db.query(Product).filter(Product.slug == slug).first():
            slug = f"{base_slug}-{count}"
            count += 1

        product_dict = data.model_dump(exclude={"colors", "slug"})
        colors_data = [color.model_dump() for color in data.colors] if data.colors else []

        # Resolve category name string to foreign key category_id
        cat_name = product_dict.pop("cat", None)
        explicit_cat_id = product_dict.get("category_id")
        resolved_cat_id = self._resolve_category_id(cat_name, explicit_cat_id)
        if resolved_cat_id is not None:
            product_dict["category_id"] = resolved_cat_id

        if "img" in product_dict and product_dict["img"]:
            product_dict["img"] = sanitize_image_url(product_dict["img"])
        if "gallery" in product_dict and product_dict["gallery"]:
            product_dict["gallery"] = [sanitize_image_url(u) for u in product_dict["gallery"] if u]

        product = Product(
            **product_dict,
            slug=slug,
            colors=colors_data,
        )
        self.db.add(product)
        self.db.commit()
        self.db.refresh(product)
        return product

    def update(self, product_id: int, data: ProductUpdate) -> Product:
        product = self.db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

        update_dict = data.model_dump(exclude_unset=True)
        if "colors" in update_dict and update_dict["colors"] is not None:
            update_dict["colors"] = [
                c.model_dump() if hasattr(c, "model_dump") else c for c in update_dict["colors"]
            ]
        if "img" in update_dict and update_dict["img"]:
            update_dict["img"] = sanitize_image_url(update_dict["img"])
        if "gallery" in update_dict and update_dict["gallery"]:
            update_dict["gallery"] = [sanitize_image_url(u) for u in update_dict["gallery"] if u]

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

    def delete(self, product_id: int) -> bool:
        product = self.db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
        self.db.delete(product)
        self.db.commit()
        return True

    # --- Review Management ---
    def get_reviews(self, product_id: int) -> List[Review]:
        return (
            self.db.query(Review)
            .filter(Review.product_id == product_id)
            .order_by(desc(Review.created_at))
            .all()
        )

    def get_recent_reviews(self, limit: int = 6) -> List[dict]:
        reviews = (
            self.db.query(Review)
            .options(joinedload(Review.product))
            .order_by(desc(Review.created_at))
            .limit(limit)
            .all()
        )
        results = []
        for r in reviews:
            results.append({
                "id": r.id,
                "product_id": r.product_id,
                "user_id": r.user_id,
                "author_name": r.author_name,
                "rating": r.rating,
                "comment": r.comment,
                "is_verified_purchase": r.is_verified_purchase,
                "created_at": r.created_at,
                "product_name": r.product.name if r.product else None,
                "product_slug": r.product.slug if r.product else None,
                "product_img": r.product.img if r.product else None,
                "product_price": r.product.price if r.product else None,
            })
        return results

    def add_review(self, product_id: int, review_data: ReviewCreate) -> Review:
        product = self.db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

        review = Review(
            product_id=product_id,
            user_id=review_data.user_id,
            author_name=review_data.author_name,
            rating=review_data.rating,
            comment=review_data.comment,
            is_verified_purchase=bool(review_data.user_id),
        )
        self.db.add(review)
        self.db.flush()

        # Recalculate average rating and reviews count
        stats = (
            self.db.query(
                func.avg(Review.rating).label("avg_rating"),
                func.count(Review.id).label("count"),
            )
            .filter(Review.product_id == product_id)
            .first()
        )
        product.rating = round(float(stats.avg_rating or 0.0), 1)
        product.reviews_count = int(stats.count or 0)

        self.db.commit()
        self.db.refresh(review)
        return review

    # --- Variant Management ---
    def add_variant(self, product_id: int, variant_data: ProductVariantCreate) -> ProductVariant:
        product = self.db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

        variant = ProductVariant(
            product_id=product_id,
            **variant_data.model_dump(),
        )
        self.db.add(variant)
        self.db.commit()
        self.db.refresh(variant)
        return variant
