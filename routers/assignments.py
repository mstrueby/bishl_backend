# filename: routers/assignments.py
import os
from datetime import datetime
from enum import Enum

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response

from authentication import AuthHandler, TokenPayload
from exceptions import (
    AuthorizationException,
    ResourceNotFoundException,
)
from mail_service import send_email
from models.assignments import AssignmentBase, AssignmentDB, AssignmentUpdate, Status, StatusHistory
from utils import get_sys_ref_tool_token

router = APIRouter()
auth = AuthHandler()
BASE_URL = os.environ["BE_API_URL"]


class AllStatuses(Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    REQUESTED = "REQUESTED"
    ASSIGNED = "ASSIGNED"
    ACCEPTED = "ACCEPTED"


async def add_status_history_entry(
    db, assignment_id, new_status, updated_by=None, updated_by_name=None, session=None
):
    """Add a new entry to the status history of an assignment"""
    status_entry = StatusHistory(
        status=new_status,
        updateDate=datetime.now().replace(microsecond=0),
        updatedBy=updated_by,
        updatedByName=updated_by_name,
    )

    await db["assignments"].update_one(
        {"_id": assignment_id},
        {"$push": {"statusHistory": jsonable_encoder(status_entry)}},
        session=session,
    )


async def insert_assignment(
    db,
    match_id,
    referee,
    status,
    position=None,
    updated_by=None,
    updated_by_name=None,
    session=None,
):
    # Create initial status history entry
    initial_status_history = [
        StatusHistory(
            status=status,
            updateDate=datetime.now().replace(microsecond=0),
            updatedBy=updated_by,
            updatedByName=updated_by_name,
        )
    ]

    assignment = AssignmentDB(
        matchId=match_id,
        referee=referee,
        status=status,
        position=position,
        statusHistory=initial_status_history,
    )
    # print(assignment)
    insert_response = await db["assignments"].insert_one(
        jsonable_encoder(assignment), session=session
    )
    return await db["assignments"].find_one({"_id": insert_response.inserted_id}, session=session)


async def set_referee_in_match(db, match_id, referee, position, session=None):
    await db["matches"].update_one(
        {"_id": match_id},
        {
            "$set": {
                f"referee{position}": {
                    "userId": referee["userId"],
                    "firstName": referee["firstName"],
                    "lastName": referee["lastName"],
                    "clubId": referee["clubId"],
                    "clubName": referee["clubName"],
                    "logoUrl": referee["logoUrl"],
                }
            }
        },
        session=session,
    )


async def send_message_to_referee(match, receiver_id, content, footer=None):
    token = await get_sys_ref_tool_token(
        email=os.environ["SYS_REF_TOOL_EMAIL"], password=os.environ["SYS_REF_TOOL_PASSWORD"]
    )
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    weekdays_german = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
    weekday_abbr = weekdays_german[match["startDate"].weekday()]
    match_text = f"{match['tournament']['name']}\n{match['home']['fullName']} - {match['away']['fullName']}\n{weekday_abbr}, {match['startDate'].strftime('%d.%m.%Y')}, {match['startDate'].strftime('%H:%M')} Uhr\n{match['venue']['name']}"
    if content is None:
        content = f"something happened to you for match:\n\n{match_text}"
    else:
        content = f"{content}\n\n{match_text}"
    message_data = {"receiverId": receiver_id, "content": content}
    url = f"{BASE_URL}/messages/"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=message_data, headers=headers)
            if response.status_code != 201:
                error_msg = "Failed to send message"
                try:
                    error_detail = response.json()
                    error_msg += f": {error_detail}"
                except (KeyError, TypeError) as e:
                    error_msg += f" (Status code: {response.status_code}, Content: {response.content}, Error: {str(e)})"
                raise HTTPException(status_code=response.status_code, detail=error_msg)

            # After successfully sending the message, also send an email
            try:
                # Get referee's email by making a request to users endpoint
                user_url = f"{BASE_URL}/users/{receiver_id}"
                user_response = await client.get(user_url, headers=headers)
                if user_response.status_code == 200:
                    user_data = user_response.json()
                    referee_email = user_data.get("email")

                    if referee_email:
                        # Format the email content as HTML
                        email_subject = "BISHL - Schiedsrichter-Information"
                        email_content = f"""
                        <p>{content.replace('\n', '<br>')}</p>
                        {f'<p>{footer}</p>' if footer else ''}
                        """

                        if os.environ.get("ENV") == "production":
                            await send_email(
                                subject=email_subject,
                                recipients=[referee_email],
                                body=email_content,
                            )
                            print(f"Email sent to referee {receiver_id} at {referee_email}")
                        else:
                            print(f"Email not sent because of ENV = {os.environ.get('ENV')}")
                    else:
                        print(f"Referee {receiver_id} has no email address")
                else:
                    print(f"Failed to get referee {receiver_id} data: {user_response.status_code}")
            except Exception as e:
                # Just log email sending failure but don't fail the request
                print(f"Failed to send email to referee {receiver_id}: {str(e)}")

        except httpx.RequestError as e:
            raise HTTPException(status_code=500, detail=f"Request failed: {str(e)}")


