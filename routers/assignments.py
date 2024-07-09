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


@router.post("/", response_model=AssignmentDB, response_description="")
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

  user_id = token_payload.sub
  if token_payload.roles not in [["ADMIN"], ['REFEREE'], ['REF_ADMIN']]:
    raise HTTPException(status_code=403, detail="Not authorized")

  # check if assignment already exists for match_id and referee.user_id = user_id
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

  if user_id == assignment_data.user_id:
    # REFEREE mode
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

  elif token_payload.roles in [["ADMIN"], ["REF_ADMIN"]]:
    # user_id != assignment_data.user_id
    # REF_ADMIN mode
    print("REF_ADMN mode")
    if assignment_data.status not in [Status.assigned]:
      raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                          detail="Invalid assignment status")
    # TODO: get referee data from col. users and pass to create_and_store_assignment
    ref_user = await request.app.mongodb["users"].find_one(
      {"_id": assignment_data.user_id})
    if not ref_user:
      raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                          detail="User not found")
    referee = {}
    referee["user_id"] = assignment_data.user_id
    referee["firstname"] = ref_user["firstname"]
    referee["lastname"] = ref_user["lastname"]
    referee["club_id"] = ref_user["club"]["club_id"]
    referee["club_name"] = ref_user["club"]["club_name"]

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
    raise HTTPException(status_code=403, detail="Not authorized")
