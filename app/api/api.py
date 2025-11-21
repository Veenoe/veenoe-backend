"""
This module defines the main API router for the application.

It aggregates all versioned routers (e.g., v1) into a single
APIRouter, which is then included by the main app.main:app.
"""

from fastapi import APIRouter
from app.api.v1 import viva  # Import the v1 viva router

# Create the main API router instance
api_router = APIRouter()

# Include all v1 routers
# All routes in viva.router will be prefixed with /v1/viva
api_router.include_router(viva.router, prefix="/v1/viva", tags=["viva"])
