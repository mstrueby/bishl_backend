# filename: routers/assignments.py
from fastapi import APIRouter, Depends, HTTPException, status, Body, Request, Path
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from authentication import AuthHandler, TokenPayload
import os
from models.assignments import AssignmentBase, AssignmentDB, AssignmentUpdate, Status
from models.messages import MessageBase
from utils import get_sys_ref_tool_token
from datetime import datetime
import requests, httpx

router = APIRouter()
auth = AuthHandler()
BASE_URL = os.environ['BE_API_URL']


async def insert_assignment(db, match_id, referee, status, position=None):
  assignment = AssignmentDB(match_id=match_id,
                            referee=referee,
                            status=status,
                            position=position)
  insert_response = await db["assignments"].insert_one(
    jsonable_encoder(assignment))
  return await db["assignments"].find_one({"_id": insert_response.inserted_id})


async def set_referee_in_match(db, match_id, referee, position):
  await db['matches'].update_one({'_id': match_id}, {
    '$set': {
      f'referee{position}': {
        'user_id': referee['user_id'],
        'firstname': referee['firstname'],
        'lastname': referee['lastname'],
        'club_id': referee['club_id'],
        'club_name': referee['club_name']
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
  message_data = {"receiver_id": receiver_id, "content": content}
  url = f"{BASE_URL}/messages/"
  print("message_data", message_data)
  async with httpx.AsyncClient() as client:
    response = await client.post(url, json=message_data, headers=headers)
    if response.status_code != 201:
      raise Exception(f"Failed to send message: {response.json()}")


# GET =====================================================================
@router.get("/",
            response_description="List all assignments of a specific match")
async def get_assignments_by_match(
  request: Request,
  match_id: str = Path(..., description="Match ID"),
  token_payload: TokenPayload = Depends(auth.auth_wrapper)):
  if not any(role in ['ADMIN', 'REF_ADMIN'] for role in token_payload.roles):
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                        detail="Not authorized")

  match = await request.app.mongodb["matches"].find_one({"_id": match_id})
  if not match:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Match with id {match_id} not found")

  # Get all users with role REFEREE
  referees = await request.app.mongodb["users"].find({
    "roles": "REFEREE"
  }, {
    "password": 0
  }).to_list(length=None)

  # Get all assignments for the match
  assignments = await request.app.mongodb["assignments"].find({
    "match_id":
    match_id
  }).to_list(length=None)
  assignment_dict = {
    assignment["referee"]["user_id"]: assignment
    for assignment in assignments
  }

  # Prepare the status of each referee
  assignment_list = []
  for referee in referees:
    assignment_obj = {}
    ref_id = referee["_id"]
    ref_status = assignment_dict.get(ref_id, {"status": "AVAILABLE"})
    if referee.get("club", None):
      club_id = referee["club"]["club_id"]
      club_name = referee["club"]["club_name"]
    else:
      club_id = None
      club_name = None
    ref_obj = {
      "user_id": ref_id,
      "firstname": referee["firstname"],
      "lastname": referee["lastname"],
      "club_id": club_id,
      "club_name": club_name
    }
    assignment_obj["_id"] = ref_status.get("_id", None)
    assignment_obj["match_id"] = match_id
    assignment_obj["status"] = ref_status[
      "status"] if ref_status != "AVAILABLE" else "AVAILABLE"
    assignment_obj["referee"] = ref_obj
    assignment_obj["position"] = ref_status.get("position", None)
    assignment_list.append(assignment_obj)

  assignment_list.sort(
    key=lambda x: (x['referee']['firstname'], x['referee']['lastname']))

  return JSONResponse(status_code=status.HTTP_200_OK,
                      content=jsonable_encoder(assignment_list))


# POST =====================================================================
@router.post("/",
             response_model=AssignmentDB,
             response_description="create an initial assignment")
async def create_assignment(
  request: Request,
  match_id: str = Path(..., description="Match ID"),
  assignment_data: AssignmentBase = Body(...),
  token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> AssignmentDB:

  if not any(role in ['ADMIN', 'REFEREE', 'REF_ADMIN']
             for role in token_payload.roles):
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                        detail="Not authorized")

  user_id = token_payload.sub
  ref_admin = assignment_data.ref_admin

  # check if match exists
  match = await request.app.mongodb["matches"].find_one({"_id": match_id})
  if not match:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Match with id {match_id} not found")

  if ref_admin:
    # REF_ADMIN mode ------------------------------------------------------------
    print("REF_ADMN mode")
    # check if assignment_data.user_id exists
    ref_id = assignment_data.user_id
    if not ref_id:
      raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                          detail="User ID for referee is required")
    # check if really ref_admin
    if ref_admin and 'REF_ADMIN' not in token_payload.roles:
      raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                          detail="Not authorized to be ref_admin")
    # check if assignment already exists for match_id and referee.user_id = ref_id
    if await request.app.mongodb["assignments"].find_one({
        "match_id":
        match_id,
        "referee.user_id":
        ref_id
    }):
      raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=
        f"Assignment already exists for match_id {match_id} and referee.user_id {ref_id}"
      )
    # check if referee user_id exists
    ref_user = await request.app.mongodb["users"].find_one({"_id": ref_id})
    if not ref_user:
      raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                          detail=f"User with id {ref_id} not found")
    # check if any role in ref_user is REFEREE
    if 'REFEREE' not in ref_user.get('roles', []):
      raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                          detail=f"User with id {ref_id} is not a referee")
    # check proper status
    if assignment_data.status != Status.assigned:
      raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                          detail="Invalid status. Only 'ASSIGNED' is allowed")
    # Check if position is set in the assignment data
    if not assignment_data.position:
      raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                          detail="Position must be set for this assignment")

    if 'club' in ref_user and ref_user['club'] is not None:
      club_id = ref_user['club']['club_id']
      club_name = ref_user['club']['club_name']
    else:
      club_id = None
      club_name = None

    referee = {}
    referee["user_id"] = assignment_data.user_id
    referee["firstname"] = ref_user["firstname"]
    referee["lastname"] = ref_user["lastname"]
    referee["club_id"] = club_id
    referee["club_name"] = club_name

    new_assignment = await insert_assignment(request.app.mongodb, match_id,
                                             referee, assignment_data.status,
                                             assignment_data.position)
    await set_referee_in_match(request.app.mongodb, match_id, referee,
                               assignment_data.position)

    await send_message_to_referee(
      match=match,
      receiver_id=referee["user_id"],
      content=
      f"Hallo {referee['firstname']}, du wurdest von {token_payload.firstname} für folgendes Spiel eingeteilt:"
    )

    if new_assignment:
      return JSONResponse(status_code=status.HTTP_201_CREATED,
                          content=jsonable_encoder(
                            AssignmentDB(**new_assignment)))
    else:
      raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                          detail="Assignment not created")

  else:
    # REFEREE mode -------------------------------------------------------------
    print("REFEREE mode")
    if 'REFEREE' not in token_payload.roles:
      raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                          detail="You are not a referee")

    # check if assignment already exists for match_id and referee.user_id = ref_id
    if await request.app.mongodb["assignments"].find_one({
        "match_id":
        match_id,
        "referee.user_id":
        user_id
    }):
      raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=
        f"Assignment already exists for match_id {match_id} and referee.user_id {user_id}"
      )
    # check proper status
    if assignment_data.status not in [Status.requested, Status.unavailable]:
      raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                          detail="Invalid assignment status")

    referee = {}
    referee["user_id"] = user_id
    referee["firstname"] = token_payload.firstname
    referee["lastname"] = token_payload.lastname
    referee["club_id"] = token_payload.club_id
    referee["club_name"] = token_payload.club_name

    new_assignment = await insert_assignment(request.app.mongodb, match_id,
                                             referee, assignment_data.status)

    if new_assignment:
      return JSONResponse(status_code=status.HTTP_201_CREATED,
                          content=jsonable_encoder(
                            AssignmentDB(**new_assignment)))
    else:
      raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                          detail="Assignment not created")

  raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                      detail="The end")


