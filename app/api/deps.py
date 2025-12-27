"""
This module configures all FastAPI dependency injection bindings
for the application.

It centralizes construction of service instances such as the LLM client
and VivaService, ensuring a clean and testable architecture.

Key Design Principles:
----------------------
1. **Dependency Injection (DI)**
   Services are provided through FastAPI's `Depends()` mechanism,
   which makes route handlers simple, testable, and free of manual wiring.

2. **Singleton LLM Service**
   The LLM provider (GeminiService) is expensive to initialize and
   should not be created per request.
   We use `@lru_cache` to build a process-wide singleton.

3. **Composable Services**
   Higher-level services (e.g., VivaService) receive dependencies
   via constructor injection, aligning with clean architecture
   and promoting loose coupling.
"""

from typing import Annotated
from functools import lru_cache
from fastapi import Depends

from app.interfaces.llm_client import LLMClient
from app.services.gemini_service import GeminiService
from app.services.viva_service import VivaService

# Re-export authentication dependencies for easy import in routes
from app.core.auth import (
    CurrentUser,
    OptionalUser,
    AuthenticatedUser,
    get_current_user,
    get_current_user_optional,
)


# ----------------------------------------------------------------------
# LLM Service Provider
# ----------------------------------------------------------------------
@lru_cache
def get_llm_service() -> LLMClient:
    """
    Construct and return a cached singleton instance of the LLM service.

    FastAPI evaluates dependency providers once per process by using `lru_cache`,
    ensuring:
    - Only one instance of GeminiService is created.
    - Efficient use of resources (e.g., network clients, auth config).
    - Thread-safe reuse across requests.

    Returns:
        LLMClient: A GeminiService instance implementing the LLMClient interface.
    """
    return GeminiService()


# ----------------------------------------------------------------------
# Viva Service Provider
# ----------------------------------------------------------------------
def get_viva_service(
    llm_service: Annotated[LLMClient, Depends(get_llm_service)],
) -> VivaService:
    """
    Construct a VivaService instance with the injected LLM client.

    This function demonstrates constructor-based dependency wiring,
    making VivaService fully testable and independent of concrete LLM providers.

    FastAPI automatically resolves the `llm_service` argument using DI.

    Args:
        llm_service (LLMClient):
            The injected LLM client instance, provided by `get_llm_service`.

    Returns:
        VivaService: The VivaService instance fully wired with dependencies.
    """
    return VivaService(llm_client=llm_service)
