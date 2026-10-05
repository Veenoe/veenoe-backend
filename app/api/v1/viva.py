"""Authenticated session endpoints; storage errors never expose AWS responses."""

import logging
from collections.abc import Awaitable
from typing import Annotated, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.api.deps import CurrentUser, get_viva_service
from app.db.models import SESSION_ID_PATTERN
from app.db.session_repository import (
    RepositoryUnavailable,
    SessionConflict,
    SessionNotFound,
    SessionTooLarge,
)
from app.schemas.viva import (
    ConcludeVivaRequest,
    ConcludeVivaResponse,
    HistoryResponse,
    RenameSessionRequest,
    VivaSessionDetailResponse,
    VivaStartRequest,
    VivaStartResponse,
)
from app.services.viva_service import VivaService

logger = logging.getLogger(__name__)
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)
Service = Annotated[VivaService, Depends(get_viva_service)]
SessionIdPath = Annotated[str, Path(pattern=SESSION_ID_PATTERN, max_length=53)]
T = TypeVar("T")


async def _run(operation: Awaitable[T], event: str, failure: str) -> T:
    """Translate domain errors consistently without logging tokens or session text.

    Missing and foreign sessions share 404. Conflicts require refreshing state;
    unavailable storage is retryable, but retries do not bypass write conditions.
    """
    try:
        return await operation
    except SessionNotFound:
        raise HTTPException(404, "Session not found") from None
    except SessionConflict:
        raise HTTPException(
            409, "Session changed or is no longer active. Refresh and retry."
        ) from None
    except SessionTooLarge:
        raise HTTPException(413, "Session data exceeds the supported size.") from None
    except RepositoryUnavailable:
        logger.error("event=%s error_type=RepositoryUnavailable", event)
        raise HTTPException(
            503, "Session storage is temporarily unavailable. Please retry."
        ) from None
    except PermissionError:
        raise HTTPException(
            403, "You do not have permission to modify this session"
        ) from None
    except Exception as error:
        logger.error("event=%s error_type=%s", event, type(error).__name__)
        raise HTTPException(500, failure) from None


@router.post("/start", response_model=VivaStartResponse)
@limiter.limit("5/minute")
async def start_viva(
    request: Request,
    viva_request: VivaStartRequest,
    service: Service,
    current_user: CurrentUser,
):
    return await _run(
        service.start_new_viva_session(
            viva_request=viva_request, user_id=current_user.user_id
        ),
        "viva_start_failed",
        "Failed to start session. Please try again.",
    )


@router.post("/conclude-viva", response_model=ConcludeVivaResponse)
async def conclude_viva(
    request: ConcludeVivaRequest, service: Service, current_user: CurrentUser
):
    return await _run(
        service.conclude_viva_session(
            **request.model_dump(), user_id=current_user.user_id
        ),
        "viva_conclude_failed",
        "Failed to conclude session. Please try again.",
    )


@router.get("/history", response_model=HistoryResponse)
async def get_history(
    service: Service,
    current_user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    cursor: Annotated[
        str | None, Query(pattern=SESSION_ID_PATTERN, max_length=53)
    ] = None,
):
    return await _run(
        service.get_user_history(current_user.user_id, limit, cursor),
        "viva_history_failed",
        "Failed to fetch history. Please try again.",
    )


@router.post("/{session_id}/abandon")
async def abandon_session(
    session_id: SessionIdPath, service: Service, current_user: CurrentUser
):
    return await _run(
        service.abandon_viva_session(session_id, current_user.user_id),
        "viva_abandon_failed",
        "Failed to end session. Please try again.",
    )


@router.get("/{session_id}", response_model=VivaSessionDetailResponse)
async def get_session_details(
    session_id: SessionIdPath, service: Service, current_user: CurrentUser
):
    return await _run(
        service.get_viva_session_details(session_id, current_user.user_id),
        "viva_details_failed",
        "Failed to fetch session details. Please try again.",
    )


@router.patch("/{session_id}/rename")
async def rename_session_endpoint(
    session_id: SessionIdPath,
    request: RenameSessionRequest,
    service: Service,
    current_user: CurrentUser,
):
    return await _run(
        service.rename_session(
            session_id=session_id,
            new_title=request.new_title,
            user_id=current_user.user_id,
        ),
        "viva_rename_failed",
        "Failed to rename session. Please try again.",
    )


@router.delete("/{session_id}")
async def delete_session_endpoint(
    session_id: SessionIdPath, service: Service, current_user: CurrentUser
):
    return await _run(
        service.delete_session(session_id=session_id, user_id=current_user.user_id),
        "viva_delete_failed",
        "Failed to delete session. Please try again.",
    )