# GET all assigments for ONE match ======
@router.get("/matches/{match_id}", response_description="List all assignments of a specific match")
async def get_assignments_by_match(
    request: Request,
    match_id: str = Path(..., description="Match ID"),
    assignmentStatus: list[AllStatuses] | None = Query(None),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
):
    mongodb = request.app.state.mongodb
    if not any(role in ["ADMIN", "REF_ADMIN"] for role in token_payload.roles):
        raise AuthorizationException(
            message="Admin or Ref Admin role required", details={"user_roles": token_payload.roles}
        )

    match = await mongodb["matches"].find_one({"_id": match_id})
    if not match:
        raise ResourceNotFoundException(resource_type="Match", resource_id=match_id)

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

    return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(assignment_list))


# GET all assignments of ONE user ======
@router.get(
    "/users/{user_id}",
    response_description="List all assignments of a specific user",
    response_model=AssignmentDB,
)
async def get_assignments_by_user(
    request: Request,
    user_id: str = Path(..., description="User ID"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> JSONResponse:
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
    return JSONResponse(content=jsonable_encoder(assignments_list), status_code=200)


# POST =====================================================================
@router.post("/", response_model=AssignmentDB, response_description="create an initial assignment")
async def create_assignment(
    request: Request,
    assignment_data: AssignmentBase = Body(...),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    if not any(role in ["ADMIN", "REFEREE", "REF_ADMIN"] for role in token_payload.roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    match_id = assignment_data.matchId
    user_id = token_payload.sub
    ref_id = assignment_data.userId
    ref_admin = assignment_data.refAdmin

    # check if match exists
    match = await mongodb["matches"].find_one({"_id": match_id})
    if not match:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Match with id {match_id} not found"
        )

    if ref_admin:
        # REF_ADMIN mode ------------------------------------------------------------
        print("REF_ADMN mode")
        # check if assignment_data.userId exists
        if not ref_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="User ID for referee is required",
            )
        # check if really ref_admin or admin
        if (
            ref_admin
            and "REF_ADMIN" not in token_payload.roles
            and "ADMIN" not in token_payload.roles
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to be referee admin"
            )
        # check if assignment already exists for match_id and referee.userId = ref_id
        if await mongodb["assignments"].find_one({"matchId": match_id, "referee.userId": ref_id}):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Assignment already exists for match Id {match_id} and referee user Id {ref_id}",
            )
        # check if referee exists
        ref_user = await mongodb["users"].find_one({"_id": ref_id})
        if not ref_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"User with id {ref_id} not found"
            )
        # check if any role in ref_user is REFEREE
        if "REFEREE" not in ref_user.get("roles", []):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with id {ref_id} is not a referee",
            )
        # check proper status
        if assignment_data.status != Status.assigned:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid status. Only 'ASSIGNED' is allowed",
            )
        # Check if position is set in the assignment data
        if not assignment_data.position:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Position must be set for this assignment",
            )

        club_info = ref_user.get("referee", {}).get("club", {})
        club_id = club_info.get("clubId")
        club_name = club_info.get("clubName")
        club_logo = club_info.get("logoUrl")

        referee = {}
        referee["userId"] = assignment_data.userId
        referee["firstName"] = ref_user["firstName"]
        referee["lastName"] = ref_user["lastName"]
        referee["clubId"] = club_id
        referee["clubName"] = club_name
        referee["logoUrl"] = club_logo
        referee["points"] = ref_user.get("referee", {}).get("points", 0)
        referee["level"] = ref_user.get("referee", {}).get("level", "n/a")

        # Use transaction to ensure assignment and match are updated together
        async with await request.app.state.client.start_session() as session:
            async with session.start_transaction():
                try:
                    # Create assignment within transaction
                    new_assignment = await insert_assignment(
                        mongodb,
                        match_id,
                        referee,
                        assignment_data.status,
                        assignment_data.position,
                        token_payload.sub,
                        f"{token_payload.firstName} {token_payload.lastName}",
                        session=session,
                    )

                    # Update match document within same transaction
                    await set_referee_in_match(
                        mongodb, match_id, referee, assignment_data.position, session=session
                    )

                    # Transaction commits automatically on success
                except Exception as e:
                    # Transaction aborts automatically on exception
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Failed to create assignment: {str(e)}",
                    )

        # Send notification after transaction commits
        await send_message_to_referee(
            match=match,
            receiver_id=referee["userId"],
            content=f"Hallo {referee['firstName']}, du wurdest von {token_payload.firstName} für folgendes Spiel eingeteilt:",
            footer="Du kannst diese Einteilung im Schiedsrichter-Tool bestätigen und damit signalisieren, dass du die Einteilung zur Kenntnis genommen hast.",
        )

        if new_assignment:
            return JSONResponse(
                status_code=status.HTTP_201_CREATED,
                content=jsonable_encoder(AssignmentDB(**new_assignment)),
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

        print("ref_id", ref_id)
        # get referee
        ref_user = await mongodb["users"].find_one({"_id": ref_id})
        if not ref_user or "REFEREE" not in ref_user.get("roles", []):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Referee with id {ref_id} not found or not a referee",
            )
        print("ref_user", ref_user)

        # check if assignment already exists for match_id and referee.userId = ref_id
        if await mongodb["assignments"].find_one({"matchId": match_id, "referee.userId": ref_id}):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Assignment already exists for match Id {match_id} and referee user Id {ref_id}",
            )
        # check proper status
        if assignment_data.status not in [Status.requested, Status.unavailable]:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid assignment status"
            )

        print("ref_id", ref_id)
        referee = {}
        referee["userId"] = ref_id
        referee["firstName"] = ref_user["firstName"]
        referee["lastName"] = ref_user["lastName"]
        referee["clubId"] = ref_user.get("referee", {}).get("club", {}).get("clubId")
        referee["clubName"] = ref_user.get("referee", {}).get("club", {}).get("clubName")
        referee["logoUrl"] = ref_user.get("referee", {}).get("club", {}).get("logoUrl")
        referee["points"] = ref_user.get("referee", {}).get("points", 0)
        referee["level"] = ref_user.get("referee", {}).get("level", "n/a")

        new_assignment = await insert_assignment(
            mongodb,
            match_id,
            referee,
            assignment_data.status,
            None,
            ref_id,
            f"{ref_user['firstName']} {ref_user['lastName']}",
        )

        if new_assignment:
            return JSONResponse(
                status_code=status.HTTP_201_CREATED,
                content=jsonable_encoder(AssignmentDB(**new_assignment)),
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Assignment not created"
            )


