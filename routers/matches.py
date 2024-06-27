# filename: routers/matches.py
from fastapi import APIRouter, Request, Body, status, HTTPException, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from models.matches import MatchBase, MatchDB, MatchUpdate
from authentication import AuthHandler
from utils import my_jsonable_encoder, parse_time_to_seconds, parse_time_from_seconds, fetch_standings_settings, apply_points, flatten_dict
import os

router = APIRouter()
auth = AuthHandler()
BASE_URL = os.environ['BE_API_URL']


# Prepare to convert matchSeconds to seconds for accurate comparison
def convert_times_to_seconds(data):
  for score in data.get("home", {}).get("scores", []):
    score["matchSeconds"] = parse_time_to_seconds(score["matchSeconds"])
  for score in data.get("away", {}).get("scores", []):
    score["matchSeconds"] = parse_time_to_seconds(score["matchSeconds"])
  for penalty in data.get("home", {}).get("penalties", []):
    penalty["matchSecondsStart"] = parse_time_to_seconds(
      penalty["matchSecondsStart"])
    if penalty.get('matchSecondsEnd') is not None:
      penalty["matchSecondsEnd"] = parse_time_to_seconds(
        penalty["matchSecondsEnd"])
  for penalty in data.get("away", {}).get("penalties", []):
    penalty["matchSecondsStart"] = parse_time_to_seconds(
      penalty["matchSecondsStart"])
    if penalty.get('matchSecondsEnd') is not None:
      penalty["matchSecondsEnd"] = parse_time_to_seconds(
        penalty["matchSecondsEnd"])
  return data


def convert_seconds_to_times(data):
  for score in data.get("home", {}).get("scores", []):
    score["matchSeconds"] = parse_time_from_seconds(score["matchSeconds"])
  for score in data.get("away", {}).get("scores", []):
    score["matchSeconds"] = parse_time_from_seconds(score["matchSeconds"])
  # parse penalties.matchSeconds[Start|End] to a string format
  for penalty in data.get("home", {}).get("penalties", []):
    penalty["matchSecondsStart"] = parse_time_from_seconds(
      penalty["matchSecondsStart"])
    if penalty.get('matchSecondsEnd') is not None:
      penalty["matchSecondsEnd"] = parse_time_from_seconds(
        penalty["matchSecondsEnd"])
  for penalty in data.get("away", {}).get("penalties", []):
    penalty["matchSecondsStart"] = parse_time_from_seconds(
      penalty["matchSecondsStart"])
    if penalty.get('matchSecondsEnd') is not None:
      penalty["matchSecondsEnd"] = parse_time_from_seconds(
        penalty["matchSecondsEnd"])
  return data


async def get_match_object(mongodb, match_id: str) -> MatchDB:
  match = await mongodb["matches"].find_one({"_id": match_id})
  if not match:
    raise HTTPException(status_code=404,
                        detail=f"Match with id {match_id} not found")

  # parse scores.matchSeconds to a string format
  match = convert_seconds_to_times(match)
  return MatchDB(**match)


# get all matches --> will be not implemented


# get one match by id
@router.get("/{match_id}", response_description="Get one match by id")
async def get_match(request: Request, match_id: str) -> MatchDB:
  match = await get_match_object(request.app.mongodb, match_id)
  return JSONResponse(status_code=status.HTTP_200_OK,
                      content=jsonable_encoder(match))


# create new match
@router.post("/", response_description="Add new match")
async def create_match(
    request: Request,
    match: MatchBase = Body(...),
    user_id=Depends(auth.auth_wrapper),
) -> MatchDB:

  # get standingsSettings and set points per team
  apply_points(match, await fetch_standings_settings(match.tournament.alias))

  match_data = my_jsonable_encoder(match)
  match_data = convert_times_to_seconds(match_data)

  try:
    # add match to collection matches
    print("insert into matches")
    print("match_data: ", match_data)

    result = await request.app.mongodb["matches"].insert_one(match_data)

    # return complete match document
    new_match = await get_match_object(request.app.mongodb, result.inserted_id)
    return JSONResponse(status_code=status.HTTP_201_CREATED,
                        content=jsonable_encoder(new_match))

  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))


# ------ update match
@router.patch("/{match_id}", response_description="Update match")
async def update_match(
  request: Request,
  match_id: str,
  match: MatchUpdate = Body(...),
  user_id=Depends(auth.auth_wrapper)
) -> MatchDB:
  match_data = match.dict(exclude_unset=True)
  match_data.pop("id", None)
  match_data = convert_times_to_seconds(match_data)

  existing_match = await request.app.mongodb["matches"].find_one(
    {"_id": match_id})
  if existing_match is None:
    raise HTTPException(status_code=404,
                        detail=f"Match with id {match_id} not found")

  # Identify fields to update
  match_to_update = {}

  def check_nested_fields(data, existing, path=""):
    for key, value in data.items():
      full_key = f"{path}.{key}" if path else key
      if isinstance(value, dict):
        check_nested_fields(value, existing.get(key, {}), full_key)
      else:
        if value != existing.get(key):
          match_to_update[full_key] = value

  check_nested_fields(match_data, existing_match)

  print("match_to_update: ", match_to_update)
  if match_to_update:
    try:
      # update match in matches
      set_data = {"$set": flatten_dict(match_to_update)}
      print("set_data: ", set_data)

      update_result = await request.app.mongodb["matches"].update_one(
        {"_id": match_id}, set_data)
      print("update result: ", update_result.modified_count)
      if update_result.modified_count == 0:
        raise HTTPException(status_code=404,
                            detail=f"Match with id {match_id} not found")

    except Exception as e:
      raise HTTPException(status_code=500, detail=str(e))
  else:
    print("No changes to update")

  # return updated match
  updated_match = await get_match_object(request.app.mongodb, match_id)
  return JSONResponse(status_code=status.HTTP_200_OK,
                      content=jsonable_encoder(updated_match))


# delete match
@router.delete("/{match_id}", response_description="Delete match")
async def delete_match(
  request: Request, match_id: str,
  user_id: str = Depends(auth.auth_wrapper)) -> None:
  try:
    # delete in matches
    result = await request.app.mongodb["matches"].delete_one({"_id": match_id})
    if result.deleted_count == 1:
      return Response(status_code=status.HTTP_204_NO_CONTENT)

    raise HTTPException(status_code=404,
                        detail=f"Match with ID {match_id} not found.")

  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))
