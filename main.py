from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.database import Base, engine
import users.models
import products.models
import orders.models
import orders.promo_models

from users.routers import router as auth_router
from products.routers import router as products_router
from orders.routers import router as orders_router
from admin.routers import router as admin_router
from sellers.routers import router as seller_router
from assistant.routers import router as assistant_router

# Create database tables automatically
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Wafa E-Commerce API",
    description="Modern High-Performance E-Commerce REST API powered by FastAPI & SQLAlchemy",
    version="1.0.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(auth_router)
app.include_router(products_router)
app.include_router(orders_router)
app.include_router(admin_router)
app.include_router(seller_router)
app.include_router(assistant_router)




@app.get("/", tags=["health"])
def health_check():
    return {
        "status": "healthy",
        "service": "Wafa E-Commerce API",
        "version": "1.0.0",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