# PATCH =====================================================================
@router.patch(
    "/{assignment_id}", response_description="Update an assignment", response_model=AssignmentDB
)
async def update_assignment(
    request: Request,
    assignment_id: str = Path(..., description="Assignment ID"),
    assignment_data: AssignmentUpdate = Body(...),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
):
    mongodb = request.app.state.mongodb
    if not any(role in ["ADMIN", "REFEREE", "REF_ADMIN"] for role in token_payload.roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    user_id = token_payload.sub
    ref_admin = assignment_data.refAdmin

    # check if really ref_admin
    if ref_admin and "REF_ADMIN" not in token_payload.roles and "ADMIN" not in token_payload.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to be ref_admin"
        )

    # get assignment from db
    assignment = await mongodb["assignments"].find_one({"_id": assignment_id})
    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assignment with id {assignment_id} not found",
        )
    match_id = assignment["matchId"]

    # check if match exists
    match = await mongodb["matches"].find_one({"_id": match_id})
    if not match:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Match with id {match_id} not found"
        )

    # check if match equals match_id of assignement
    if assignment["matchId"] != match_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Assignment {assignment_id} does not belong to match with id {match_id}",
        )

    if ref_admin:
        # REF_ADMIN mode ------------------------------------------------------------
        print("REF_ADMIN mode")
        ref_id = assignment["referee"]["userId"]
        update_data = assignment_data.model_dump(exclude_unset=True)
        # exclude unchanged data
        for key, value in assignment.items():
            if key in update_data and value == update_data[key]:
                update_data.pop(key)
        # check if position is set if status in assigned or accepted
        if assignment_data.status == Status.assigned or assignment_data.status == Status.accepted:
            if not assignment_data.position:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Position must be set for status {assignment_data.status}",
                )
        # print("update_data", update_data)
        if "status" not in update_data:
            # print("no update")
            return Response(status_code=status.HTTP_304_NOT_MODIFIED)
        elif (
            update_data.get("status")
            and (
                assignment["status"] == Status.requested
                and update_data["status"] == Status.assigned
            )
            or (
                assignment["status"] == Status.assigned
                and update_data["status"] == Status.unavailable
            )
            or (
                assignment["status"] == Status.accepted
                and update_data["status"] == Status.unavailable
            )
        ):
            # print("do update")
            if "ref_admin" in update_data:
                del update_data["ref_admin"]

            # Use transaction for assignment and match updates
            async with await request.app.state.client.start_session() as session:
                async with session.start_transaction():
                    try:
                        if update_data["status"] not in [Status.assigned, Status.accepted]:
                            # Ref wurde aus Ansetzung entfernt
                            result = await mongodb["assignments"].update_one(
                                {"_id": assignment_id},
                                {"$set": update_data, "$unset": {"position": ""}},
                                session=session,
                            )
                            # Add status history entry
                            await add_status_history_entry(
                                mongodb,
                                assignment_id,
                                update_data["status"],
                                token_payload.sub,
                                f"{token_payload.firstName} {token_payload.lastName}",
                                session=session,
                            )
                            # Update match and remove referee
                            await mongodb["matches"].update_one(
                                {"_id": match_id},
                                {"$set": {f'referee{assignment["position"]}': None}},
                                session=session,
                            )
                        else:
                            result = await mongodb["assignments"].update_one(
                                {"_id": assignment_id}, {"$set": update_data}, session=session
                            )
                            # Add status history entry
                            await add_status_history_entry(
                                mongodb,
                                assignment_id,
                                update_data["status"],
                                token_payload.sub,
                                f"{token_payload.firstName} {token_payload.lastName}",
                                session=session,
                            )
                            if update_data["status"] in [Status.assigned, Status.accepted]:
                                await set_referee_in_match(
                                    mongodb,
                                    match_id,
                                    assignment["referee"],
                                    assignment_data.position,
                                    session=session,
                                )
                        # Transaction commits automatically on success
                    except Exception as e:
                        # Transaction aborts automatically on exception
                        raise HTTPException(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Failed to update assignment: {str(e)}",
                        ) from e

            # Send notifications after transaction commits
            if update_data["status"] not in [Status.assigned, Status.accepted]:
                await send_message_to_referee(
                    match=match,
                    receiver_id=ref_id,
                    content=f"Hallo {assignment['referee']['firstName']}, deine Einteilung wurde von {token_payload.firstName} für folgendes Spiel ENTFERNT:",
                )
            elif update_data["status"] in [Status.assigned, Status.accepted]:
                await send_message_to_referee(
                    match=match,
                    receiver_id=ref_id,
                    content=f"Hallo {assignment['referee']['firstName']}, du wurdest von {token_payload.firstName} für folgendes Spiel eingeteilt:",
                    footer="Du kannst diese Einteilung im Schiedsrichter-Tool bestätigen und damit signalisieren, dass du die Einteilung zur Kenntnis genommen hast.",
                )
            # print("update_data before update", update_data)
            if result.modified_count == 1:
                updated_assignment = await mongodb["assignments"].find_one({"_id": assignment_id})
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content=jsonable_encoder(AssignmentDB(**updated_assignment)),
                )

        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid assignment status: {assignment['status']} --> {update_data['status']}",
            )
    else:
        # REFEREE mode -------------------------------------------------------------
        print("REFEREE mode")

        if assignment["referee"]["userId"] != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update assignment of other referee",
            )
        update_data = assignment_data.model_dump(exclude_unset=True)
        # exclude unchanged data
        for key, value in assignment.items():
            if key in update_data and value == update_data[key]:
                update_data.pop(key)
        # print("update_data", update_data)
        if not update_data:
            print("no update")
            return Response(status_code=status.HTTP_304_NOT_MODIFIED)
        elif (
            update_data.get("status")
            and (
                assignment["status"] == Status.unavailable
                and update_data["status"] == Status.requested
            )
            or (
                assignment["status"] == Status.requested
                and update_data["status"] == Status.unavailable
            )
            or (
                assignment["status"] == Status.assigned and update_data["status"] == Status.accepted
            )
        ):
            # print("do update")
            result = await mongodb["assignments"].update_one(
                {"_id": assignment_id}, {"$set": update_data}
            )
            # Add status history entry
            await add_status_history_entry(
                mongodb,
                assignment_id,
                update_data["status"],
                user_id,
                f"{assignment['referee']['firstName']} {assignment['referee']['lastName']}",
            )

            if result.modified_count == 1:
                updated_assignment = await mongodb["assignments"].find_one({"_id": assignment_id})
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content=jsonable_encoder(AssignmentDB(**updated_assignment)),
                )

        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid assignment status: {assignment['status']} --> {update_data['status']}",
            )

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Can not update assignment"
    )


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
    #    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
    #                        detail="Not authorized")

    # Calculate date exactly 14 days from now
    from datetime import datetime, timedelta

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
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": "No unassigned matches found for 14 days from now",
                "matches": [],
                "emails_sent": 0,
                "target_date": target_date.strftime("%Y-%m-%d"),
            },
        )

    emails_sent = 0

    if send_emails:
        # Group matches by club - either matchday owner or home club
        matches_by_club = {}
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

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "message": f"Found {len(matches)} unassigned matches in 14 days",
            "matches": jsonable_encoder(match_list),
            "emails_sent": emails_sent,
            "target_date": target_date.strftime("%Y-%m-%d"),
        },
    )


