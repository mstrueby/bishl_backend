# filename: routers/assignments.py
from fastapi import APIRouter, Depends, HTTPException, status, Body, Request, Path, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from typing import Optional
from authentication import AuthHandler, TokenPayload
import os
from models.assignments import AssignmentBase, AssignmentDB, AssignmentUpdate, Status
from utils import get_sys_ref_tool_token
import httpx
from enum import Enum
from mail_service import send_email


router = APIRouter()
auth = AuthHandler()
BASE_URL = os.environ['BE_API_URL']


class AllStatuses(Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    REQUESTED = "REQUESTED"
    ASSIGNED = "ASSIGNED"
    ACCEPTED = "ACCEPTED"

async def insert_assignment(db, match_id, referee, status, position=None):
    assignment = AssignmentDB(matchId=match_id,
                              referee=referee,
                              status=status,
                              position=position)
    #print(assignment)
    insert_response = await db["assignments"].insert_one(
        jsonable_encoder(assignment))
    return await db["assignments"].find_one(
        {"_id": insert_response.inserted_id})


async def set_referee_in_match(db, match_id, referee, position):
    await db['matches'].update_one({'_id': match_id}, {
        '$set': {
            f'referee{position}': {
                'userId': referee['userId'],
                'firstName': referee['firstName'],
                'lastName': referee['lastName'],
                'clubId': referee['clubId'],
                'clubName': referee['clubName'],
                'logoUrl': referee['logoUrl'],
            }
        }
    })


async def send_message_to_referee(match, receiver_id, content):
    token = await get_sys_ref_tool_token(
        email=os.environ['SYS_REF_TOOL_EMAIL'],
        password=os.environ['SYS_REF_TOOL_PASSWORD']
    )
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    weekdays_german = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']
    weekday_abbr = weekdays_german[match['startDate'].weekday()]
    match_text = f"{match['tournament']['name']}\n{match['home']['fullName']} - {match['away']['fullName']}\n{weekday_abbr}, {match['startDate'].strftime('%d.%m.%Y')}, {match['startDate'].strftime('%H:%M')} Uhr\n{match['venue']['name']}"
    if content is None:
        content = f"something happened to you for match:\n\n{match_text}"
    else:
        content = f"{content}\n\n{match_text}"
    message_data = {"receiverId": receiver_id, "content": content}
    url = f"{BASE_URL}/messages/"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url,
                                         json=message_data,
                                         headers=headers)
            if response.status_code != 201:
                error_msg = "Failed to send message"
                try:
                    error_detail = response.json()
                    error_msg += f": {error_detail}"
                except (KeyError, TypeError) as e:
                    error_msg += f" (Status code: {response.status_code}, Content: {response.content}, Error: {str(e)})"
                raise HTTPException(status_code=response.status_code,
                                    detail=error_msg)
            
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
                        <h2>BISHL - Schiedsrichter-Information</h2>
                        <p>{content.replace('\n', '<br>')}</p>
                        <p>Hinweis: Du kannst weitere Details zu diesem Spiel auf der BISHL-Website einsehen.</p>
                        """
                        
                        if os.environ.get('ENV') == 'production':
                            await send_email(
                                subject=email_subject,
                                recipients=[referee_email],
                                body=email_content
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
            raise HTTPException(status_code=500,
                                detail=f"Request failed: {str(e)}")


# GET all assigments for ONE match ======
@router.get("/matches/{match_id}",
            response_description="List all assignments of a specific match")
async def get_assignments_by_match(
    request: Request,
    match_id: str = Path(..., description="Match ID"),
    assignmentStatus: Optional[list[AllStatuses]] = Query(None),
    token_payload: TokenPayload = Depends(auth.auth_wrapper)):
    mongodb = request.app.state.mongodb
    if not any(role in ['ADMIN', 'REF_ADMIN'] for role in token_payload.roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Not authorized")

    match = await mongodb["matches"].find_one({"_id": match_id})
    if not match:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Match with id {match_id} not found")

    # Get all users with role REFEREE
    referees = await mongodb["users"].find({
        "roles": "REFEREE"
    }, {
        "password": 0
    }).to_list(length=None)

    # Get all assignments for the match with optional status filter
    query = {"matchId": match_id}
    assignments = await mongodb["assignments"].find(query).to_list(length=None)
    assignment_dict = {
        assignment["referee"]["userId"]: assignment
        for assignment in assignments
    }

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
        assignment_obj["status"] = ref_status[
            "status"] if ref_status != "AVAILABLE" else "AVAILABLE"
        assignment_obj["referee"] = ref_obj
        assignment_obj["position"] = ref_status.get(
            "position", None) if isinstance(ref_status, dict) else None
        assignment_list.append(assignment_obj)

    # Filter the list by status
    if assignmentStatus:
        assignment_list = [
            assignment for assignment in assignment_list
            if assignment["status"] in [status.value for status in assignmentStatus]
        ]
    
    assignment_list.sort(
        key=lambda x: (x['referee']['firstName'], x['referee']['lastName']))


    return JSONResponse(status_code=status.HTTP_200_OK,
                        content=jsonable_encoder(assignment_list))


# GET all assignments of ONE user ======
@router.get("/users/{user_id}",
            response_description="List all assignments of a specific user",
            response_model=AssignmentDB)
async def get_assignments_by_user(
        request: Request,
        user_id: str = Path(..., description="User ID"),
        token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    if not (user_id == token_payload.sub or any(role in ['ADMIN', 'REF_ADMIN'] for role in token_payload.roles)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Not authorized")

    user = await mongodb["users"].find_one({"_id": user_id})
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"User with id {user_id} not found")
    # Get all assignments for the user
    assignments = await mongodb["assignments"].find({
        "referee.userId": user_id
    }).to_list(length=None)

    assignments_list = [
        AssignmentDB(**assignment) for assignment in assignments
    ]
    return JSONResponse(content=jsonable_encoder(assignments_list),
                        status_code=200)


# POST =====================================================================
@router.post("/",
             response_model=AssignmentDB,
             response_description="create an initial assignment")
async def create_assignment(
    request: Request,
    assignment_data: AssignmentBase = Body(...),
    token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    if not any(role in ['ADMIN', 'REFEREE', 'REF_ADMIN']
               for role in token_payload.roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Not authorized")

    match_id = assignment_data.matchId
    user_id = token_payload.sub
    ref_id = assignment_data.userId
    ref_admin = assignment_data.refAdmin

    # check if match exists
    match = await mongodb["matches"].find_one({"_id": match_id})
    if not match:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Match with id {match_id} not found")
      
    if ref_admin:
        # REF_ADMIN mode ------------------------------------------------------------
        print("REF_ADMN mode")
        # check if assignment_data.userId exists
        if not ref_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="User ID for referee is required")
        # check if really ref_admin or admin
        if ref_admin and 'REF_ADMIN' not in token_payload.roles and 'ADMIN' not in token_payload.roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="Not authorized to be referee admin")
        # check if assignment already exists for match_id and referee.userId = ref_id
        if await mongodb["assignments"].find_one({
                "matchId": match_id,
                "referee.userId": ref_id
        }):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=
                f"Assignment already exists for match Id {match_id} and referee user Id {ref_id}"
            )
        # check if referee exists
        ref_user = await mongodb["users"].find_one({"_id": ref_id})
        if not ref_user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"User with id {ref_id} not found")
        # check if any role in ref_user is REFEREE
        if 'REFEREE' not in ref_user.get('roles', []):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with id {ref_id} is not a referee")
        # check proper status
        if assignment_data.status != Status.assigned:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid status. Only 'ASSIGNED' is allowed")
        # Check if position is set in the assignment data
        if not assignment_data.position:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Position must be set for this assignment")

        club_info = ref_user.get('referee', {}).get('club', {})
        club_id = club_info.get('clubId')
        club_name = club_info.get('clubName')
        club_logo = club_info.get('logoUrl')

        referee = {}
        referee["userId"] = assignment_data.userId
        referee["firstName"] = ref_user["firstName"]
        referee["lastName"] = ref_user["lastName"]
        referee["clubId"] = club_id
        referee["clubName"] = club_name
        referee["logoUrl"] = club_logo
        referee["points"] = ref_user.get('referee', {}).get('points', 0)
        referee["level"] = ref_user.get('referee', {}).get('level', 'n/a')

        new_assignment = await insert_assignment(mongodb, match_id, referee,
                                                 assignment_data.status,
                                                 assignment_data.position)
        await set_referee_in_match(mongodb, match_id, referee,
                                   assignment_data.position)

        await send_message_to_referee(
            match=match,
            receiver_id=referee["userId"],
            content=
            f"Hallo {referee['firstName']}, du wurdest von {token_payload.firstName} für folgendes Spiel eingeteilt:"
        )

        if new_assignment:
            return JSONResponse(status_code=status.HTTP_201_CREATED,
                                content=jsonable_encoder(
                                    AssignmentDB(**new_assignment)))
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Assignment not created")

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
        if not ref_user or 'REFEREE' not in ref_user.get('roles', []):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"Referee with id {ref_id} not found or not a referee")
        print("ref_user", ref_user)

        # check if assignment already exists for match_id and referee.userId = ref_id
        if await mongodb["assignments"].find_one({
                "matchId": match_id,
                "referee.userId": ref_id
        }):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=
                f"Assignment already exists for match Id {match_id} and referee user Id {ref_id}"
            )
        # check proper status
        if assignment_data.status not in [
                Status.requested, Status.unavailable
        ]:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid assignment status")

        print("ref_id", ref_id)
        referee = {}
        referee["userId"] = ref_id
        referee["firstName"] = ref_user["firstName"]
        referee["lastName"] = ref_user["lastName"]
        referee["clubId"] = ref_user.get('referee', {}).get('club', {}).get('clubId')
        referee["clubName"] = ref_user.get('referee', {}).get('club', {}).get('clubName')
        referee["logoUrl"] = ref_user.get('referee', {}).get('club', {}).get('logoUrl')
        referee["points"] = ref_user.get('referee', {}).get('points', 0)
        referee["level"] = ref_user.get('referee', {}).get('level', 'n/a')

        new_assignment = await insert_assignment(mongodb, match_id, referee,
                                                 assignment_data.status)

        if new_assignment:
            return JSONResponse(status_code=status.HTTP_201_CREATED,
                                content=jsonable_encoder(
                                    AssignmentDB(**new_assignment)))
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Assignment not created")


# PATCH =====================================================================
@router.patch("/{assignment_id}",
              response_description="Update an assignment",
              response_model=AssignmentDB)
async def update_assignment(
    request: Request,
    assignment_id: str = Path(..., description="Assignment ID"),
    assignment_data: AssignmentUpdate = Body(...),
    token_payload: TokenPayload = Depends(auth.auth_wrapper)):
    mongodb = request.app.state.mongodb
    if not any(role in ['ADMIN', 'REFEREE', 'REF_ADMIN']
               for role in token_payload.roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Not authorized")

    user_id = token_payload.sub
    ref_admin = assignment_data.refAdmin

    # check if really ref_admin
    if ref_admin and 'REF_ADMIN' not in token_payload.roles and 'ADMIN' not in token_payload.roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Not authorized to be ref_admin")

    # get assignment from db
    assignment = await mongodb["assignments"].find_one({"_id": assignment_id})
    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assignment with id {assignment_id} not found")
    match_id = assignment["matchId"]

    # check if match exists
    match = await mongodb["matches"].find_one({"_id": match_id})
    if not match:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Match with id {match_id} not found")

    # check if match equals match_id of assignement
    if assignment["matchId"] != match_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=
            f"Assignment {assignment_id} does not belong to match with id {match_id}"
        )

    if ref_admin:
        # REF_ADMIN mode ------------------------------------------------------------
        print("REF_ADMIN mode")
        ref_id = assignment["referee"]["userId"]
        update_data = assignment_data.dict(exclude_unset=True)
        # exclude unchanged data
        for key, value in assignment.items():
            if key in update_data and value == update_data[key]:
                update_data.pop(key)
        # check if position is set if status in assigned or accepted
        if assignment_data.status == Status.assigned or assignment_data.status == Status.accepted:
            if not assignment_data.position:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=
                    f"Position must be set for status {assignment_data.status}"
                )
        #print("update_data", update_data)
        if 'status' not in update_data:
            #print("no update")
            return Response(status_code=status.HTTP_304_NOT_MODIFIED)
        elif update_data.get("status") and (
                assignment['status'] == Status.requested
                and update_data["status"] == Status.assigned) or (
                    assignment['status'] == Status.assigned
                    and update_data["status"] == Status.unavailable) or (
                        assignment['status'] == Status.accepted
                        and update_data["status"] == Status.unavailable):
            #print("do update")
            if 'ref_admin' in update_data:
                del update_data['ref_admin']
            if update_data['status'] not in [Status.assigned, Status.accepted]:
                # Ref wurde aus Ansetzung entfernt
                result = await mongodb["assignments"].update_one(
                    {"_id": assignment_id}, {
                        "$set": update_data,
                        "$unset": {
                            "position": ""
                        }
                    })
                # Update match and remove referee
                await mongodb['matches'].update_one(
                    {'_id': match_id},
                    {'$set': {
                        f'referee{assignment["position"]}': None
                    }})
                await send_message_to_referee(
                    match=match,
                    receiver_id=ref_id,
                    content=
                    f"Hallo {assignment['referee']['firstName']}, deine Einteilung wurde von {token_payload.firstName} für folgendes Spiel ENTFERNT:"
                )
            else:
                result = await mongodb["assignments"].update_one(
                    {"_id": assignment_id}, {"$set": update_data})
                if update_data['status'] in [Status.assigned, Status.accepted]:

                    await set_referee_in_match(mongodb, match_id,
                                               assignment['referee'],
                                               assignment_data.position)

                    await send_message_to_referee(
                        match=match,
                        receiver_id=ref_id,
                        content=
                        f"Hallo {assignment['referee']['firstName']}, du wurdest von {token_payload.firstName} für folgendes Spiel eingeteilt:"
                    )
            #print("update_data before update", update_data)
            if result.modified_count == 1:
                updated_assignment = await mongodb["assignments"].find_one(
                    {"_id": assignment_id})
                return JSONResponse(status_code=status.HTTP_200_OK,
                                    content=jsonable_encoder(
                                        AssignmentDB(**updated_assignment)))

        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=
                f"Invalid assignment status: {assignment['status']} --> {update_data['status']}"
            )
    else:
        # REFEREE mode -------------------------------------------------------------
        print("REFEREE mode")

        if assignment['referee']['userId'] != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update assignment of other referee")
        update_data = assignment_data.dict(exclude_unset=True)
        # exclude unchanged data
        for key, value in assignment.items():
            if key in update_data and value == update_data[key]:
                update_data.pop(key)
        #print("update_data", update_data)
        if not update_data:
            print("no update")
            return Response(status_code=status.HTTP_304_NOT_MODIFIED)
        elif update_data.get("status") and (
                assignment['status'] == Status.unavailable
                and update_data["status"] == Status.requested) or (
                    assignment['status'] == Status.requested
                    and update_data["status"] == Status.unavailable) or (
                        assignment['status'] == Status.assigned
                        and update_data["status"] == Status.accepted):
            #print("do update")
            result = await mongodb["assignments"].update_one(
                {"_id": assignment_id}, {"$set": update_data})

            if result.modified_count == 1:
                updated_assignment = await mongodb["assignments"].find_one(
                    {"_id": assignment_id})
                return JSONResponse(status_code=status.HTTP_200_OK,
                                    content=jsonable_encoder(
                                        AssignmentDB(**updated_assignment)))

        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=
                f"Invalid assignment status: {assignment['status']} --> {update_data['status']}"
            )

    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Can not update assignment")

# delete assignment
@router.delete("/{id}",
               response_description="Delete an assignment")
async def delete_assignment(
    request: Request,
    id: str = Path(..., description="Assignment ID"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> Response:
    mongodb = request.app.state.mongodb
    if not any(role in ['ADMIN', 'REF_ADMIN'] for role in token_payload.roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Not authorized")
    # check if assignment exists
    assignment = await mongodb["assignments"].find_one({"_id": id})
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Assignment with id {id} not found")
    match_id = assignment["matchId"]
    ref_id = assignment["referee"]["userId"]

    # check if match exists
    match = await mongodb["matches"].find_one({"_id": match_id})
    if not match:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Match with id {match_id} not found")
        
    # delete assignment
    result = await mongodb["assignments"].delete_one({"_id": id})
    if result.deleted_count == 1:
        # Update match and remove referee
        await mongodb['matches'].update_one(
            {'_id': match_id},
            {'$set': {
                f'referee{assignment["position"]}': None
            }})
        await send_message_to_referee(
            match=match,
            receiver_id=ref_id,
            content=
            f"Hallo {assignment['referee']['firstName']}, deine Einteilung wurde von {token_payload.firstName} für folgendes Spiel ENTFERNT:"
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
        
    else:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Assignment with id {id} not found")