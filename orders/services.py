import uuid
import datetime
from typing import Optional, List, Tuple, Dict
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, desc
from fastapi import HTTPException, status

from orders.models import Order, OrderItem, OrderStatusHistory, Cart, CartItem, OrderStatus, PaymentStatus
from orders.schemas import OrderCreate, OrderUpdate, CartItemCreate, CartItemUpdate, CheckoutPreviewRequest
from products.models import Product
from services.email_service import send_order_confirmation_email


# NOTE: Promo codes are now managed via the promo_codes DB table.
# The COUPONS dict below is the legacy fallback and will be ignored when DB codes exist.


def generate_order_number() -> str:
    """Generate a clean, professional order reference like ORD-20260907-A1B2."""
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d")
    short_id = uuid.uuid4().hex[:6].upper()
    return f"ORD-{today}-{short_id}"


class OrderService:
    def __init__(self, db: Session):
        self.db = db

    def calculate_totals(
        self,
        items_data: List[dict],
        coupon_code: Optional[str] = None,
        shipping_country: str = "US",
    ) -> dict:
        """Calculate subtotal, discounts, shipping, taxes, and grand total."""
        subtotal = 0.0
        validated_items = []

        for item_in in items_data:
            product = self.db.query(Product).filter(Product.id == item_in["product_id"]).first()
            if not product:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Product with ID {item_in['product_id']} not found",
                )
            if not product.in_stock or (product.stock_quantity is not None and product.stock_quantity < item_in["qty"]):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Product '{product.name}' has insufficient stock (available: {product.stock_quantity})",
                )

            line_total = round(product.price * item_in["qty"], 2)
            subtotal += line_total

            validated_items.append({
                "product": product,
                "product_id": product.id,
                "product_name": product.name,
                "product_sku": product.sku,
                "product_img": product.img,
                "selected_size": str(item_in.get("selected_size")) if item_in.get("selected_size") is not None else None,
                "selected_color": item_in.get("selected_color"),
                "unit_price": product.price,
                "qty": item_in["qty"],
                "total_price": line_total,
            })

        subtotal = round(subtotal, 2)
        discount_percentage = 0.0
        discount = 0.0
        applied_coupon = None

        if coupon_code:
            code_upper = coupon_code.strip().upper()
            # Try DB-managed promo codes first
            try:
                from orders.promo_service import PromoCodeService
                promo_svc = PromoCodeService(self.db)
                promo_info = promo_svc.validate(code_upper, cart_subtotal=subtotal)
                if promo_info["discount_type"] == "percentage":
                    discount_percentage = promo_info["discount_value"] / 100.0
                    discount = round(subtotal * discount_percentage, 2)
                else:  # fixed
                    discount = min(round(promo_info["discount_value"], 2), subtotal)
                    discount_percentage = (discount / subtotal) if subtotal > 0 else 0
                applied_coupon = code_upper
            except HTTPException:
                # Code not found in DB — silently ignore (treated as invalid)
                pass

        # Free shipping on orders over $150, else $15 flat
        shipping_fee = 0.0 if (subtotal - discount) >= 150.0 else (15.0 if subtotal > 0 else 0.0)
        
        # 5% estimated tax
        tax_amount = round((subtotal - discount) * 0.05, 2) if (subtotal - discount) > 0 else 0.0
        total = round(max(0.0, (subtotal - discount) + shipping_fee + tax_amount), 2)

        return {
            "subtotal": subtotal,
            "discount": discount,
            "discount_percentage": discount_percentage * 100,
            "applied_coupon": applied_coupon,
            "shipping_fee": shipping_fee,
            "tax_amount": tax_amount,
            "total": total,
            "items": validated_items,
        }

    def preview_checkout(self, request: CheckoutPreviewRequest) -> dict:
        """Preview checkout totals without creating an order."""
        items_payload = [item.model_dump() for item in request.items]
        calc = self.calculate_totals(
            items_data=items_payload,
            coupon_code=request.coupon_code,
            shipping_country=request.shipping_country,
        )
        return {
            "subtotal": calc["subtotal"],
            "discount": calc["discount"],
            "discount_percentage": calc["discount_percentage"],
            "shipping_fee": calc["shipping_fee"],
            "tax_amount": calc["tax_amount"],
            "total": calc["total"],
            "applied_coupon": calc["applied_coupon"],
        }

    def create_order(self, order_data: OrderCreate, user_id: Optional[int] = None) -> Order:
        """Create a full Order with snapshot items, inventory reduction, and audit log."""
        items_payload = [item.model_dump() for item in order_data.items]
        calc = self.calculate_totals(
            items_data=items_payload,
            coupon_code=order_data.coupon_code,
            shipping_country=order_data.shipping_country,
        )

        order_number = generate_order_number()

        order = Order(
            order_number=order_number,
            user_id=user_id,
            customer_name=order_data.customer_name,
            customer_email=order_data.customer_email,
            customer_phone=order_data.customer_phone,
            shipping_address=order_data.shipping_address,
            shipping_city=order_data.shipping_city,
            shipping_state=order_data.shipping_state,
            shipping_zip=order_data.shipping_zip,
            shipping_country=order_data.shipping_country,
            billing_address=order_data.billing_address or order_data.shipping_address,
            billing_city=order_data.billing_city or order_data.shipping_city,
            billing_zip=order_data.billing_zip or order_data.shipping_zip,
            currency="USD",
            subtotal=calc["subtotal"],
            discount=calc["discount"],
            coupon_code=calc["applied_coupon"],
            shipping_fee=calc["shipping_fee"],
            tax_amount=calc["tax_amount"],
            total=calc["total"],
            payment_method=order_data.payment_method,
            status=OrderStatus.PENDING.value,
            payment_status=PaymentStatus.PENDING.value,
            customer_notes=order_data.customer_notes,
        )
        self.db.add(order)
        self.db.flush()

        # Create Line Items & Reduce Inventory
        for v_item in calc["items"]:
            item_row = OrderItem(
                order_id=order.id,
                product_id=v_item["product_id"],
                product_name=v_item["product_name"],
                product_sku=v_item["product_sku"],
                product_img=v_item["product_img"],
                selected_size=v_item["selected_size"],
                selected_color=v_item["selected_color"],
                unit_price=v_item["unit_price"],
                qty=v_item["qty"],
                total_price=v_item["total_price"],
            )
            self.db.add(item_row)

            # Deduct inventory
            product = v_item["product"]
            if product.stock_quantity is not None:
                product.stock_quantity -= v_item["qty"]
                if product.stock_quantity <= 0:
                    product.stock_quantity = 0
                    product.in_stock = False

        # Add initial audit history
        history = OrderStatusHistory(
            order_id=order.id,
            status=OrderStatus.PENDING.value,
            comment="Order received and awaiting payment processing",
            notify_customer=True,
        )
        self.db.add(history)

        self.db.commit()
        self.db.refresh(order)

        # Dispatch order confirmation email
        try:
            if order.customer_email:
                send_order_confirmation_email(
                    to_email=order.customer_email,
                    order_number=order.order_number,
                    total_amount=order.total,
                    customer_name=order.customer_name or "Valued Customer"
                )
        except Exception as mail_err:
            print(f"[ORDER EMAIL ERROR] Failed to send order email: {mail_err}")

        return order

    def get_orders(
        self,
        user_id: Optional[int] = None,
        status_filter: Optional[str] = None,
        payment_status_filter: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Order], int]:
        """Fetch orders list with filtering and pagination."""
        query = self.db.query(Order)

        if user_id:
            query = query.filter(Order.user_id == user_id)
        if status_filter:
            query = query.filter(Order.status == status_filter)
        if payment_status_filter:
            query = query.filter(Order.payment_status == payment_status_filter)
        if search:
            pattern = f"%{search.lower()}%"
            query = query.filter(
                (Order.order_number.ilike(pattern))
                | (Order.customer_name.ilike(pattern))
                | (Order.customer_email.ilike(pattern))
            )

        total = query.count()
        items = query.order_by(desc(Order.created_at)).offset((page - 1) * page_size).limit(page_size).all()
        return items, total

    def get_by_id_or_number(self, identifier: str, user_id: Optional[int] = None) -> Optional[Order]:
        """Fetch full order details by ID or unique order number."""
        query = (
            self.db.query(Order)
            .options(
                joinedload(Order.items),
                joinedload(Order.status_history),
            )
        )
        if identifier.isdigit():
            query = query.filter(Order.id == int(identifier))
        else:
            query = query.filter(Order.order_number == identifier)

        if user_id is not None:
            query = query.filter(Order.user_id == user_id)

        return query.first()

    def update_order(self, order_id: int, data: OrderUpdate) -> Order:
        """Update order details, status lifecycle, and record history."""
        order = self.db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

        update_dict = data.model_dump(exclude_unset=True)
        status_comment = update_dict.pop("status_comment", None)
        new_status = update_dict.get("status")
        now = datetime.datetime.now(datetime.timezone.utc)

        # Status transition handling
        if new_status and new_status != order.status:
            order.status = new_status
            if new_status == OrderStatus.CONFIRMED.value and not order.paid_at:
                order.paid_at = now
                order.payment_status = PaymentStatus.PAID.value
            elif new_status == OrderStatus.SHIPPED.value:
                order.shipped_at = now
            elif new_status == OrderStatus.DELIVERED.value:
                order.delivered_at = now
            elif new_status == OrderStatus.CANCELLED.value:
                order.cancelled_at = now
                # Restore product stock
                for item in order.items:
                    if item.product:
                        item.product.stock_quantity += item.qty
                        item.product.in_stock = True

            # Record history
            history = OrderStatusHistory(
                order_id=order.id,
                status=new_status,
                comment=status_comment or f"Status changed to {new_status}",
                notify_customer=True,
            )
            self.db.add(history)

        for key, value in update_dict.items():
            setattr(order, key, value)

        self.db.commit()
        self.db.refresh(order)
        return order


