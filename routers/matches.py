# filename: routers/matches.py
from fastapi import APIRouter, Request, Body, status, HTTPException, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from models.matches import MatchBase, MatchDB, MatchUpdate, MatchTeamUpdate
from authentication import AuthHandler
from utils import my_jsonable_encoder, parse_time_to_seconds, parse_time_from_seconds, fetch_standings_settings, calc_match_stats, flatten_dict, calc_standings_per_round, calc_standings_per_matchday
import os
from bson import ObjectId

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
  if match is None:
    raise HTTPException(status_code=404,
                        detail=f"Match with ID {match_id} not found.")

  return JSONResponse(status_code=status.HTTP_200_OK,
                      content=jsonable_encoder(match))


# create new match
@router.post("/", response_description="Add new match")
async def create_match(
    request: Request,
    match: MatchBase = Body(...),
    user_id=Depends(auth.auth_wrapper),
) -> MatchDB:
  try:
    # get standingsSettings and set points per team
    if all(
      [hasattr(match, 'tournament') and hasattr(match.tournament, 'alias')]):
      print("do stats")
      stats = calc_match_stats(
        match.matchStatus.key, match.finishType.key,
        jsonable_encoder(match.home.stats), await
        fetch_standings_settings(match.tournament.alias))
      print("stats: ", stats)
      match.home.stats = stats['home']
      match.away.stats = stats['away']

    match_data = my_jsonable_encoder(match)
    match_data = convert_times_to_seconds(match_data)

    # add match to collection matches
    print("insert into matches")
    print("match_data: ", match_data)

    result = await request.app.mongodb["matches"].insert_one(match_data)

    # calc standings and set it in round if createStandings is true
    await calc_standings_per_round(request.app.mongodb, match.tournament.alias,
                                   match.season.alias, match.round.alias)
    await calc_standings_per_matchday(request.app.mongodb,
                                      match.tournament.alias,
                                      match.season.alias, match.round.alias,
                                      match.matchday.alias)

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

  # Helper function to add _id to new nested documents
  def add_id_to_scores(scores):
    for score in scores:
      if '_id' not in score:
        score['_id'] = str(ObjectId())

  # Firstly, check if match exists and get this match
  existing_match = await request.app.mongodb["matches"].find_one(
    {"_id": match_id})
  if existing_match is None:
    raise HTTPException(status_code=404,
                        detail=f"Match with id {match_id} not found")
  t_alias = match.tournament.alias if getattr(
    match, 'tournament', None) and getattr(
      match.tournament, 'alias',
      None) else existing_match['tournament']['alias']
  s_alias = match.season.alias if getattr(match, 'season', None) and getattr(
    match.season, 'alias', None) else existing_match['season']['alias']
  r_alias = match.round.alias if getattr(
    match.round, 'alias', None) and getattr(
      match.round, 'alias', None) else existing_match['round']['alias']
  md_alias = match.matchday.alias if getattr(match, 'matchday', None) and getattr(
    match.matchday, 'alias', None) else existing_match['matchday']['alias']
 
  match_status = getattr(
    match.matchStatus, 'key',
    existing_match.get('matchStatus', None).get('key', None))
  finish_type = getattr(
    match.finishType, 'key',
    existing_match.get('finishType', None).get('key', None))

  home_stats = getattr(match.home, 'stats',
                       existing_match.get('home', {}).get(
                         'stats',
                         None))  # if getattr(match, 'home', None) else None
  away_stats = getattr(match.away, 'stats',
                       existing_match.get('away', {}).get(
                         'stats',
                         None))  # if getattr(match, 'away', None) else None

  print("exisiting_match: ", existing_match)
  print("t_alias: ", t_alias)
  print("match_status: ", match_status)
  print("finish_type: ", finish_type)
  print("home_stats: ", home_stats)
  print("away_stats: ", away_stats)
  if finish_type and home_stats and t_alias:
    stats = calc_match_stats(match_status, finish_type,
                             jsonable_encoder(home_stats), await
                             fetch_standings_settings(t_alias))
    if getattr(match, 'home', None) is None:
      match.home = MatchTeamUpdate()
    if getattr(match, 'away', None) is None:
      match.away = MatchTeamUpdate()

    match.home.stats = stats['home']
    match.away.stats = stats['away']

  print("match/after stats: ", match)

  match_data = match.dict(exclude_unset=True)
  match_data.pop("id", None)

  match_data = convert_times_to_seconds(match_data)

  if match_data.get("home") and match_data["home"].get("scores"):
    add_id_to_scores(match_data["home"]["scores"])
  if match_data.get("away") and match_data["away"].get("scores"):
    add_id_to_scores(match_data["away"]["scores"])

  def check_nested_fields(data, existing, path=""):
    for key, value in data.items():
      full_key = f"{path}.{key}" if path else key
      if existing is None or key not in existing:
        match_to_update[full_key] = value
      elif isinstance(value, dict):
        check_nested_fields(value, existing.get(key, {}), full_key)
      else:
        if value != existing.get(key):
          match_to_update[full_key] = value

  match_to_update = {}
  check_nested_fields(match_data, existing_match)

  if match_to_update:
    try:
      set_data = {"$set": flatten_dict(match_to_update)}
      update_result = await request.app.mongodb["matches"].update_one(
        {"_id": match_id}, set_data)

      if update_result.modified_count == 0:
        raise HTTPException(status_code=404,
                            detail=f"Match with id {match_id} not found")
    except Exception as e:
      raise HTTPException(status_code=500, detail=str(e))
  else:
    print("No changes to update")

  # calc standings and set it in round
  await calc_standings_per_round(request.app.mongodb, t_alias, s_alias,
                                 r_alias)
  await calc_standings_per_matchday(request.app.mongodb, t_alias, s_alias, r_alias, md_alias)

  updated_match = await get_match_object(request.app.mongodb, match_id)
  return JSONResponse(status_code=status.HTTP_200_OK,
                      content=jsonable_encoder(updated_match))


# delete match
@router.delete("/{match_id}", response_description="Delete match")
async def delete_match(
  request: Request, match_id: str,
  user_id: str = Depends(auth.auth_wrapper)) -> None:
  # check and get match
  match = await request.app.mongodb["matches"].find_one(
    {"_id": match_id})
  if match is None:
    raise HTTPException(status_code=404,
      detail=f"Match with ID {match_id} not found.")

  try:
    t_alias = match.get('tournament', {}).get('alias', None)
    s_alias = match.get('season', {}).get('alias', None)
    r_alias = match.get('round', {}).get('alias', None)
    md_alias = match.get('matchday', {}).get('alias', None)
    
    # delete in matches
    result = await request.app.mongodb["matches"].delete_one({"_id": match_id})
    if result.deleted_count == 0:
      raise HTTPException(status_code=404,
                          detail=f"Match with id {match_id} not found")
    
    await calc_standings_per_round(request.app.mongodb, t_alias, s_alias, r_alias)
    await calc_standings_per_matchday(request.app.mongodb, t_alias, s_alias, r_alias, md_alias)
      
    return Response(status_code=status.HTTP_204_NO_CONTENT)

  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))
  
