# filename: routers/assignments.py
from fastapi import APIRouter, Depends, HTTPException, status, Body, Request, Path
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from authentication import AuthHandler, TokenPayload
import os
from models.assignments import AssignmentBase, AssignmentDB, AssignmentUpdate, Status
from utils import get_sys_ref_tool_token
import httpx

router = APIRouter()
auth = AuthHandler()
BASE_URL = os.environ['BE_API_URL']


async def insert_assignment(db, match_id, referee, status, position=None):
    assignment = AssignmentDB(matchId=match_id,
                              referee=referee,
                              status=status,
                              position=position)
    print(assignment)
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
                'clubName': referee['clubName']
            }
        }
    })


async def send_message_to_referee(match, receiver_id, content):
    token = await get_sys_ref_tool_token()
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    match_text = f"{match['tournament']['name']}\n{match['home']['fullName']} - {match['away']['fullName']}\n{match['startDate'].strftime('%d.%m.%Y %H:%M')} Uhr\n{match['venue']}"
    if content is None:
        content = f"something happened to you for match:\n\n{match_text}"
    else:
        content = f"{content}\n\n{match_text}"
    message_data = {"receiverId": receiver_id, "content": content}
    url = f"{BASE_URL}/messages/"
    print("message_data", message_data)
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=message_data, headers=headers)
        if response.status_code != 201:
            raise Exception(f"Failed to send message: {response.json()}")


# GET all assigments for ONE match ======
@router.get("/matches/{match_id}",
            response_description="List all assignments of a specific match")
async def get_assignments_by_match(
    request: Request,
    match_id: str = Path(..., description="Match ID"),
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

    # Get all assignments for the match
    assignments = await mongodb["assignments"].find({
        "matchId": match_id
    }).to_list(length=None)
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
        if referee.get("club", None):
            club_id = referee["club"]["clubId"]
            club_name = referee["club"]["clubName"]
        else:
            club_id = None
            club_name = None
        ref_obj = {
            "userId": ref_id,
            "firstName": referee["firstName"],
            "lastName": referee["lastName"],
            "clubId": club_id,
            "clubName": club_name
        }
        assignment_obj["_id"] = ref_status.get("_id", None)
        assignment_obj["matchId"] = match_id
        assignment_obj["status"] = ref_status[
            "status"] if ref_status != "AVAILABLE" else "AVAILABLE"
        assignment_obj["referee"] = ref_obj
        assignment_obj["position"] = ref_status.get(
            "position", None) if isinstance(ref_status, dict) else None
        assignment_list.append(assignment_obj)

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
) -> JSONResponse:
    mongodb = request.app.state.mongodb
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
        ref_id = assignment_data.userId
        if not ref_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="User ID for referee is required")
        # check if really ref_admin
        if ref_admin and 'REF_ADMIN' not in token_payload.roles:
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
        # check if referee user_id exists
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

        if 'club' in ref_user and ref_user['club'] is not None:
            club_id = ref_user['club']['clubId']
            club_name = ref_user['club']['clubName']
        else:
            club_id = None
            club_name = None

        referee = {}
        referee["userId"] = assignment_data.userId
        referee["firstName"] = ref_user["firstName"]
        referee["lastName"] = ref_user["lastName"]
        referee["clubId"] = club_id
        referee["clubName"] = club_name

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
        if 'REFEREE' not in token_payload.roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="You are not a referee")

        # check if assignment already exists for match_id and referee.userId = ref_id
        if await mongodb["assignments"].find_one({
                "matchId": match_id,
                "referee.userId": user_id
        }):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=
                f"Assignment already exists for match Id {match_id} and referee user Id {user_id}"
            )
        # check proper status
        if assignment_data.status not in [
                Status.requested, Status.unavailable
        ]:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid assignment status")

        referee = {}
        referee["userId"] = user_id
        referee["firstName"] = token_payload.firstName
        referee["lastName"] = token_payload.lastName
        referee["clubId"] = token_payload.clubId
        referee["clubName"] = token_payload.clubName

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
    if ref_admin and 'REF_ADMIN' not in token_payload.roles:
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
        print("update_data", update_data)
        if 'status' not in update_data:
            print("no update")
            return Response(status_code=status.HTTP_304_NOT_MODIFIED)
        elif update_data.get("status") and (
                assignment['status'] == Status.requested
                and update_data["status"] == Status.assigned) or (
                    assignment['status'] == Status.assigned
                    and update_data["status"] == Status.unavailable) or (
                        assignment['status'] == Status.accepted
                        and update_data["status"] == Status.unavailable):
            print("do update")
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
                        f'referee{assignment["position"]}': {}
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
            print("update_data before update", update_data)
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
        print("update_data", update_data)
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
            print("do update")
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