# delete assignment
@router.delete("/{id}", response_description="Delete an assignment")
async def delete_assignment(
    request: Request,
    id: str = Path(..., description="Assignment ID"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> Response:
    mongodb = request.app.state.mongodb
    if not any(role in ["ADMIN", "REF_ADMIN"] for role in token_payload.roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    # check if assignment exists
    assignment = await mongodb["assignments"].find_one({"_id": id})
    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Assignment with id {id} not found"
        )
    match_id = assignment["matchId"]
    ref_id = assignment["referee"]["userId"]

    # check if match exists
    match = await mongodb["matches"].find_one({"_id": match_id})
    if not match:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Match with id {match_id} not found"
        )

    # Use transaction to delete assignment and update match together
    async with await request.app.state.client.start_session() as session:
        async with session.start_transaction():
            try:
                # Delete assignment
                result = await mongodb["assignments"].delete_one({"_id": id}, session=session)
                if result.deleted_count == 1:
                    # Update match and remove referee
                    await mongodb["matches"].update_one(
                        {"_id": match_id},
                        {"$set": {f'referee{assignment["position"]}': None}},
                        session=session,
                    )
                    # Transaction commits automatically on success
                else:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Assignment with id {id} not found",
                    )
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to delete assignment: {str(e)}",
                )

    # Send notification after transaction commits
    await send_message_to_referee(
        match=match,
        receiver_id=ref_id,
        content=f"Hallo {assignment['referee']['firstName']}, deine Einteilung wurde von {token_payload.firstName} für folgendes Spiel ENTFERNT:",
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)