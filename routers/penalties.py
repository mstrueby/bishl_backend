# filename: routers/penalties.py
from typing import List
from bson import ObjectId
from fastapi import APIRouter, Request, Body, status, HTTPException, Depends, Path
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from models.matches import PenaltiesBase, PenaltiesDB, PenaltiesUpdate
from authentication import AuthHandler
from utils import parse_time_to_seconds, parse_time_from_seconds

router = APIRouter()
auth = AuthHandler()


async def get_penalty_object(mongodb, match_id: str, team_flag: str,
                             penalty_id: str) -> PenaltiesDB:
  """
    Retrieve a single penalty object from the specified match and team.

    Parameters:
    - mongodb: MongoDB client instance
    - match_id: The ID of the match
    - team_flag: The team flag (home/away)
    - penalty_id: The ID of the penalty

    Returns:
    - A dictionary containing the penalty object
    """

  # Validate team_flag
  if team_flag not in ["home", "away"]:
    raise HTTPException(status_code=400, detail="Invalid team flag")

  # Perform the query
  penalty = await mongodb["matches"].find_one(
    {
      "_id": match_id,
      f"{team_flag}.penalties._id": penalty_id
    }, {
      "_id": 0,
      f"{team_flag}.penalties.$": 1
    })

  if not penalty or not penalty.get(
      team_flag or "penalties" not in penalty.get(team_flag)):
    raise HTTPException(
      status_code=404,
      detail=f"Penalty with ID {penalty_id} not found in match {match_id}")

  return_data = penalty[team_flag]["penalties"][0]

  # Parse matchSeconds to a string format
  if 'matchSecondsStart' in return_data:
    return_data['matchSecondsStart'] = parse_time_from_seconds(
      return_data['matchSecondsStart'])
  if 'matchSecondsEnd' in return_data and return_data[
      'matchSecondsEnd'] is not None:
    return_data['matchSecondsEnd'] = parse_time_from_seconds(
      return_data['matchSecondsEnd'])
  return PenaltiesDB(**return_data)


# get penalty sheet of a team
@router.get("/", response_description="Get penalty sheet")
async def get_penalty_sheet(
  request: Request,
  match_id: str = Path(..., description="The ID of the match"),
  team_flag: str = Path(..., description="The team flag (home/away)"),
) -> List[PenaltiesDB]:
  team_flag = team_flag.lower()
  if team_flag not in ["home", "away"]:
    raise HTTPException(status_code=400, detail="Invalid team flag")

  match = await request.app.mongodb["matches"].find_one({"_id": match_id})
  if match is None:
    raise HTTPException(status_code=404,
                        detail=f"Match with ID {match_id} not found")

  # Get penalty sheet from match document
  penalties = match.get(team_flag, {}).get("penalties", [])

  if not isinstance(penalties, list):
    raise HTTPException(status_code=500,
                        detail="Unexpected data structure in penaltySheet")

  for penalty in penalties:
    if 'matchSecondsStart' in penalty:
      penalty['matchSecondsStart'] = parse_time_from_seconds(penalty['matchSecondsStart'])
    if 'matchSecondsEnd' in penalty and penalty['matchSecondsEnd'] is not None:
      penalty['matchSecondsEnd'] = parse_time_from_seconds(penalty['matchSecondsEnd'])

  penalty_entries = [PenaltiesDB(**penalty) for penalty in penalties]

  return JSONResponse(status_code=status.HTTP_200_OK,
                      content=jsonable_encoder(penalty_entries))


# create one penalty
@router.post("/", response_description="Create one penalty")
async def create_penalty(
  request: Request,
  match_id: str = Path(..., description="The id of the match"),
  team_flag: str = Path(..., description="The flag of the team"),
  penalty: PenaltiesBase = Body(
    ..., description="The penalty to be added to the penaltiesheet"),
  user_id: str = Depends(auth.auth_wrapper)
) -> PenaltiesDB:
  #check
  team_flag = team_flag.lower()
  if team_flag not in ["home", "away"]:
    raise HTTPException(status_code=400, detail="Invalid team flag")
  match = await request.app.mongodb["matches"].find_one({"_id": match_id})
  if match is None:
    raise HTTPException(status_code=404,
                        detail=f"Match with id {match_id} not found")

  try:
    penalty_data = {}
    new_penalty_id = str(ObjectId())
    penalty_data["_id"] = new_penalty_id
    penalty_data.update(penalty.dict())
    penalty_data.pop("id")

    penalty_data["matchSecondsStart"] = parse_time_to_seconds(
      penalty_data["matchSecondsStart"])
    if penalty_data["matchSecondsEnd"] is not None:
      penalty_data["matchSecondsEnd"] = parse_time_to_seconds(
        penalty_data['matchSecondsEnd'])
    penalty_data = jsonable_encoder(penalty_data)

    update_result = await request.app.mongodb["matches"].update_one(
      {"_id": match_id}, {"$push": {
        f"{team_flag}.penalties": penalty_data
      }})
    if update_result.modified_count == 0:
      raise HTTPException(status_code=500, detail="Failed to update match")

    # Use the reusable function to return the new penalty
    new_penalty = await get_penalty_object(request.app.mongodb, match_id,
                                           team_flag, new_penalty_id)
    return JSONResponse(status_code=status.HTTP_201_CREATED,
                        content=jsonable_encoder(new_penalty))

  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))


