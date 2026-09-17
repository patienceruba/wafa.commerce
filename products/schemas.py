from pydantic import BaseModel, Field, HttpUrl
from datetime import datetime
from typing import Optional, List, Any


# --- Category Schemas ---

class CategoryBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    slug: Optional[str] = Field(None, max_length=120)
    description: Optional[str] = None
    image_url: Optional[str] = None
    parent_id: Optional[int] = None
    is_active: bool = True


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    slug: Optional[str] = Field(None, max_length=120)
    description: Optional[str] = None
    image_url: Optional[str] = None
    parent_id: Optional[int] = None
    is_active: Optional[bool] = None


class CategoryResponse(CategoryBase):
    id: int
    slug: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# --- Product Variant & Image Schemas ---

class ProductColor(BaseModel):
    name: str
    hex: str


class ProductVariantBase(BaseModel):
    title: str
    sku: Optional[str] = None
    color_name: Optional[str] = None
    color_hex: Optional[str] = None
    size: Optional[str] = None
    price_override: Optional[float] = Field(None, gt=0)
    stock_quantity: int = Field(0, ge=0)
    img: Optional[str] = None
    is_active: bool = True


class ProductVariantCreate(ProductVariantBase):
    pass


class ProductVariantUpdate(BaseModel):
    title: Optional[str] = None
    sku: Optional[str] = None
    color_name: Optional[str] = None
    color_hex: Optional[str] = None
    size: Optional[str] = None
    price_override: Optional[float] = None
    stock_quantity: Optional[int] = None
    img: Optional[str] = None
    is_active: Optional[bool] = None


class ProductVariantResponse(ProductVariantBase):
    id: int
    product_id: int

    class Config:
        from_attributes = True


class ProductImageBase(BaseModel):
    image_url: str
    alt_text: Optional[str] = None
    is_primary: bool = False
    display_order: int = 0


class ProductImageCreate(ProductImageBase):
    pass


class ProductImageResponse(ProductImageBase):
    id: int
    product_id: int

    class Config:
        from_attributes = True


# --- Review Schemas ---

class ReviewCreate(BaseModel):
    author_name: str = Field(..., min_length=2, max_length=100)
    rating: float = Field(..., ge=1.0, le=5.0)
    comment: str = Field(..., min_length=3)
    user_id: Optional[int] = None


class ReviewUpdate(BaseModel):
    rating: Optional[float] = Field(None, ge=1.0, le=5.0)
    comment: Optional[str] = None


class ReviewResponse(BaseModel):
    id: int
    product_id: int
    user_id: Optional[int] = None
    author_name: str
    rating: float
    comment: str
    is_verified_purchase: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ReviewWithProductResponse(ReviewResponse):
    product_name: Optional[str] = None
    product_slug: Optional[str] = None
    product_img: Optional[str] = None
    product_price: Optional[float] = None


# --- Core Product Schemas ---

class ProductBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    slug: Optional[str] = None
    sku: Optional[str] = None
    brand: Optional[str] = None
    category_id: Optional[int] = None
    price: float = Field(..., gt=0)
    old_price: Optional[float] = Field(None, gt=0)
    cost_price: Optional[float] = Field(None, gt=0)
    stock_quantity: int = Field(0, ge=0)
    in_stock: bool = True
    img: Optional[str] = None
    gallery: List[str] = []
    badge: Optional[str] = None
    desc: Optional[str] = None
    details: List[str] = []
    colors: List[ProductColor] = []
    sizes: List[Any] = []
    is_popular: bool = False
    is_featured: bool = False
    is_active: bool = True


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    sku: Optional[str] = None
    brand: Optional[str] = None
    category_id: Optional[int] = None
    price: Optional[float] = Field(None, gt=0)
    old_price: Optional[float] = None
    cost_price: Optional[float] = None
    stock_quantity: Optional[int] = Field(None, ge=0)
    in_stock: Optional[bool] = None
    img: Optional[str] = None
    gallery: Optional[List[str]] = None
    badge: Optional[str] = None
    desc: Optional[str] = None
    details: Optional[List[str]] = None
    colors: Optional[List[ProductColor]] = None
    sizes: Optional[List[Any]] = None
    is_popular: Optional[bool] = None
    is_featured: Optional[bool] = None
    is_active: Optional[bool] = None


class ProductResponse(ProductBase):
    id: int
    slug: str
    rating: float
    reviews_count: int
    discount_percentage: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProductDetailResponse(ProductResponse):
    category: Optional[CategoryResponse] = None
    reviews: List[ReviewResponse] = []
    variants: List[ProductVariantResponse] = []
    images: List[ProductImageResponse] = []

    class Config:
        from_attributes = True


class PaginatedProductsResponse(BaseModel):
    total: int
    page: int
    page_size: int
    pages: int
    items: List[ProductResponse]

