"""
This module is the main entry point for the AI Viva SaaS backend application.
It initializes the FastAPI application, sets up the application lifespan
(including database initialization), and includes the main API router.

Design Decisions (First Principles):
1. Rate Limiting: Protect against abuse and Gemini API quota exhaustion
2. Proper Lifecycle: Database init/close for resource management
3. Centralized CORS: All origins configurable via environment
"""

import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from app.db.database import init_db, close_db, verify_connection
from app.api.api import api_router
from app.core.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate Limiting Configuration
# ---------------------------------------------------------------------------
# Uses client IP for rate limiting. In production behind a proxy,
# configure X-Forwarded-For header parsing appropriately.
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Asynchronous context manager for the application's lifespan.
    This function is executed when the application starts up and shuts down.
    It's used to initialize resources like the database connection.

    Args:
        app (FastAPI): The FastAPI application instance.
    """
    logger.info("Application starting up...")
    await init_db()  # Initialize the database connection and models
    yield
    logger.info("Application shutting down...")
    await close_db()  # Gracefully close database connection


# Create the main FastAPI application instance
app = FastAPI(
    title="AI Viva SaaS Backend",
    description="Manages AI-powered oral exams (vivas). Integrates with Google Gemini Live API.",
    version="1.0.0",
    lifespan=lifespan,
)

# Attach rate limiter to app state (required by SlowAPI)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Define allowed origins for CORS
# Base origins for local development
origins = [
    "http://localhost:3000",  # React default
    "http://localhost:5173",  # Vite default
    "http://localhost:8080",  # Alternative frontend port
]

# Add production origins from settings
if settings.FRONTEND_URL:
    origins.append(settings.FRONTEND_URL)

# Add additional configured origins
if settings.CORS_ORIGINS:
    origins.extend(settings.CORS_ORIGINS)

# Add CORS middleware to allow frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
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
    Production-ready health check endpoint.

    Verifies database connectivity to provide accurate health status.
    Returns 503 Service Unavailable if database is unreachable.
    """
    db_healthy = await verify_connection()

    if db_healthy:
        return {"status": "healthy", "database": "connected"}

    # Return 503 for unhealthy state so load balancers can respond appropriately
    return JSONResponse(
        status_code=503,
        content={
            "status": "unhealthy",
            "database": "disconnected",
            "message": "Database connection failed",
        },
    )
