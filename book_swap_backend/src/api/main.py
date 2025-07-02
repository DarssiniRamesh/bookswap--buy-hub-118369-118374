from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import router

app = FastAPI(
    title="Book Swap Marketplace Backend",
    description="API for user authentication, book listings, and transactions.",
    version="1.0.0",
    openapi_tags=[
        {"name": "Authentication", "description": "User registration, login, profile management."},
        {"name": "Books", "description": "Book listing, CRUD, and details."},
        {"name": "Transactions", "description": "Buying, swapping, and transaction history."},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adapt in production to specific frontend host(s)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

@app.get("/")
def health_check():
    """PUBLIC_INTERFACE: Health check endpoint for the Book Swap backend."""
    return {"message": "Healthy"}
