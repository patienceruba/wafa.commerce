from sqlalchemy import Column, Integer, Float, String, Text, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from config.database import Base


class Category(Base):
    """
    Product Category Model (hierarchical support with parent/child categories).
    """
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    slug = Column(String(120), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    image_url = Column(String(500), nullable=True)
    parent_id = Column(Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    parent = relationship("Category", remote_side=[id], backref="children")
    products = relationship("Product", back_populates="category", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Category(id={self.id}, name='{self.name}', slug='{self.slug}')>"


class Product(Base):
    """
    Core E-Commerce Product Model.
    Supports pricing, multi-image galleries, attribute variations (colors, sizes, details),
    ratings, badges, inventory management, and SEO-friendly slugs.
    """
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    slug = Column(String(280), unique=True, nullable=False, index=True)
    sku = Column(String(100), unique=True, nullable=True, index=True)
    brand = Column(String(100), nullable=True, index=True)
    
    # Categorization & Ownership
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    # Pricing & Inventory
    price = Column(Float, nullable=False)
    old_price = Column(Float, nullable=True)
    cost_price = Column(Float, nullable=True)
    stock_quantity = Column(Integer, default=0, nullable=False)
    in_stock = Column(Boolean, default=True, nullable=False)

    # Media & Display
    img = Column(Text, nullable=True)  # Primary thumbnail / featured image (supports URL or base64 data URL)
    gallery = Column(JSON, default=list, nullable=False)  # List of image URLs
    badge = Column(String(50), nullable=True)  # e.g., "BESTSELLER", "HOT", "SALE", "NEW"
    desc = Column(Text, nullable=True)  # Full description / overview
    details = Column(JSON, default=list, nullable=False)  # Feature bullet points: ["Feature 1", "Feature 2"]

    # Variants / Specifications
    colors = Column(JSON, default=list, nullable=False)  # [{"name": "Space Black", "hex": "#1e1e24"}]
    sizes = Column(JSON, default=list, nullable=False)  # ["512GB", "1TB", "2TB"] or ["S", "M", "L"]

    # Metrics & Flags
    rating = Column(Float, default=0.0, nullable=False)
    reviews_count = Column(Integer, default=0, nullable=False)
    is_popular = Column(Boolean, default=False, nullable=False)
    is_featured = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    # Audit Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    category = relationship("Category", back_populates="products")
    seller = relationship("User")
    reviews = relationship("Review", back_populates="product", cascade="all, delete-orphan", order_by="desc(Review.created_at)")
    variants = relationship("ProductVariant", back_populates="product", cascade="all, delete-orphan")
    images = relationship("ProductImage", back_populates="product", cascade="all, delete-orphan", order_by="ProductImage.display_order")

    @property
    def cat(self) -> str:
        if self.category and self.category.name:
            return self.category.name
        return "Accessories"

    @property
    def discount_percentage(self) -> int:
        if self.old_price and self.old_price > self.price:
            return round(((self.old_price - self.price) / self.old_price) * 100)
        return 0

    def __repr__(self) -> str:
        return f"<Product(id={self.id}, name='{self.name}', price={self.price}, in_stock={self.in_stock})>"


class ProductVariant(Base):
    """
    Specific product SKU variations (e.g. specific Size + Color combinations with individual inventory).
    """
    __tablename__ = "product_variants"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    sku = Column(String(100), unique=True, nullable=True, index=True)
    title = Column(String(150), nullable=False)  # e.g., "Space Black / 1TB"
    color_name = Column(String(50), nullable=True)
    color_hex = Column(String(20), nullable=True)
    size = Column(String(50), nullable=True)
    price_override = Column(Float, nullable=True)
    stock_quantity = Column(Integer, default=0, nullable=False)
    img = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    # Relationship
    product = relationship("Product", back_populates="variants")

    def __repr__(self) -> str:
        return f"<ProductVariant(id={self.id}, product_id={self.product_id}, title='{self.title}')>"


class ProductImage(Base):
    """
    Normalized Product Gallery Images.
    """
    __tablename__ = "product_images"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    image_url = Column(String(500), nullable=False)
    alt_text = Column(String(255), nullable=True)
    is_primary = Column(Boolean, default=False, nullable=False)
    display_order = Column(Integer, default=0, nullable=False)

    # Relationship
    product = relationship("Product", back_populates="images")

    def __repr__(self) -> str:
        return f"<ProductImage(id={self.id}, product_id={self.product_id}, image_url='{self.image_url}')>"


class Review(Base):
    """
    Product Review and Ratings Model.
    """
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    author_name = Column(String(100), nullable=False)
    rating = Column(Float, nullable=False)  # 1.0 - 5.0
    comment = Column(Text, nullable=False)
    is_verified_purchase = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    product = relationship("Product", back_populates="reviews")
    user = relationship("User")

    def __repr__(self) -> str:
        return f"<Review(id={self.id}, product_id={self.product_id}, rating={self.rating}, author='{self.author_name}')>"

