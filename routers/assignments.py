# filename: routers/assignments.py
import os
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response

from authentication import AuthHandler, TokenPayload
from exceptions import (
    AuthorizationException,
    ResourceNotFoundException,
)

from logging_config import logger
from mail_service import send_email
from models.assignments import AssignmentBase, AssignmentDB, AssignmentUpdate, Status, StatusHistory, AssignmentCreate, AssignmentRead, AssignmentStatusUpdate
from models.responses import StandardResponse, PaginatedResponse
from services.assignment_service import AssignmentService
from services.message_service import MessageService
from utils.user_roles import UserRoles

DEBUG_LEVEL = int(os.environ.get("DEBUG_LEVEL", 0))

router = APIRouter()
auth = AuthHandler()
BASE_URL = os.environ["BE_API_URL"]

# Dependency injection providers
def get_db(request: Request):
    """Get the current request's MongoDB database"""
    return request.app.state.mongodb

def get_assignment_service(db = Depends(get_db)) -> AssignmentService:
    """Create AssignmentService instance with current request's DB"""
    return AssignmentService(db)

def get_message_service(db = Depends(get_db)) -> MessageService:
    """Create MessageService instance with current request's DB"""
    return MessageService(db)


class AllStatuses(Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    REQUESTED = "REQUESTED"
    ASSIGNED = "ASSIGNED"
    ACCEPTED = "ACCEPTED"


async def send_message_to_referee(
    mongodb, match, receiver_id, content, sender_id, sender_name, footer=None
):
    """
    Send notification to referee using MessageService.
    Replaces HTTP call to /messages/ endpoint.
    """
    message_service = MessageService(mongodb)

    await message_service.send_referee_notification(
        referee_id=receiver_id,
        match=match,
        content=content,
        sender_id=sender_id,
        sender_name=sender_name,
        footer=footer
    )


# GET all assigments for ONE match ======
@router.get("/matches/{match_id}", response_description="List all assignments of a specific match")
async def get_assignments_by_match(
    request: Request,
    match_id: str = Path(..., description="Match ID"),
    assignmentStatus: list[AllStatuses] | None = Query(None, description="Filter by assignment status"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
    assignment_service: AssignmentService = Depends(get_assignment_service),
):
    """Get all assignments for a specific match"""
    mongodb = request.app.state.mongodb

    # Get all users with role REFEREE
    referees = (
        await mongodb["users"].find({"roles": "REFEREE"}, {"password": 0}).to_list(length=None)
    )

    # Get all assignments for the match with optional status filter
    query = {"matchId": match_id}
    assignments = await mongodb["assignments"].find(query).to_list(length=None)
    assignment_dict = {assignment["referee"]["userId"]: assignment for assignment in assignments}

    # Prepare the status of each referee
    assignment_list = []
    for referee in referees:
        assignment_obj = {}
        ref_id = referee["_id"]
        ref_status = assignment_dict.get(ref_id, {"status": "AVAILABLE"})
        if referee.get("referee", {}).get("club", None):
            club_id = referee["referee"]["club"]["clubId"]
            club_name = referee["referee"]["club"]["clubName"]
            club_logo = referee["referee"]["club"]["logoUrl"]
        else:
            club_id = None
            club_name = None
            club_logo = None
        ref_obj = {
            "userId": ref_id,
            "firstName": referee["firstName"],
            "lastName": referee["lastName"],
            "clubId": club_id,
            "clubName": club_name,
            "logoUrl": club_logo,
            "level": referee.get("referee", {}).get("level", "n/a"),
        }
        assignment_obj["_id"] = ref_status.get("_id", None)
        assignment_obj["matchId"] = match_id
        assignment_obj["status"] = (
            ref_status["status"] if ref_status != "AVAILABLE" else "AVAILABLE"
        )
        assignment_obj["referee"] = ref_obj
        assignment_obj["position"] = (
            ref_status.get("position", None) if isinstance(ref_status, dict) else None
        )
        assignment_list.append(assignment_obj)

    # Filter the list by status
    if assignmentStatus:
        assignment_list = [
            assignment
            for assignment in assignment_list
            if assignment["status"] in [status.value for status in assignmentStatus]
        ]

    assignment_list.sort(key=lambda x: (x["referee"]["firstName"], x["referee"]["lastName"]))

    return StandardResponse(
        success=True,
        data=assignment_list,
        message="Assignments retrieved successfully",
        status_code=status.HTTP_200_OK,
    )


# GET all assignments of ONE user ======
@router.get(
    "/users/{user_id}",
    response_description="List all assignments of a specific user",
    response_model=StandardResponse[list[AssignmentDB]],
)
async def get_assignments_by_user(
    request: Request,
    user_id: str = Path(..., description="User ID"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> StandardResponse:
    mongodb = request.app.state.mongodb
    if not (
        user_id == token_payload.sub
        or any(role in ["ADMIN", "REF_ADMIN"] for role in token_payload.roles)
    ):
        raise AuthorizationException(
            message="Not authorized to view assignments for other users",
            details={"requested_user": user_id, "requester": token_payload.sub},
        )

    user = await mongodb["users"].find_one({"_id": user_id})
    if not user:
        raise ResourceNotFoundException(resource_type="User", resource_id=user_id)
    # Get all assignments for the user
    assignments = (
        await mongodb["assignments"].find({"referee.userId": user_id}).to_list(length=None)
    )

    assignments_list = [AssignmentDB(**assignment) for assignment in assignments]
    return StandardResponse(
        success=True,
        data=assignments_list,
        message="User assignments retrieved successfully",
        status_code=status.HTTP_200_OK,
    )


# GET all assignments for ONE referee ======
@router.get("/referees/{referee_id}", response_model=list[AssignmentRead])
async def get_assignments_by_referee(
    request: Request,
    referee_id: str = Path(..., description="Referee ID"),
    assignmentStatus: list[AllStatuses] | None = Query(
        None, description="Filter by assignment status"
    ),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
    assignment_service: AssignmentService = Depends(get_assignment_service),
):
    """Get all assignments for a specific referee"""
    assignments = await assignment_service.get_assignments_by_referee(
        referee_id, assignmentStatus
    )
    return assignments

# GET a specific assignment by ID ======
@router.get("/{assignment_id}", response_model=AssignmentRead)
async def get_assignment(
    request: Request,
    assignment_id: str = Path(..., description="Assignment ID"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
    assignment_service: AssignmentService = Depends(get_assignment_service),
):
    """Get a specific assignment by ID"""
    assignment = await assignment_service.get_assignment_by_id(assignment_id)
    if not assignment:
        raise_http_exception(
            status_code=404,
            error_code="ASSIGNMENT_NOT_FOUND",
            message="Assignment not found",
        )
    return assignment

# POST =====================================================================
@router.post("", response_model=AssignmentRead, status_code=201)
async def create_assignment(
    request: Request,
    assignment_create: AssignmentCreate,
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
    assignment_service: AssignmentService = Depends(get_assignment_service),
):
    """Create Assignment"""
    mongodb = request.app.state.mongodb

    match_id = assignment_create.matchId
    user_id = token_payload.sub
    ref_id = assignment_create.refereeId
    ref_admin = assignment_create.refAdmin

    # check if match exists
    match = await mongodb["matches"].find_one({"_id": match_id})
    if not match:
        raise ResourceNotFoundException(resource_type="Match", resource_id=match_id)

    if ref_admin:
        # REF_ADMIN mode ------------------------------------------------------------
        print("REF_ADMN mode")
        # check if assignment_create.refereeId exists
        if not ref_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="User ID for referee is required",
            )
        # check if really ref_admin or admin
        if (
            ref_admin
            and UserRoles.REF_ADMIN not in token_payload.roles
            and UserRoles.ADMIN not in token_payload.roles
        ):
            raise AuthorizationException(detail="Not authorized to be referee admin")

        # check if assignment already exists for match_id and referee.userId = ref_id
        if await assignment_service.check_assignment_exists(match_id, ref_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Assignment already exists for match Id {match_id} and referee user Id {ref_id}",
            )
        # check proper status
        if assignment_create.status != Status.assigned:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid status. Only 'ASSIGNED' is allowed",
            )
        # Check if position is set in the assignment data
        if not assignment_create.position:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Position must be set for this assignment",
            )

        # Create referee object
        referee = await assignment_service.create_referee_object(ref_id)

        # Use transaction to ensure assignment and match are updated together
        async with await request.app.state.mongodb.client.start_session() as session:
            async with session.start_transaction():
                try:
                    # Create assignment within transaction
                    new_assignment = await assignment_service.create_assignment(
                        match_id=match_id,
                        referee=referee,
                        status=assignment_create.status,
                        position=assignment_create.position,
                        updated_by=token_payload.sub,
                        updated_by_name=f"{token_payload.firstName} {token_payload.lastName}",
                        session=session,
                    )

                    # Update match document within same transaction
                    await assignment_service.set_referee_in_match(
                        match_id, jsonable_encoder(referee), assignment_create.position, session=session
                    )

                    # Transaction commits automatically on success
                except Exception as e:
                    # Transaction aborts automatically on exception
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Failed to create assignment: {str(e)}",
                    ) from e

        # Send notification after transaction commits
        await send_message_to_referee(
            mongodb=mongodb,
            match=match,
            receiver_id=referee.userId,
            content=f"Hallo {referee.firstName}, du wurdest von {token_payload.firstName} für folgendes Spiel eingeteilt:",
            sender_id=token_payload.sub,
            sender_name=f"{token_payload.firstName} {token_payload.lastName}",
            footer="Du kannst diese Einteilung im Schiedsrichter-Tool bestätigen und damit signalisieren, dass du die Einteilung zur Kenntnis genommen hast.",
        )

        if new_assignment:
            return StandardResponse(
                success=True,
                data=AssignmentDB(**new_assignment),
                message="Assignment created and referee assigned successfully",
                status_code=status.HTTP_201_CREATED,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Assignment not created"
            )

    else:
        # REFEREE mode -------------------------------------------------------------
        print("REFEREE mode")
        ref_id = user_id
        """
        if 'REFEREE' not in token_payload.roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="You are not a referee")
        """

        # check if assignment already exists for match_id and referee.userId = ref_id
        if await assignment_service.check_assignment_exists(match_id, ref_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Assignment already exists for match Id {match_id} and referee user Id {ref_id}",
            )
        # check proper status
        if assignment_create.status not in [Status.requested, Status.unavailable]:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid assignment status"
            )

        # Create referee object
        referee = await assignment_service.create_referee_object(ref_id)

        new_assignment = await assignment_service.create_assignment(
            match_id=match_id,
            referee=referee,
            status=assignment_create.status,
            position=None,
            updated_by=ref_id,
            updated_by_name=f"{referee.firstName} {referee.lastName}",
        )

        if new_assignment:
            return StandardResponse(
                success=True,
                data=AssignmentDB(**new_assignment),
                message="Assignment created successfully",
                status_code=status.HTTP_201_CREATED,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Assignment not created"
            )


