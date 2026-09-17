from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional, List

from config.database import get_db
from users.routers import get_current_user
from users.models import User
from products.schemas import ProductResponse, ProductCreate, ProductUpdate
from sellers.services import SellerService

router = APIRouter(prefix="/seller", tags=["seller"])


def get_seller_service(db: Session = Depends(get_db)) -> SellerService:
    return SellerService(db)


def require_seller_user(current_user: User = Depends(get_current_user)) -> User:
    """Ensure user is a verified seller or admin."""
    if not (current_user.is_seller or current_user.is_admin or current_user.role in ["seller", "admin", "owner"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verified seller privileges required to access this portal",
        )
    return current_user


@router.get("/dashboard")
def get_seller_dashboard(
    current_user: User = Depends(require_seller_user),
    seller_service: SellerService = Depends(get_seller_service),
):
    """Fetch seller overview, net volume, products summary, and ratings."""
    return seller_service.get_seller_dashboard(current_user.id)


@router.get("/products", response_model=List[ProductResponse])
def get_seller_products(
    search: Optional[str] = None,
    current_user: User = Depends(require_seller_user),
    seller_service: SellerService = Depends(get_seller_service),
):
    """List all products belonging to the authenticated merchant."""
    return seller_service.get_seller_products(current_user.id, search=search)


@router.post("/products", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_seller_product(
    product_data: ProductCreate,
    current_user: User = Depends(require_seller_user),
    seller_service: SellerService = Depends(get_seller_service),
):
    """List a new product in the store catalog under the seller's account."""
    return seller_service.create_seller_product(current_user.id, product_data)


@router.put("/products/{product_id}", response_model=ProductResponse)
def update_seller_product(
    product_id: int,
    product_data: ProductUpdate,
    current_user: User = Depends(require_seller_user),
    seller_service: SellerService = Depends(get_seller_service),
):
    """Update seller product details, pricing, or inventory quantity."""
    return seller_service.update_seller_product(current_user.id, product_id, product_data)


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_seller_product(
    product_id: int,
    current_user: User = Depends(require_seller_user),
    seller_service: SellerService = Depends(get_seller_service),
):
    """Remove a product listing from the marketplace."""
    seller_service.delete_seller_product(current_user.id, product_id)
    return None
