"""
This module is the main entry point for the AI Viva SaaS backend application.
It initializes the FastAPI application, sets up the application lifespan
(including database initialization), and includes the main API router.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.db.database import init_db
from app.api.api import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Asynchronous context manager for the application's lifespan.
    This function is executed when the application starts up and shuts down.
    It's used to initialize resources like the database connection.
    
    Args:
        app (FastAPI): The FastAPI application instance.
    """
    print("Application starting up...")
    await init_db()  # Initialize the database connection and models
    yield
    print("Application shutting down...")


# Create the main FastAPI application instance
app = FastAPI(
    title="AI Viva SaaS Backend",
    description="Manages AI-powered oral exams (vivas). Integrates with Google Gemini Live API.",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware to allow frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # React default
        "http://localhost:5173",  # Vite default
        "http://localhost:8080",  # Alternative frontend port
        # Add your production frontend URL here
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include the main API router
app.include_router(api_router, prefix="/api")


@app.get("/")
async def root():
    """
    Root endpoint for health check.
    """
    return {
        "message": "AI Viva SaaS Backend is running",
        "version": "1.0.0",
        "status": "healthy",
    }


@app.get("/health")
async def health_check():
    """
    Health check endpoint.
    """
    return {"status": "healthy"}