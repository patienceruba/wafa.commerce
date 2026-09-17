from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional, List
import math

from config.database import get_db
from users.routers import get_current_user
from users.models import User
from products.schemas import (
    ProductCreate,
    ProductUpdate,
    ProductResponse,
    ProductDetailResponse,
    PaginatedProductsResponse,
    CategoryCreate,
    CategoryUpdate,
    CategoryResponse,
    ReviewCreate,
    ReviewResponse,
    ReviewWithProductResponse,
    ProductVariantCreate,
    ProductVariantResponse,
)
from products.services import ProductService, CategoryService

router = APIRouter(prefix="/products", tags=["products"])


def get_product_service(db: Session = Depends(get_db)) -> ProductService:
    return ProductService(db)


def get_category_service(db: Session = Depends(get_db)) -> CategoryService:
    return CategoryService(db)


# ==========================================
# CATEGORY ENDPOINTS
# ==========================================

@router.get("/categories", response_model=List[CategoryResponse])
def list_categories(
    active_only: bool = True,
    category_service: CategoryService = Depends(get_category_service),
):
    """List all product categories."""
    return category_service.get_all(active_only=active_only)


@router.post("/categories", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
def create_category(
    category_data: CategoryCreate,
    current_user: User = Depends(get_current_user),
    category_service: CategoryService = Depends(get_category_service),
):
    """Create a new category."""
    return category_service.create(category_data)


@router.get("/categories/{category_id_or_slug}", response_model=CategoryResponse)
def get_category(
    category_id_or_slug: str,
    category_service: CategoryService = Depends(get_category_service),
):
    """Get category by numeric ID or URL slug."""
    if category_id_or_slug.isdigit():
        category = category_service.get_by_id(int(category_id_or_slug))
    else:
        category = category_service.get_by_slug(category_id_or_slug)

    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    return category


@router.put("/categories/{category_id}", response_model=CategoryResponse)
def update_category(
    category_id: int,
    category_data: CategoryUpdate,
    current_user: User = Depends(get_current_user),
    category_service: CategoryService = Depends(get_category_service),
):
    """Update an existing category."""
    return category_service.update(category_id, category_data)


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    category_id: int,
    current_user: User = Depends(get_current_user),
    category_service: CategoryService = Depends(get_category_service),
):
    """Delete a category."""
    category_service.delete(category_id)
    return None


# ==========================================
# PRODUCT ENDPOINTS
# ==========================================

@router.get("", response_model=PaginatedProductsResponse)
def list_products(
    category_id: Optional[int] = None,
    category: Optional[str] = Query(None, description="Category slug"),
    search: Optional[str] = None,
    brand: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    min_rating: Optional[float] = None,
    in_stock_only: bool = False,
    is_popular_only: bool = False,
    is_featured_only: bool = False,
    sort_by: str = Query("newest", pattern="^(newest|price_asc|price_desc|rating|popular)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    product_service: ProductService = Depends(get_product_service),
):
    """List products with advanced filtering, sorting, and pagination."""
    items, total = product_service.get_products(
        category_id=category_id,
        category_slug=category,
        search=search,
        brand=brand,
        min_price=min_price,
        max_price=max_price,
        min_rating=min_rating,
        in_stock_only=in_stock_only,
        is_popular_only=is_popular_only,
        is_featured_only=is_featured_only,
        sort_by=sort_by,
        page=page,
        page_size=page_size,
    )
    pages = math.ceil(total / page_size) if total > 0 else 1
    return PaginatedProductsResponse(
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        items=items,
    )


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(
    product_data: ProductCreate,
    current_user: User = Depends(get_current_user),
    product_service: ProductService = Depends(get_product_service),
):
    """Create a new product."""
    return product_service.create(product_data)


@router.get("/reviews/recent", response_model=List[ReviewWithProductResponse])
def get_recent_reviews(
    limit: int = Query(6, ge=1, le=20),
    product_service: ProductService = Depends(get_product_service),
):
    """List recent verified customer reviews across all products with product details."""
    return product_service.get_recent_reviews(limit=limit)


@router.get("/{product_id_or_slug}", response_model=ProductDetailResponse)
def get_product_details(
    product_id_or_slug: str,
    product_service: ProductService = Depends(get_product_service),
):
    """Get full product details including variants, images, and reviews."""
    if product_id_or_slug.isdigit():
        product = product_service.get_by_id(int(product_id_or_slug))
    else:
        product = product_service.get_by_slug(product_id_or_slug)

    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


@router.put("/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: int,
    product_data: ProductUpdate,
    current_user: User = Depends(get_current_user),
    product_service: ProductService = Depends(get_product_service),
):
    """Update product details."""
    return product_service.update(product_id, product_data)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: int,
    current_user: User = Depends(get_current_user),
    product_service: ProductService = Depends(get_product_service),
):
    """Delete a product."""
    product_service.delete(product_id)
    return None


# ==========================================
# REVIEWS & VARIANTS
# ==========================================

@router.get("/{product_id}/reviews", response_model=List[ReviewResponse])
def list_product_reviews(
    product_id: int,
    product_service: ProductService = Depends(get_product_service),
):
    """List all reviews for a product in descending chronological order."""
    return product_service.get_reviews(product_id)


@router.post("/{product_id}/reviews", response_model=ReviewResponse, status_code=status.HTTP_201_CREATED)
def add_product_review(
    product_id: int,
    review_data: ReviewCreate,
    product_service: ProductService = Depends(get_product_service),
):
    """Add a customer review and recalculate the product rating."""
    return product_service.add_review(product_id, review_data)


@router.post("/{product_id}/variants", response_model=ProductVariantResponse, status_code=status.HTTP_201_CREATED)
def add_product_variant(
    product_id: int,
    variant_data: ProductVariantCreate,
    current_user: User = Depends(get_current_user),
    product_service: ProductService = Depends(get_product_service),
):
    """Add a SKU variant (size/color/price variation) to a product."""
    return product_service.add_variant(product_id, variant_data)
