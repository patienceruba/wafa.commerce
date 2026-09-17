from fastapi import FastAPI, Request, Response
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
origins = [
    "https://wafa-commerce-frontend.vercel.app",
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"^https?:\/\/.*$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


@app.middleware("http")
async def ensure_cors_headers(request: Request, call_next):
    origin = request.headers.get("origin")
    if request.method == "OPTIONS":
        response = Response(status_code=204)
    else:
        response = await call_next(request)

    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH, HEAD"
        response.headers["Access-Control-Allow-Headers"] = "*"
        response.headers["Access-Control-Expose-Headers"] = "*"

    return response

# Include Routers
app.include_router(auth_router)
app.include_router(products_router)
app.include_router(orders_router)
app.include_router(admin_router)
app.include_router(seller_router)
app.include_router(assistant_router)




from fastapi.responses import Response, JSONResponse

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    origin = request.headers.get("origin")
    headers = {
        "Access-Control-Allow-Origin": origin or "*",
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH, HEAD",
        "Access-Control-Allow-Headers": "*",
    } if origin else {}
    return JSONResponse(
        status_code=500,
        content={"detail": f"Server Error: {str(exc)}"},
        headers=headers,
    )

@app.api_route("/", methods=["GET", "POST", "HEAD", "OPTIONS", "PUT", "DELETE"], tags=["health"])
@app.api_route("", methods=["GET", "POST", "HEAD", "OPTIONS", "PUT", "DELETE"], tags=["health"], include_in_schema=False)
def health_check():
    return {
        "status": "healthy",
        "service": "Wafa E-Commerce API",
        "version": "1.0.0",
    }

@app.api_route("/favicon.ico", methods=["GET", "HEAD", "OPTIONS"], include_in_schema=False)
def favicon():
    return Response(status_code=204)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
