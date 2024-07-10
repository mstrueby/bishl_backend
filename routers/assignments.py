# filename: routers/assignments.py
from fastapi import APIRouter, Depends, HTTPException, status, Body, Request, Path
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from authentication import AuthHandler, TokenPayload
import os
from models.assignments import AssignmentBase, AssignmentDB, AssignmentUpdate, Status

router = APIRouter()
auth = AuthHandler()
BASE_URL = os.environ['BE_API_URL']


@router.get("/",
            response_description="List all assignments of a specific match")
async def get_assignments_by_match(
  request: Request,
  match_id: str = Path(..., description="Match ID"),
  token_payload: TokenPayload = Depends(auth.auth_wrapper)):
  if not any(role in ['ADMIN', 'REF_ADMIN']
             for role in token_payload.roles):
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                        detail="Not authorized")

  match = await request.app.mongodb["matches"].find_one({"_id": match_id})
  if not match:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Match with id {match_id} not found")

  assignments = await request.app.mongodb["assignments"].find({
    "match_id": match_id
  }).sort("referee.firstname").to_list(length=None)
  return JSONResponse(status_code=status.HTTP_200_OK,
                      content=jsonable_encoder(assignments))


@router.post("/",
             response_model=AssignmentDB,
             response_description="create an initial assignment")
async def create_assignment(
  request: Request,
  match_id: str = Path(..., description="Match ID"),
  assignment_data: AssignmentBase = Body(...),
  token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> AssignmentDB:

  async def insert_assignment(match_id, referee, status):
    assignment = AssignmentDB(match_id=match_id,
                              referee=referee,
                              status=status)
    insert_response = await request.app.mongodb["assignments"].insert_one(
      jsonable_encoder(assignment))
    return await request.app.mongodb["assignments"].find_one(
      {"_id": insert_response.inserted_id})

  if not any(role in ['ADMIN', 'REFEREE', 'REF_ADMIN']
             for role in token_payload.roles):
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                        detail="Not authorized")

  user_id = token_payload.sub
  ref_id = assignment_data.user_id

  # preliminary checks

  # check if match exists
  match = await request.app.mongodb["matches"].find_one({"_id": match_id})
  if not match:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Match with id {match_id} not found")
  # check if assignment already exists for match_id and referee.user_id = user_id
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
                        detail="User not found")
  # check if any role in ref_user is REFEREE
  if 'REFEREE' not in ref_user.get('roles', []):
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                        detail="User is not a referee")
  #print("roles", token_payload.roles)
  #print("REF_ADMIN", any(role in ['ADMIN', 'REF_ADMIN'] for role in token_payload.roles))
  if user_id == ref_id and 'REFEREE' in token_payload.roles and assignment_data.status != Status.assigned:
    # REFEREE mode
    print("REFEREE mode")
    if 'REFEREE' not in token_payload.roles:
      raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                          detail="You are not a referee")

    if assignment_data.status not in [Status.requested, Status.unavailable]:
      raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                          detail="Invalid assignment status")

    referee = {}
    referee["user_id"] = assignment_data.user_id
    referee["firstname"] = token_payload.firstname
    referee["lastname"] = token_payload.lastname
    referee["club_id"] = token_payload.club_id
    referee["club_name"] = token_payload.club_name

    new_assignment = await insert_assignment(match_id, referee,
                                             assignment_data.status)
    if new_assignment:
      return JSONResponse(status_code=status.HTTP_201_CREATED,
                          content=jsonable_encoder(
                            AssignmentDB(**new_assignment)))
    else:
      raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                          detail="Assignment not created")

  elif any(role in ['ADMIN', 'REF_ADMIN'] for role in
           token_payload.roles) and assignment_data.status == Status.assigned:
    # user_id != assignment_data.user_id
    # REF_ADMIN mode
    print("REF_ADMN mode")

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
    referee["position"] = assignment_data.position
    referee["user_id"] = assignment_data.user_id
    referee["firstname"] = ref_user["firstname"]
    referee["lastname"] = ref_user["lastname"]
    referee["club_id"] = club_id
    referee["club_name"] = club_name

    new_assignment = await insert_assignment(match_id, referee,
                                             assignment_data.status)
    if new_assignment:
      return JSONResponse(status_code=status.HTTP_201_CREATED,
                          content=jsonable_encoder(
                            AssignmentDB(**new_assignment)))
    else:
      raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                          detail="Assignment not created")

  else:
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="Invalid assignment status")