# PATCH =====================================================================
@router.patch(
    "/{assignment_id}/status", response_model=AssignmentRead
)
async def update_assignment_status(
    request: Request,
    assignment_id: str = Path(..., description="Assignment ID"),
    status_update: AssignmentStatusUpdate = Body(...),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
    assignment_service: AssignmentService = Depends(get_assignment_service),
    message_service: MessageService = Depends(get_message_service),
):
    """Update assignment status (accept/decline by referee)"""
    # Get existing assignment
    existing = await assignment_service.get_assignment_by_id(assignment_id)
    if not existing:
        raise_http_exception(
            status_code=404,
            error_code="ASSIGNMENT_NOT_FOUND",
            message="Assignment not found",
        )

    # Check permissions: referee can only update their own assignments
    if (
        UserRoles.REFEREE in token_payload.roles
        and existing["refereeId"] != token_payload.sub
    ):
        raise_http_exception(
            status_code=403,
            error_code="PERMISSION_DENIED",
            message="You can only update your own assignments",
        )

    # Use transaction for atomic update of assignment and message creation
    async with await request.app.state.mongodb.client.start_session() as session:
        async with session.start_transaction():
            try:
                updated_assignment = await assignment_service.update_assignment_status(
                    assignment_id, status_update.status, token_payload.sub, session=session
                )
                # Add status history entry
                await assignment_service.add_status_history(
                    assignment_id,
                    status_update.status,
                    token_payload.sub,
                    f"{token_payload.firstName} {token_payload.lastName}",
                    session=session,
                )

                # Update match document if status is accepted or unavailable
                if status_update.status in [Status.accepted, Status.unavailable]:
                    await assignment_service.update_match_referee_status(
                        existing["matchId"],
                        existing["position"],
                        status_update.status,
                        session=session,
                    )

                # Send notification to referee if accepted
                if status_update.status == Status.accepted:
                    match = await mongodb["matches"].find_one({"_id": existing["matchId"]})
                    await send_message_to_referee(
                        mongodb=mongodb,
                        match=match,
                        receiver_id=existing["refereeId"],
                        content=f"Hallo {existing['referee']['firstName']}, deine Einteilung wurde von {token_payload.firstName} bestätigt:",
                        sender_id=token_payload.sub,
                        sender_name=f"{token_payload.firstName} {token_payload.lastName}",
                        footer="Du kannst diese Einteilung im Schiedsrichter-Tool bestätigen und damit signalisieren, dass du die Einteilung zur Kenntnis genommen hast.",
                    )
                # Transaction commits automatically on success
            except Exception as e:
                # Transaction aborts automatically on exception
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to update assignment status: {str(e)}",
                ) from e

    return StandardResponse(
        success=True,
        data=AssignmentRead(**updated_assignment),
        message="Assignment status updated successfully",
        status_code=status.HTTP_200_OK,
    )