class CartService:
    def __init__(self, db: Session):
        self.db = db

    def get_or_create_cart(self, user_id: Optional[int] = None, session_token: Optional[str] = None) -> Cart:
        """Retrieve existing shopping cart or initialize a new one."""
        query = self.db.query(Cart).options(joinedload(Cart.items).joinedload(CartItem.product))

        if user_id:
            cart = query.filter(Cart.user_id == user_id).first()
        elif session_token:
            cart = query.filter(Cart.session_token == session_token).first()
        else:
            cart = None

        if not cart:
            cart = Cart(
                user_id=user_id,
                session_token=session_token or (uuid.uuid4().hex if not user_id else None),
            )
            self.db.add(cart)
            self.db.commit()
            self.db.refresh(cart)
        return cart

    def get_cart_response(self, user_id: Optional[int] = None, session_token: Optional[str] = None) -> dict:
        """Get formatted cart with item details and subtotal."""
        cart = self.get_or_create_cart(user_id=user_id, session_token=session_token)
        items_response = []
        subtotal = 0.0
        total_items = 0

        for item in cart.items:
            prod_price = item.product.price if item.product else 0.0
            line_subtotal = round(prod_price * item.qty, 2)
            subtotal += line_subtotal
            total_items += item.qty

            items_response.append({
                "id": item.id,
                "cart_id": item.cart_id,
                "product_id": item.product_id,
                "selected_size": item.selected_size,
                "selected_color": item.selected_color,
                "qty": item.qty,
                "product_name": item.product.name if item.product else "Unknown",
                "product_price": prod_price,
                "product_img": item.product.img if item.product else None,
                "subtotal": line_subtotal,
            })

        return {
            "id": cart.id,
            "user_id": cart.user_id,
            "session_token": cart.session_token,
            "items": items_response,
            "total_items": total_items,
            "subtotal": round(subtotal, 2),
        }

    def add_to_cart(self, item_data: CartItemCreate, user_id: Optional[int] = None, session_token: Optional[str] = None) -> dict:
        """Add item to cart or increment qty if existing, respecting stock limits."""
        product = self.db.query(Product).filter(Product.id == item_data.product_id).first()
        if not product:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

        if not product.in_stock or (product.stock_quantity is not None and product.stock_quantity <= 0):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Product '{product.name}' is currently out of stock.",
            )

        cart = self.get_or_create_cart(user_id=user_id, session_token=session_token)
        
        # Check if item with same product, size, and color already exists
        existing_item = (
            self.db.query(CartItem)
            .filter(
                CartItem.cart_id == cart.id,
                CartItem.product_id == item_data.product_id,
                CartItem.selected_size == str(item_data.selected_size) if item_data.selected_size is not None else None,
                CartItem.selected_color == item_data.selected_color,
            )
            .first()
        )

        current_qty = existing_item.qty if existing_item else 0
        new_total_qty = current_qty + item_data.qty

        if product.stock_quantity is not None and new_total_qty > product.stock_quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot add {item_data.qty} items. Only {product.stock_quantity} available in stock (already {current_qty} in your cart).",
            )

        if existing_item:
            existing_item.qty = new_total_qty
        else:
            new_item = CartItem(
                cart_id=cart.id,
                product_id=item_data.product_id,
                selected_size=str(item_data.selected_size) if item_data.selected_size is not None else None,
                selected_color=item_data.selected_color,
                qty=item_data.qty,
            )
            self.db.add(new_item)

        self.db.commit()
        return self.get_cart_response(user_id=user_id, session_token=session_token)

    def update_item_qty(self, item_id: int, qty: int, user_id: Optional[int] = None, session_token: Optional[str] = None) -> dict:
        """Update specific cart item quantity with stock validation."""
        cart = self.get_or_create_cart(user_id=user_id, session_token=session_token)
        item = self.db.query(CartItem).filter(CartItem.id == item_id, CartItem.cart_id == cart.id).first()
        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found")

        if qty <= 0:
            return self.remove_item(item_id, user_id=user_id, session_token=session_token)

        product = item.product or self.db.query(Product).filter(Product.id == item.product_id).first()
        if product and product.stock_quantity is not None and qty > product.stock_quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot set quantity to {qty}. Only {product.stock_quantity} available in stock for '{product.name}'.",
            )

        item.qty = qty
        self.db.commit()
        return self.get_cart_response(user_id=user_id, session_token=session_token)

    def remove_item(self, item_id: int, user_id: Optional[int] = None, session_token: Optional[str] = None) -> dict:
        """Remove item from cart."""
        cart = self.get_or_create_cart(user_id=user_id, session_token=session_token)
        item = self.db.query(CartItem).filter(CartItem.id == item_id, CartItem.cart_id == cart.id).first()
        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found")

        self.db.delete(item)
        self.db.commit()
        return self.get_cart_response(user_id=user_id, session_token=session_token)

    def clear_cart(self, user_id: Optional[int] = None, session_token: Optional[str] = None) -> dict:
        """Clear all items in cart."""
        cart = self.get_or_create_cart(user_id=user_id, session_token=session_token)
        self.db.query(CartItem).filter(CartItem.cart_id == cart.id).delete()
        self.db.commit()
        return self.get_cart_response(user_id=user_id, session_token=session_token)
