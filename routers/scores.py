# filename: routers/scores.py
from typing import List
from bson import ObjectId
from fastapi import APIRouter, Request, Body, status, HTTPException, Depends, Path
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from models.matches import ScoresBase, ScoresUpdate, ScoresDB
from authentication import AuthHandler
from pymongo.errors import DuplicateKeyError
from utils import my_jsonable_encoder

router = APIRouter()
auth = AuthHandler()


async def get_score_object(mongodb, match_id: str, team_flag: str,
                           score_id: str) -> ScoresDB:
  """
    Retrieve a single score object from the specified match and team.

    Parameters:
    - mongodb: MongoDB client instance
    - match_id: The ID of the match
    - team_flag: The team flag (home/away)
    - score_id: The ID of the score

    Returns:
    - A dictionary containing the score object
    """
  # Convert IDs to ObjectId
  #match_object_id = ObjectId(match_id)
  #score_object_id = ObjectId(score_id)

  # Validate team_flag
  if team_flag not in ["home", "away"]:
    raise HTTPException(status_code=400, detail="Invalid team flag")

  # Perform the query
  score = await mongodb["matches"].find_one(
    {
      "_id": match_id,
      f"{team_flag}.scores._id": score_id
    }, {
      "_id": 0,
      f"{team_flag}.scores.$": 1
    })

  if not score or not score.get(
      team_flag or "scores" not in score.get(
        team_flag)):
    raise HTTPException(
      status_code=404,
      detail=f"Score with ID {score_id} not found in match {match_id}")

  return_data = score[team_flag]["scores"][0]
  #print("score: ", score)
  return ScoresDB(**return_data)


# get scoresheet of a team
@router.get("/", response_description="Get score sheet")
async def get_scoresheet(
    request: Request,
    match_id: str = Path(..., description="The ID of the match"),
    team_flag: str = Path(..., description="The team flag (home/away)"),
) -> List[ScoresDB]:
    team_flag = team_flag.lower()
    if team_flag not in ["home", "away"]:
        raise HTTPException(status_code=400, detail="Invalid team flag")

    match = await request.app.mongodb["matches"].find_one({"_id": match_id})
    if match is None:
        raise HTTPException(status_code=404, detail=f"Match with ID {match_id} not found")

    # Get score sheet from match document
    scores = match.get(team_flag, {}).get("scores", [])

    if not isinstance(scores, list):
        raise HTTPException(status_code=500, detail="Unexpected data structure in scoresheet")

    score_entries = [ScoresDB(**score) for score in scores]

    return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(score_entries)) 


# create one score
@router.post("/", response_description="Create one score")
async def create_score(
  request: Request,
  match_id: str = Path(..., description="The id of the match"),
  team_flag: str = Path(..., description="The flag of the team"),
  score: ScoresBase = Body(
    ..., description="The score to be added to the scoresheet"),
  user_id: str = Depends(auth.auth_wrapper)
) -> ScoresDB:
  #check
  team_flag = team_flag.lower()
  if team_flag not in ["home", "away"]:
    raise HTTPException(status_code=400, detail="Invalid team flag")
  match = await request.app.mongodb["matches"].find_one({"_id": match_id})
  if match is None:
    raise HTTPException(status_code=404,
                        detail=f"Match with id {match_id} not found")

  score_data = jsonable_encoder(score)
  new_score_id = str(ObjectId())
  score_data['_id'] = new_score_id
  print("score_data: ", score_data)

  try:
    update_result = await request.app.mongodb["matches"].update_one(
      {"_id": match_id},
      {"$push": {
        f"{team_flag}.scores": score_data
      }})
    if update_result.modified_count == 0:
      raise HTTPException(status_code=500, detail="Failed to update match")

    # Use the reusable function to return the new score
    new_score = await get_score_object(request.app.mongodb, match_id, team_flag, new_score_id)
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=jsonable_encoder(new_score))

  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))


# get one score
@router.get("/{score_id}", response_description="Get one score")
async def get_one_score(
  request: Request,
  match_id: str = Path(..., description="The id of the match"),
  score_id: str = Path(..., description="The id of the score"),
  team_flag: str = Path(..., description="The flag of the team")
) -> ScoresDB:
  team_flag = team_flag.lower()
  # Use the reusable function to return the score
  score = await get_score_object(request.app.mongodb, match_id, team_flag, score_id)
  return JSONResponse(status_code=status.HTTP_200_OK,
                      content=jsonable_encoder(score))

# update one score
@router.patch("/{score_id}", response_description="Patch one score")
async def patch_one_score(
  request: Request,
  match_id: str = Path(..., description="The id of the match"),
  score_id: str = Path(..., description="The id of the score"),
  team_flag: str = Path(..., description="The flag of the team"),
  score: ScoresUpdate = Body(
    ..., description="The score to be added to the scoresheet"),
  user_id: str = Depends(auth.auth_wrapper)
) -> ScoresDB:
  # Data validation and conversion
  team_flag = team_flag.lower()
  if team_flag not in ["home", "away"]:
    raise HTTPException(status_code=400, detail="Invalid team flag")
  match = await request.app.mongodb["matches"].find_one({"_id": match_id})
  if match is None:
    raise HTTPException(status_code=404,
                        detail=f"Match with id {match_id} not found")

  # Fetch the current score
  current_score = None
  for score_entry in match.get(team_flag, {}).get("scores", []):
    if score_entry["_id"] == score_id:
      current_score = score_entry
      break

  if current_score is None:
    raise HTTPException(
      status_code=404,
      detail=f"Score with id {score_id} not found in match {match_id}")

  # Update data
  score_data = jsonable_encoder(score.dict(exclude_unset=True))
  update_data = {"$set": {}}
  for key, value in score_data.items():
    if current_score.get(key) != value:
      update_data["$set"][f"{team_flag}.scores.$.{key}"] = value

  if update_data.get("$set"):
    try:
      result = await request.app.mongodb["matches"].update_one(
        {
          "_id": match_id,
          f"{team_flag}.scores._id": score_id
        }, update_data)
      if result.modified_count == 0:
        raise HTTPException(status_code=404, detail=f"Score with ID {score_id} not found in match {match_id}")

    except Exception as e:
      raise HTTPException(status_code=500, detail=str(e))
  else:
    print("No update data")

  # Use the reusable function to return the updated score
  updated_score = await get_score_object(request.app.mongodb, match_id, team_flag, score_id)
  return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(updated_score))


# delete one score
@router.delete("/{score_id}", response_description="Delete one score")
async def delete_one_score(
  request: Request,
  match_id: str = Path(..., description="The id of the match"),
  score_id: str = Path(..., description="The id of the score"),
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

  # Fetch the current score
  current_score = None
  for score_entry in match.get(team_flag, {}).get("scores", []):
    if score_entry["_id"] == score_id:
      current_score = score_entry
      break

  if current_score is None:
    raise HTTPException(
      status_code=404,
      detail=f"Score with id {score_id} not found in match {match_id}")

  # Delete the score
  try:
    result = await request.app.mongodb["matches"].update_one(
      {
        "_id": match_id,
        f"{team_flag}.scores._id": score_id
      }, {"$pull": {
        f"{team_flag}.scores": {"_id": score_id}
      }})
    if result.modified_count == 0:
      raise HTTPException(status_code=404, detail=f"Score with ID {score_id} not found in match {match_id}")
    else:
      return Response(status_code=status.HTTP_204_NO_CONTENT)
      
  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))