# PUT =====================================================================
@router.put("/{assignment_id}", response_model=AssignmentRead)
async def update_assignment(
    request: Request,
    assignment_id: str = Path(..., description="Assignment ID"),
    assignment_update: AssignmentUpdate = Body(...),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
    assignment_service: AssignmentService = Depends(get_assignment_service),
):
    """Update an assignment"""
    # Get existing assignment
    existing = await assignment_service.get_assignment_by_id(assignment_id)
    if not existing:
        raise_http_exception(
            status_code=404,
            error_code="ASSIGNMENT_NOT_FOUND",
            message="Assignment not found",
        )

    # Check permissions
    if UserRoles.REF_ADMIN not in token_payload.roles:
        raise_http_exception(
            status_code=403,
            error_code="PERMISSION_DENIED",
            message="Only REF_ADMIN can update assignments",
        )

    updated = await assignment_service.update_assignment(assignment_id, assignment_update)
    return updated


# DELETE =====================================================================
@router.delete("/{assignment_id}", status_code=204)
async def delete_assignment(
    request: Request,
    assignment_id: str = Path(..., description="Assignment ID"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
    assignment_service: AssignmentService = Depends(get_assignment_service),
):
    """Delete an assignment"""
    # Get existing assignment
    existing = await assignment_service.get_assignment_by_id(assignment_id)
    if not existing:
        raise_http_exception(
            status_code=404,
            error_code="ASSIGNMENT_NOT_FOUND",
            message="Assignment not found",
        )

    # Check permissions
    if UserRoles.REF_ADMIN not in token_payload.roles:
        raise_http_exception(
            status_code=403,
            error_code="PERMISSION_DENIED",
            message="Only REF_ADMIN can delete assignments",
        )

    await assignment_service.delete_assignment(assignment_id)
    return Response(status_code=204)


# GET matches starting in 14 days with no referees ======
@router.get(
    "/unassigned-in-14-days",
    response_description="Get matches starting in 14 days with no referees and notify club admins",
)
async def get_unassigned_matches_in_14_days(
    request: Request,
    send_emails: bool = Query(False, description="Whether to send notification emails"),
    # token_payload: TokenPayload = Depends(auth.auth_wrapper)
):
    mongodb = request.app.state.mongodb
    # if not any(role in ['ADMIN', 'REF_ADMIN'] for role in token_payload.roles):
    #    raise AuthorizationException(detail="Not authorized")

    # Calculate date exactly 14 days from now
    target_date = datetime.now() + timedelta(
        days=14 if os.environ.get("ENV") == "production" else 14
    )
    start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = target_date.replace(hour=23, minute=59, second=59, microsecond=999999)

    # Find matches starting exactly in 14 days with no referees assigned
    matches_cursor = mongodb["matches"].find(
        {
            "startDate": {"$gte": start_of_day, "$lte": end_of_day},
            "$and": [
                {"$or": [{"referee1": {"$exists": False}}, {"referee1": None}]},
                {"$or": [{"referee2": {"$exists": False}}, {"referee2": None}]},
                {"tournament.alias": {"$nin": ["bambini", "mini"]}},
            ],
        }
    )

    matches = await matches_cursor.to_list(length=None)

    if not matches:
        return StandardResponse(
            success=True,
            data={
                "message": "No unassigned matches found for 14 days from now",
                "matches": [],
                "emails_sent": 0,
                "target_date": target_date.strftime("%Y-%m-%d"),
            },
            message="No unassigned matches found for 14 days from now",
            status_code=status.HTTP_200_OK,
        )

    emails_sent = 0

    if send_emails:
        # Group matches by club - either matchday owner or home club
        matches_by_club: dict[str, list[Any]] = {}
        for match in matches:
            # Get matchday owner by calling the API endpoint
            matchday_owner = None
            try:
                tournament_alias = match.get("tournament", {}).get("alias")
                season_alias = match.get("season", {}).get("alias")
                round_alias = match.get("round", {}).get("alias")
                matchday_alias = match.get("matchday", {}).get("alias")

                if all([tournament_alias, season_alias, round_alias, matchday_alias]):
                    headers = {"Content-Type": "application/json"}

                    matchday_url = f"{BASE_URL}/tournaments/{tournament_alias}/seasons/{season_alias}/rounds/{round_alias}/matchdays/{matchday_alias}"
                    async with httpx.AsyncClient() as client:
                        matchday_response = await client.get(matchday_url, headers=headers)
                        if matchday_response.status_code == 200:
                            matchday_data = matchday_response.json()
                            matchday_owner = matchday_data.get("owner")
            except Exception as e:
                print(f"Failed to fetch matchday owner for match {match.get('_id')}: {str(e)}")

            if matchday_owner and matchday_owner.get("clubId"):
                # Group by matchday owner club
                club_id = matchday_owner.get("clubId")
            else:
                # Group by home club if no matchday owner
                club_id = match.get("home", {}).get("clubId")

            if club_id:
                if club_id not in matches_by_club:
                    matches_by_club[club_id] = []
                matches_by_club[club_id].append(match)

        # Send emails to club admins
        for club_id, club_matches in matches_by_club.items():
            try:
                # Find users with CLUB_ADMIN role for this club
                club_admins = (
                    await mongodb["users"]
                    .find({"roles": "CLUB_ADMIN", "club.clubId": club_id})
                    .to_list(length=None)
                )

                if not club_admins:
                    print(f"No club admins found for club {club_id}")
                    continue

                # Get club info for the email
                first_match = club_matches[0]

                # Fetch matchday owner info for email subject
                matchday_owner = None
                try:
                    tournament_alias = first_match.get("tournament", {}).get("alias")
                    season_alias = first_match.get("season", {}).get("alias")
                    round_alias = first_match.get("round", {}).get("alias")
                    matchday_alias = first_match.get("matchday", {}).get("alias")

                    if all([tournament_alias, season_alias, round_alias, matchday_alias]):
                        headers = {"Content-Type": "application/json"}

                        matchday_url = f"{BASE_URL}/tournaments/{tournament_alias}/seasons/{season_alias}/rounds/{round_alias}/matchdays/{matchday_alias}"
                        async with httpx.AsyncClient() as client:
                            matchday_response = await client.get(matchday_url, headers=headers)
                            if matchday_response.status_code == 200:
                                matchday_data = matchday_response.json()
                                matchday_owner = matchday_data.get("owner")
                except Exception as e:
                    print(f"Failed to fetch matchday owner for email: {str(e)}")

                if matchday_owner and matchday_owner.get("clubId"):
                    # Use matchday owner club info
                    club_name = matchday_owner.get("clubName", "Unknown Club")
                else:
                    # Use home club info
                    club_name = first_match.get("home", {}).get("clubName", "Unknown Club")

                # Determine if this is a matchday owner or home club
                is_matchday_owner = matchday_owner and matchday_owner.get("clubId") == club_id

                # Prepare email content
                email_subject = f"BISHL - Keine Schiedsrichter eingeteilt für {club_name}"

                match_details = ""
                for match in club_matches:
                    tournament_name = match.get("tournament", {}).get("name", "Unknown Tournament")
                    home_team = match.get("home", {}).get("fullName", "Unknown Team")
                    away_team = match.get("away", {}).get("fullName", "Unknown Team")
                    start_date = match.get("startDate")
                    venue_name = match.get("venue", {}).get("name", "Unknown Venue")

                    if start_date:
                        weekdays_german = [
                            "Montag",
                            "Dienstag",
                            "Mittwoch",
                            "Donnerstag",
                            "Freitag",
                            "Samstag",
                            "Sonntag",
                        ]
                        weekday = weekdays_german[start_date.weekday()]
                        formatted_date = start_date.strftime("%d.%m.%Y")
                        formatted_time = start_date.strftime("%H:%M")

                        match_details += f"""
                        <tr>
                            <td style="padding: 8px; border: 1px solid #ddd;">{tournament_name}</td>
                            <td style="padding: 8px; border: 1px solid #ddd;">{home_team} - {away_team}</td>
                            <td style="padding: 8px; border: 1px solid #ddd;">{weekday}, {formatted_date}</td>
                            <td style="padding: 8px; border: 1px solid #ddd;">{formatted_time}</td>
                            <td style="padding: 8px; border: 1px solid #ddd;">{venue_name}</td>
                        </tr>
                        """

                if is_matchday_owner:
                    # Email content for matchday owner
                    email_content = f"""
                    <h2>BISHL - Schiedsrichter-Einteilung erforderlich</h2>
                    <p>Hallo,</p>
                    <p>für den Spieltag des Vereins <strong>{club_name}</strong> sind für folgende Spiele noch keine Schiedsrichter eingeteilt:</p>

                    <table style="border-collapse: collapse; width: 100%; margin: 20px 0;">
                        <thead>
                            <tr style="background-color: #f5f5f5;">
                                <th style="padding: 10px; border: 1px solid #ddd; text-align: left;">Wettbewerb</th>
                                <th style="padding: 10px; border: 1px solid #ddd; text-align: left;">Spiel</th>
                                <th style="padding: 10px; border: 1px solid #ddd; text-align: left;">Datum</th>
                                <th style="padding: 10px; border: 1px solid #ddd; text-align: left;">Zeit</th>
                                <th style="padding: 10px; border: 1px solid #ddd; text-align: left;">Ort</th>
                            </tr>
                        </thead>
                        <tbody>
                            {match_details}
                        </tbody>
                    </table>

                    <p>Als Veranstalter des Spieltags ist <strong>{club_name}</strong> dafür verantwortlich, dass für alle Spiele des Spieltags Schiedsrichter gestellt werden.</p>
                    <p>Bis zum {(target_date - timedelta(days=7)).strftime('%d.%m.')} können nur Schiedsrichter der beteiligten Vereine anfragen. Ab dem {(target_date - timedelta(days=6)).strftime('%d.%m.')} können wieder alle Schiedsrichter anfragen.</p>
                    <p>Werden erst in den letzten 7 Tagen vor Spielbeginn Schiedsrichter eingeteilt, entstehen höhere Spielgebühren.</p>
                    <p>Sind drei Tage vor Spielbeginn keine Schiedsrichter eingeteilt, wird das Spiel gewertet.</p>
                    <p>Bei Fragen wendet euch gerne an das BISHL-Team.</p>
                    """
                else:
                    # Email content for home club
                    email_content = f"""
                    <h2>BISHL - Schiedsrichter-Einteilung erforderlich</h2>
                    <p>Hallo,</p>
                    <p>für folgende Heimspiele von <strong>{club_name}</strong> sind noch keine Schiedsrichter eingeteilt:</p>

                    <table style="border-collapse: collapse; width: 100%; margin: 20px 0;">
                        <thead>
                            <tr style="background-color: #f5f5f5;">
                                <th style="padding: 10px; border: 1px solid #ddd; text-align: left;">Wettbewerb</th>
                                <th style="padding: 10px; border: 1px solid #ddd; text-align: left;">Spiel</th>
                                <th style="padding: 10px; border: 1px solid #ddd; text-align: left;">Datum</th>
                                <th style="padding: 10px; border: 1px solid #ddd; text-align: left;">Zeit</th>
                                <th style="padding: 10px; border: 1px solid #ddd; text-align: left;">Ort</th>
                            </tr>
                        </thead>
                        <tbody>
                            {match_details}
                        </tbody>
                    </table>

                    <p>Bis zum {(target_date - timedelta(days=7)).strftime('%d.%m.')} können nur Schiedsrichter der beteiligten Vereine anfragen. Als Heimverein ist <strong>{club_name}</strong> nun in der Verantwortung, zwei Schiedsrichter für diese Spiele zu stellen. Ab dem {(target_date - timedelta(days=6)).strftime('%d.%m.')} können wieder alle Schiedsrichter anfragen.</p>
                    <p>Werden erst in den letzten 7 Tagen vor Spielbeginn Schiedsrichter eingeteilt, entstehen höhere Spielgebühren.</p>
                    <p>Sind drei Tage vor Spielbeginn keine Schiedsrichter eingeteilt, wird das Spiel gewertet.</p>
                    <p>Bei Fragen wendet euch gerne an das BISHL-Team.</p>
                    """

                # Send email to all club admins
                admin_emails = [admin.get("email") for admin in club_admins if admin.get("email")]
                ligenleitung_email = os.environ.get("LIGENLEITUNG_EMAIL")

                if admin_emails and os.environ.get("ENV") == "production":
                    # Add LIGENLEITUNG_EMAIL to CC when club admin emails are available
                    cc_emails = [ligenleitung_email] if ligenleitung_email else []
                    await send_email(
                        subject=email_subject,
                        recipients=admin_emails,
                        cc=cc_emails,
                        body=email_content,
                    )
                    emails_sent += len(admin_emails)
                    print(
                        f"Email sent to {len(admin_emails)} club admins for {club_name} with CC to {cc_emails}"
                    )
                elif admin_emails and os.environ.get("ENV") == "development":
                    # In development, send to admin user instead
                    admin_user_email = os.environ.get("ADMIN_USER")
                    if admin_user_email:
                        cc_emails = []
                        # Modify email content to indicate it's a test email
                        test_email_content = f"""
                        <h2>BISHL - Schiedsrichter-Einteilung erforderlich (TEST EMAIL)</h2>
                        <p><strong>Diese E-Mail würde in Produktion an Club-Admins von {club_name} gesendet werden.</strong></p>
                        <p>Original-Empfänger: {', '.join(admin_emails)}</p>
                        <p>CC: {', '.join(cc_emails) if cc_emails else 'None'}</p>
                        <hr>
                        {email_content}
                        """
                        await send_email(
                            subject=f"[TEST] {email_subject}",
                            recipients=[admin_user_email],
                            cc=cc_emails,
                            body=test_email_content,
                        )
                        emails_sent += 1
                        print(
                            f"Test email sent to admin user {admin_user_email} for {club_name} (would go to {len(admin_emails)} admins in production) with CC to {cc_emails}"
                        )
                    else:
                        print(f"ADMIN_USER not set in environment, email not sent for {club_name}")
                elif ligenleitung_email:
                    # No club admin emails available, send only to LIGENLEITUNG_EMAIL
                    if os.environ.get("ENV") == "production":
                        await send_email(
                            subject=email_subject,
                            recipients=[ligenleitung_email],
                            body=email_content,
                        )
                        emails_sent += 1
                        print(
                            f"Email sent to LIGENLEITUNG_EMAIL for {club_name} (no club admin emails available)"
                        )
                    else:
                        # In development, send to admin user instead
                        admin_user_email = os.environ.get("ADMIN_USER")
                        if admin_user_email:
                            test_email_content = f"""
                            <h2>BISHL - Schiedsrichter-Einteilung erforderlich (TEST EMAIL)</h2>
                            <p><strong>Diese E-Mail würde in Produktion an LIGENLEITUNG_EMAIL gesendet werden, da keine Club-Admin E-Mails für {club_name} verfügbar sind.</strong></p>
                            <p>Empfänger: {ligenleitung_email}</p>
                            <hr>
                            {email_content}
                            """
                            await send_email(
                                subject=f"[TEST] {email_subject}",
                                recipients=[admin_user_email],
                                body=test_email_content,
                            )
                            emails_sent += 1
                            print(
                                f"Test email sent to admin user {admin_user_email} for {club_name} (would go to LIGENLEITUNG_EMAIL in production)"
                            )
                        else:
                            print(
                                f"ADMIN_USER not set in environment, email not sent for {club_name}"
                            )
                else:
                    print(
                        f"No email addresses found for club admins of {club_name} and LIGENLEITUNG_EMAIL not set"
                    )

            except Exception as e:
                print(f"Failed to send email for club {club_id}: {str(e)}")

    # Return the matches and email status
    match_list = []
    for match in matches:
        match_info = {
            "_id": match["_id"],
            "tournament": match.get("tournament", {}),
            "home": match.get("home", {}),
            "away": match.get("away", {}),
            "startDate": match.get("startDate"),
            "venue": match.get("venue", {}),
            "referee1": match.get("referee1"),
            "referee2": match.get("referee2"),
        }
        match_list.append(match_info)

    return StandardResponse(
        success=True,
        data={
            "message": f"Found {len(matches)} unassigned matches in 14 days",
            "matches": jsonable_encoder(match_list),
            "emails_sent": emails_sent,
            "target_date": target_date.strftime("%Y-%m-%d"),
        },
        message=f"Found {len(matches)} unassigned matches in 14 days",
        status_code=status.HTTP_200_OK,
    )