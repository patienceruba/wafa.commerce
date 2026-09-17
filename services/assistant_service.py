import re
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_, desc, asc

from products.models import Product, Category, Review
from orders.models import Order, OrderItem
from users.models import User


class AssistantService:
    def __init__(self, db: Session):
        self.db = db

    def process_query(self, query_text: str, user_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Intelligently parses user query, checks live PostgreSQL database,
        and generates context-rich responses with live product cards & order statuses.
        """
        q = query_text.strip()
        q_lower = q.lower()

        # 1. Check for Order Lookup (e.g. ORD-20260907-A1B2 or WAFA-123456 or #123)
        order_match = re.search(r"(ORD-[A-Z0-9-]+|WAFA-[A-Z0-9-]+|\bORD\b|\border\b|\btrack\b)", q, re.IGNORECASE)
        found_order_code = re.search(r"(ORD-[A-Z0-9-]+|WAFA-[0-9]+)", q, re.IGNORECASE)

        if found_order_code:
            order_code = found_order_code.group(1).upper()
            order = (
                self.db.query(Order)
                .options(joinedload(Order.items))
                .filter(func.upper(Order.order_number) == order_code)
                .first()
            )
            if order:
                items_summary = ", ".join([f"{item.qty}x {item.product_name}" for item in order.items])
                tracking_info = f"Tracking: **{order.shipping_carrier or 'Courier'} ({order.tracking_number})**" if order.tracking_number else "Tracking number will be assigned upon dispatch."
                return {
                    "reply": (
                        f"📦 **Order Status Found: {order.order_number}**\n\n"
                        f"- **Status:** `{order.status.upper()}`\n"
                        f"- **Customer:** {order.customer_name} ({order.customer_email})\n"
                        f"- **Total Amount:** **${order.total:.2f}** ({order.payment_status.upper()})\n"
                        f"- **Items:** {items_summary}\n"
                        f"- **Logistics:** {tracking_info}\n\n"
                        f"Need anything else regarding this shipment?"
                    ),
                    "order": {
                        "id": order.id,
                        "order_number": order.order_number,
                        "status": order.status,
                        "total": order.total,
                        "tracking_number": order.tracking_number,
                        "shipping_carrier": order.shipping_carrier,
                    },
                    "products": [],
                    "suggestions": ["🚚 Delivery Timeframes", "🎟️ Available Coupons", "🛍️ Browse Catalog"]
                }
            else:
                return {
                    "reply": f"🔍 I couldn't find an order with reference code **{order_code}** in our database. Please double-check your order number or contact support.",
                    "products": [],
                    "suggestions": ["📦 Track another order", "💬 Contact Support", "🛍️ View Shop"]
                }

        # 2. Check for Category List queries
        if any(w in q_lower for w in ["what categories", "list categories", "all categories", "what do you sell", "show categories"]):
            categories = self.db.query(Category).filter(Category.is_active == True).all()
            cat_names = [c.name for c in categories]
            cat_list_str = " • ".join([f"**{name}**" for name in cat_names]) if cat_names else "**Smartphones**, **Laptops**, **Audio**, **Gaming**, **Wearables**, **Accessories**"
            return {
                "reply": f"🏪 **Our Current Product Catalog Categories:**\n\n{cat_list_str}\n\nAsk me about any specific hardware, price budget, or stock availability!",
                "products": [],
                "suggestions": ["💻 Show Laptops", "🎧 Show Audio Gear", "📱 Show Smartphones", "🎟️ View Coupons"]
            }

        # 3. Check for Policy / Coupons / Shipping queries
        if any(w in q_lower for w in ["coupon", "discount", "promo", "voucher", "code"]):
            return {
                "reply": (
                    "🎟️ **Active Store Promotional Discounts:**\n\n"
                    "- **`WAFA20`** / **`TECH20`** — **20% OFF** sitewide on all tech orders.\n"
                    "- **`WELCOME10`** — **10% OFF** for first-time customers.\n"
                    "- **`VIP50`** — **50% OFF** exclusive VIP privileges.\n\n"
                    "You can enter these codes directly in your shopping bag or during checkout!"
                ),
                "products": [],
                "suggestions": ["🛍️ Explore Products", "🚚 Free Shipping Threshold", "💎 VIP Membership"]
            }

        if any(w in q_lower for w in ["shipping", "delivery", "dispatch", "how long", "courier"]):
            return {
                "reply": (
                    "🚚 **Shipping & Logistics Policy:**\n\n"
                    "- **FREE Express Shipping** on all orders over **$99** ($15 flat rate otherwise).\n"
                    "- **Delivery Speed:** 2 to 3 business days via tracked FedEx / DHL Express.\n"
                    "- **Tracking:** Full real-time milestone tracking included with every dispatch."
                ),
                "products": [],
                "suggestions": ["🛡️ Warranty Info", "📦 Track My Order", "🎟️ Promo Codes"]
            }

        if any(w in q_lower for w in ["warranty", "guarantee", "return", "refund"]):
            return {
                "reply": (
                    "🛡️ **Warranty & Satisfaction Guarantee:**\n\n"
                    "- **2-Year Official Manufacturer Warranty** included with all tech hardware.\n"
                    "- **30-Day Money Back Guarantee** for full refund or instant unit exchange.\n"
                    "- 24/7 dedicated hardware replacement support."
                ),
                "products": [],
                "suggestions": ["🛍️ Shop with Confidence", "🚚 Shipping Details", "🎟️ Get Discount"]
            }

        # 4. Search Products in PostgreSQL Database
        products_query = self.db.query(Product).filter(Product.is_active == True)

        # Price constraints (e.g. "under 500", "under $1000", "less than 700")
        price_match = re.search(r"(?:under|below|less than|\<)\s*\$?(\d+)", q_lower)
        if price_match:
            max_p = float(price_match.group(1))
            products_query = products_query.filter(Product.price <= max_p)

        # Popular / Featured / Best Rating queries
        if any(w in q_lower for w in ["best", "top", "highest", "popular", "recommended", "favorite"]):
            products_query = products_query.order_by(desc(Product.rating), desc(Product.reviews_count))
        elif "cheap" in q_lower or "lowest price" in q_lower or "affordable" in q_lower:
            products_query = products_query.order_by(asc(Product.price))
        elif "expensive" in q_lower or "flagship" in q_lower or "premium" in q_lower:
            products_query = products_query.order_by(desc(Product.price))
        else:
            products_query = products_query.order_by(desc(Product.created_at))

        # Check keyword matches in Name, Brand, Category, Details
        search_words = [w for w in re.findall(r"\w+", q_lower) if len(w) > 2 and w not in ["the", "and", "for", "with", "show", "have", "you", "what", "how", "much", "tell", "about", "product", "products", "item", "items"]]

        if search_words:
            conditions = []
            for word in search_words:
                pattern = f"%{word}%"
                conditions.append(func.lower(Product.name).like(pattern))
                conditions.append(func.lower(Product.desc).like(pattern))
                conditions.append(func.lower(Product.brand).like(pattern))
            products_query = products_query.filter(or_(*conditions))

        matching_products = products_query.limit(4).all()

        # If no strict keyword match, fetch all active store products to answer reliably
        if not matching_products:
            matching_products = self.db.query(Product).filter(Product.is_active == True).order_by(desc(Product.rating)).limit(4).all()

        # Build detailed product summaries with live database stocks and prices
        if matching_products:
            prod_summaries = []
            structured_products = []

            for p in matching_products:
                in_stock_text = f"**{p.stock_quantity} units available**" if (p.in_stock and p.stock_quantity > 0) else "❌ **Currently Out of Stock**"
                prod_summaries.append(
                    f"• **{p.name}** — **${p.price:.2f}** (★ {p.rating} | {in_stock_text})\n  _{p.desc[:110]}..._"
                )
                structured_products.append({
                    "id": p.id,
                    "name": p.name,
                    "price": p.price,
                    "oldPrice": p.old_price or p.price,
                    "rating": p.rating,
                    "reviewsCount": p.reviews_count,
                    "img": p.img,
                    "cat": p.category.name if p.category else "Hardware",
                    "inStock": p.in_stock and (p.stock_quantity > 0),
                    "stock_quantity": p.stock_quantity,
                })

            reply_text = (
                f"⚡ **Live Database Results ({len(matching_products)} item{'s' if len(matching_products) > 1 else ''}):**\n\n"
                + "\n\n".join(prod_summaries)
                + "\n\nClick any item below to view full specifications or add to cart!"
            )

            return {
                "reply": reply_text,
                "products": structured_products,
                "suggestions": [
                    f"Check stock for {matching_products[0].name.split()[0]}",
                    "🎟️ Use 20% Discount",
                    "🚚 Shipping Info"
                ]
            }

        return {
            "reply": "I checked our live product catalog, but couldn't find any products matching that description. Feel free to explore our categories or ask for recommendations!",
            "products": [],
            "suggestions": ["📱 Smartphones", "💻 Laptops", "🎧 Audio Gear", "🎟️ Promo Codes"]
        }