# PATCH =====================================================================
@router.patch("/{assignment_id}", response_model=AssignmentDB)
async def update_assignment(
  request: Request,
  match_id: str = Path(..., description="Match ID"),
  assignment_id: str = Path(..., description="Assignment ID"),
  assignment_data: AssignmentUpdate = Body(...),
  token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> AssignmentDB:
  if not any(role in ['ADMIN', 'REFEREE', 'REF_ADMIN']
             for role in token_payload.roles):
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                        detail="Not authorized")

  user_id = token_payload.sub
  ref_admin = assignment_data.ref_admin

  # check if really ref_admin
  if ref_admin and 'REF_ADMIN' not in token_payload.roles:
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                        detail="Not authorized to be ref_admin")

  # check if match exists
  match = await request.app.mongodb["matches"].find_one({"_id": match_id})
  if not match:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Match with id {match_id} not found")

  # get assignment from db
  assignment = await request.app.mongodb["assignments"].find_one(
    {"_id": assignment_id})
  if not assignment:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Assignment with id {assignment_id} not found")

  # check if match equals match_id of assignement
  if assignment["match_id"] != match_id:
    raise HTTPException(
      status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
      detail=
      f"Assignment {assignment_id} does not belong to match with id {match_id}"
    )

  if ref_admin:
    # REF_ADMIN mode ------------------------------------------------------------
    print("REF_ADMIN mode")
    ref_id = assignment["referee"]["user_id"]
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
          detail=f"Position must be set for status {assignment_data.status}")
    print("update_data", update_data)
    if 'status' not in update_data:
      print("no update")
      return JSONResponse(status_code=status.HTTP_304_NOT_MODIFIED,
                          content=jsonable_encoder(AssignmentDB(**assignment)))
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
        result = await request.app.mongodb["assignments"].update_one(
          {"_id": assignment_id}, {
            "$set": update_data,
            "$unset": {
              "position": ""
            }
          })
        # Update match and remove referee
        await request.app.mongodb['matches'].update_one(
          {'_id': match_id},
          {'$set': {
            f'referee{assignment["position"]}': {}
          }})
        await send_message_to_referee(
          match=match,
          receiver_id=ref_id,
          content=
          f"Hallo {assignment['referee']['firstname']}, deine Einteilung wurde von {token_payload.firstname} für folgendes Spiel ENTFERNT:"
        )
      else:
        result = await request.app.mongodb["assignments"].update_one(
          {"_id": assignment_id}, {"$set": update_data})
        if update_data['status'] in [Status.assigned, Status.accepted]:

          await set_referee_in_match(request.app.mongodb, match_id,
                                     assignment['referee'],
                                     assignment_data.position)

          await send_message_to_referee(
            match=match,
            receiver_id=ref_id,
            content=
            f"Hallo {assignment['referee']['firstname']}, du wurdest von {token_payload.firstname} für folgendes Spiel eingeteilt:"
          )
      print("update_data before update", update_data)
      if result.modified_count == 1:
        updated_assignment = await request.app.mongodb["assignments"].find_one(
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

    if assignment['referee']['user_id'] != user_id:
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
    elif update_data.get("status") and (
        assignment['status'] == Status.unavailable
        and update_data["status"] == Status.requested) or (
          assignment['status'] == Status.requested
          and update_data["status"] == Status.unavailable) or (
            assignment['status'] == Status.assigned
            and update_data["status"] == Status.accepted):
      print("do update")
      result = await request.app.mongodb["assignments"].update_one(
        {"_id": assignment_id}, {"$set": update_data})

      if result.modified_count == 1:
        updated_assignment = await request.app.mongodb["assignments"].find_one(
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
