"""
Reftool Router - Optimized read-only endpoints for referee scheduling UX

Provides three endpoints designed for day-view and sidepanel UI patterns,
replacing the heavy all-referees pattern in /assignments/matches/{match_id}.
"""

from datetime import date

from fastapi import APIRouter, Depends, Query, Request

from authentication import AuthHandler, TokenPayload
from exceptions import AuthorizationException, ValidationException
from models.responses import StandardResponse
from services.assignment_service import AssignmentService

router = APIRouter()
auth = AuthHandler()

MAX_DATE_RANGE_DAYS = 30


def get_assignment_service(request: Request) -> AssignmentService:
    return AssignmentService(request.app.state.mongodb)


def _require_reftool_role(token_payload: TokenPayload) -> None:
    allowed = {"ADMIN", "REF_ADMIN", "REFEREE"}
    if not any(role in allowed for role in token_payload.roles):
        raise AuthorizationException(
            message="ADMIN, REF_ADMIN, or REFEREE role required",
            details={"user_roles": token_payload.roles},
        )


def _parse_date(value: str, field_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValidationException(
            field=field_name,
            message=f"Invalid date format '{value}'. Expected YYYY-MM-DD.",
        )


@router.get(
    "/matches",
    response_description="Matches grouped by date with lightweight refSummary aggregations",
)
async def get_matches_with_ref_summary(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
    assignment_service: AssignmentService = Depends(get_assignment_service),
) -> StandardResponse:
    _require_reftool_role(token_payload)

    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date")

    if (end - start).days >= MAX_DATE_RANGE_DAYS:
        raise ValidationException(
            field="end_date",
            message=f"Date range must not exceed {MAX_DATE_RANGE_DAYS} days.",
            details={"start_date": start_date, "end_date": end_date},
        )

    data = await assignment_service.get_matches_by_day_range(start, end)

    return StandardResponse(
        success=True,
        data=data,
        message="Matches retrieved successfully",
    )


@router.get(
    "/matches/{match_id}",
    response_description="Sidepanel data: assigned, requested, and available referee lists",
)
async def get_match_referee_options(
    match_id: str,
    scope: str | None = Query(None, description="Optional club-ID scope filter for available referees"),
    levelFilter: str | None = Query(None, description="Optional referee level filter (e.g. S1, S2)"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
    assignment_service: AssignmentService = Depends(get_assignment_service),
) -> StandardResponse:
    _require_reftool_role(token_payload)

    data = await assignment_service.get_referee_options_for_match(
        match_id=match_id,
        scope=scope,
        level_filter=levelFilter,
    )

    return StandardResponse(
        success=True,
        data=data,
        message="Referee options retrieved successfully",
    )


@router.get(
    "/day-strip",
    response_description="Per-day totals for navigation tiles",
)
async def get_day_strip(
    year: int = Query(..., description="Calendar year (e.g., 2026)"),
    month: int = Query(..., description="Calendar month (1-12)"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
    assignment_service: AssignmentService = Depends(get_assignment_service),
) -> StandardResponse:
    _require_reftool_role(token_payload)

    if month < 1 or month > 12:
        raise ValidationException(
            field="month",
            message="'month' must be between 1 and 12.",
            details={"month": month},
        )

    summaries = await assignment_service.get_day_summaries(year=year, month=month)

    return StandardResponse(
        success=True,
        data=summaries,
        message="Day summaries retrieved successfully",
    )
