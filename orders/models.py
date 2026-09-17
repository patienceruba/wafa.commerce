import enum
from sqlalchemy import Column, Integer, Float, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from config.database import Base


class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentMethod(str, enum.Enum):
    CREDIT_CARD = "credit_card"
    PAYPAL = "paypal"
    APPLE_PAY = "apple_pay"
    STRIPE = "stripe"
    COD = "cash_on_delivery"


class Order(Base):
    """
    Core E-Commerce Order Model.
    Represents customer orders supporting both authenticated users and guest checkouts,
    address snapshots, financial breakdowns, tracking, and audit statuses.
    """
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    order_number = Column(String(50), unique=True, nullable=False, index=True)  # e.g. "ORD-20260907-8A3F"
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    # Customer Snapshot (at time of order)
    customer_name = Column(String(150), nullable=False)
    customer_email = Column(String(255), nullable=False, index=True)
    customer_phone = Column(String(50), nullable=True)

    # Shipping Address
    shipping_address = Column(String(255), nullable=False)
    shipping_city = Column(String(100), nullable=False)
    shipping_state = Column(String(100), nullable=True)
    shipping_zip = Column(String(30), nullable=False)
    shipping_country = Column(String(100), default="US", nullable=False)

    # Billing Address (Optional / Fallback to Shipping)
    billing_address = Column(String(255), nullable=True)
    billing_city = Column(String(100), nullable=True)
    billing_zip = Column(String(30), nullable=True)

    # Financial Breakdown
    currency = Column(String(10), default="USD", nullable=False)
    subtotal = Column(Float, nullable=False)
    discount = Column(Float, default=0.0, nullable=False)
    coupon_code = Column(String(50), nullable=True)
    shipping_fee = Column(Float, default=0.0, nullable=False)
    tax_amount = Column(Float, default=0.0, nullable=False)
    total = Column(Float, nullable=False)

    # Order & Payment Status
    status = Column(String(30), default=OrderStatus.PENDING.value, nullable=False, index=True)
    payment_status = Column(String(30), default=PaymentStatus.PENDING.value, nullable=False, index=True)
    payment_method = Column(String(50), default=PaymentMethod.CREDIT_CARD.value, nullable=False)
    payment_transaction_id = Column(String(150), nullable=True)

    # Shipping & Tracking
    tracking_number = Column(String(150), nullable=True)
    shipping_carrier = Column(String(100), nullable=True)

    # Notes
    customer_notes = Column(Text, nullable=True)
    admin_notes = Column(Text, nullable=True)

    # Timestamps & Lifecycle Milestones
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    shipped_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    status_history = relationship("OrderStatusHistory", back_populates="order", cascade="all, delete-orphan", order_by="desc(OrderStatusHistory.created_at)")

    @property
    def total_items_count(self) -> int:
        return sum(item.qty for item in self.items) if self.items else 0

    def __repr__(self) -> str:
        return f"<Order(id={self.id}, order_number='{self.order_number}', total={self.total}, status='{self.status}')>"


class OrderItem(Base):
    """
    Individual Line Item within an Order.
    Stores immutable snapshot data of the purchased product to preserve order history accuracy.
    """
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True)

    # Product Snapshot (Preserves pricing & naming even if product is deleted/edited)
    product_name = Column(String(255), nullable=False)
    product_sku = Column(String(100), nullable=True)
    product_img = Column(String(500), nullable=True)
    selected_size = Column(String(50), nullable=True)
    selected_color = Column(String(50), nullable=True)
    unit_price = Column(Float, nullable=False)
    qty = Column(Integer, default=1, nullable=False)
    total_price = Column(Float, nullable=False)

    # Relationships
    order = relationship("Order", back_populates="items")
    product = relationship("Product")

    def __repr__(self) -> str:
        return f"<OrderItem(id={self.id}, order_id={self.order_id}, product='{self.product_name}', qty={self.qty})>"


class OrderStatusHistory(Base):
    """
    Audit log / timeline tracking every status transition of an Order.
    """
    __tablename__ = "order_status_history"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(50), nullable=False)
    comment = Column(Text, nullable=True)
    notify_customer = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationship
    order = relationship("Order", back_populates="status_history")

    def __repr__(self) -> str:
        return f"<OrderStatusHistory(id={self.id}, order_id={self.order_id}, status='{self.status}')>"


class Cart(Base):
    """
    Persistent Shopping Cart for authenticated users or guest session tokens.
    """
    __tablename__ = "carts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, unique=True, index=True)
    session_token = Column(String(255), nullable=True, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    user = relationship("User")
    items = relationship("CartItem", back_populates="cart", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Cart(id={self.id}, user_id={self.user_id})>"


class CartItem(Base):
    """
    Individual items added into a persistent Shopping Cart.
    """
    __tablename__ = "cart_items"

    id = Column(Integer, primary_key=True, index=True)
    cart_id = Column(Integer, ForeignKey("carts.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    selected_size = Column(String(50), nullable=True)
    selected_color = Column(String(50), nullable=True)
    qty = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    cart = relationship("Cart", back_populates="items")
    product = relationship("Product")

    def __repr__(self) -> str:
        return f"<CartItem(id={self.id}, cart_id={self.cart_id}, product_id={self.product_id}, qty={self.qty})>"