# get one penalty
@router.get("/{penalty_id}", response_description="Get one penalty")
async def get_one_penalty(
  request: Request,
  match_id: str = Path(..., description="The id of the match"),
  penalty_id: str = Path(..., description="The id of the penalty"),
  team_flag: str = Path(..., description="The flag of the team")
) -> PenaltiesDB:
  team_flag = team_flag.lower()
  # Use the reusable function to return the penalty
  penalty = await get_penalty_object(request.app.mongodb, match_id, team_flag,
                                     penalty_id)
  return JSONResponse(status_code=status.HTTP_200_OK,
                      content=jsonable_encoder(penalty))


# update one penalty
@router.patch("/{penalty_id}", response_description="Patch one penalty")
async def patch_one_penalty(
  request: Request,
  match_id: str = Path(..., description="The id of the match"),
  penalty_id: str = Path(..., description="The id of the penalty"),
  team_flag: str = Path(..., description="The flag of the team"),
  penalty: PenaltiesUpdate = Body(
    ..., description="The penalty to be added to the penaltiesheet"),
  user_id: str = Depends(auth.auth_wrapper)
) -> PenaltiesDB:
  # Data validation and conversion
  team_flag = team_flag.lower()
  if team_flag not in ["home", "away"]:
    raise HTTPException(status_code=400, detail="Invalid team flag")
  match = await request.app.mongodb["matches"].find_one({"_id": match_id})
  if match is None:
    raise HTTPException(status_code=404,
                        detail=f"Match with id {match_id} not found")

  # Fetch the current penalty
  current_penalty = None
  for penalty_entry in match.get(team_flag, {}).get("penalties", []):
    if penalty_entry["_id"] == penalty_id:
      current_penalty = penalty_entry
      break

  if current_penalty is None:
    raise HTTPException(
      status_code=404,
      detail=f"Penalty with id {penalty_id} not found in match {match_id}")

  # Update data
  penalty_data = penalty.dict(exclude_unset=True)
  if 'matchSecondsStart' in penalty_data:
    penalty_data['matchSecondsStart'] = parse_time_to_seconds(
      penalty_data['matchSecondsStart'])
  if 'matchSecondsEnd' in penalty_data:
    penalty_data['matchSecondsEnd'] = parse_time_to_seconds(
      penalty_data['matchSecondsEnd'])
  penalty_data = jsonable_encoder(penalty_data)

  update_data = {"$set": {}}
  for key, value in penalty_data.items():
    if current_penalty.get(key) != value:
      update_data["$set"][f"{team_flag}.penalties.$.{key}"] = value

  if update_data.get("$set"):
    try:
      result = await request.app.mongodb["matches"].update_one(
        {
          "_id": match_id,
          f"{team_flag}.penalties._id": penalty_id
        }, update_data)
      if result.modified_count == 0:
        raise HTTPException(
          status_code=404,
          detail=f"Penalty with ID {penalty_id} not found in match {match_id}")

    except Exception as e:
      raise HTTPException(status_code=500, detail=str(e))
  else:
    print("No update data")

  # Use the reusable function to return the updated penalty
  updated_penalty = await get_penalty_object(request.app.mongodb, match_id,
                                             team_flag, penalty_id)
  return JSONResponse(status_code=status.HTTP_200_OK,
                      content=jsonable_encoder(updated_penalty))


# delete one penalty
@router.delete("/{penalty_id}", response_description="Delete one penalty")
async def delete_one_penalty(
  request: Request,
  match_id: str = Path(..., description="The id of the match"),
  penalty_id: str = Path(..., description="The id of the penalty"),
  team_flag: str = Path(..., description="The flag of the team"),
  user_id: str = Depends(auth.auth_wrapper)
) -> None:
  team_flag = team_flag.lower()
  if team_flag not in ["home", "away"]:
    raise HTTPException(status_code=400, detail="Invalid team flag")
  match = await request.app.mongodb["matches"].find_one({"_id": match_id})
  if match is None:
    raise HTTPException(status_code=404,
                        detail=f"Match with id {match_id} not found")

  # Fetch the current penalty
  current_penalty = None
  for penalty_entry in match.get(team_flag, {}).get("penalties", []):
    if penalty_entry["_id"] == penalty_id:
      current_penalty = penalty_entry
      break

  if current_penalty is None:
    raise HTTPException(
      status_code=404,
      detail=f"Penalty with id {penalty_id} not found in match {match_id}")

  # Delete the penalty
  try:
    result = await request.app.mongodb["matches"].update_one(
      {
        "_id": match_id,
        f"{team_flag}.penalties._id": penalty_id
      }, {"$pull": {
        f"{team_flag}.penalties": {
          "_id": penalty_id
        }
      }})
    if result.modified_count == 0:
      raise HTTPException(
        status_code=404,
        detail=f"Penalty with ID {penalty_id} not found in match {match_id}")
    else:
      return Response(status_code=status.HTTP_204_NO_CONTENT)

  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))
