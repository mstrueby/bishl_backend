# filename: routers/scores.py
from typing import List
from bson import ObjectId
from fastapi import APIRouter, Request, Body, status, HTTPException, Depends, Path
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from models.matches import ScoresBase, ScoresUpdate, ScoresDB
from authentication import AuthHandler, TokenPayload
from utils import parse_time_to_seconds, parse_time_from_seconds, fetch_standings_settings, calc_match_stats, calc_standings_per_round, calc_standings_per_matchday, calc_roster_stats, calc_player_card_stats
import os

router = APIRouter()
auth = AuthHandler()

BASE_URL = os.environ['BE_API_URL']


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

  if not score or not score.get(team_flag
                                or "scores" not in score.get(team_flag)):
    raise HTTPException(
        status_code=404,
        detail=f"Score with ID {score_id} not found in match {match_id}")

  return_data = score[team_flag]["scores"][0]

  # Parse matchSeconds to a string format
  if 'matchSeconds' in return_data:
    return_data['matchTime'] = parse_time_from_seconds(
        return_data['matchSeconds'])
  return ScoresDB(**return_data)


# get score sheet of a team
@router.get("/",
            response_description="Get score sheet",
            response_model=List[ScoresDB])
async def get_score_sheet(
    request: Request,
    match_id: str = Path(..., description="The ID of the match"),
    team_flag: str = Path(..., description="The team flag (home/away)"),
) -> JSONResponse:
  mongodb = request.app.state.mongodb
  team_flag = team_flag.lower()
  if team_flag not in ["home", "away"]:
    raise HTTPException(status_code=400, detail="Invalid team flag")

  match = await mongodb["matches"].find_one({"_id": match_id})
  if match is None:
    raise HTTPException(status_code=404,
                        detail=f"Match with ID {match_id} not found")

  # Get score sheet from match document
  scores = match.get(team_flag, {}).get("scores") or []

  # Parse matchSeconds to a string format
  print("scores", scores)
  for score in scores:
    if 'matchSeconds' in score:
      score['matchTime'] = parse_time_from_seconds(score['matchSeconds'])

  score_entries = [ScoresDB(**score) for score in scores]

  return JSONResponse(status_code=status.HTTP_200_OK,
                      content=jsonable_encoder(score_entries))


# create one score
@router.post("/",
             response_description="Create one score",
             response_model=ScoresDB)
async def create_score(
    request: Request,
    match_id: str = Path(..., description="The id of the match"),
    team_flag: str = Path(..., description="The flag of the team"),
    score: ScoresBase = Body(
        ..., description="The score to be added to the scoresheet"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> JSONResponse:
  mongodb = request.app.state.mongodb
  #if "ADMIN" not in token_payload.roles:
  #  raise HTTPException(status_code=403, detail="Nicht authorisiert")
  #check
  team_flag = team_flag.lower()
  if team_flag not in ["home", "away"]:
    raise HTTPException(status_code=400, detail="Invalid team flag")
  match = await mongodb["matches"].find_one({"_id": match_id})
  if match is None:
    raise HTTPException(status_code=404,
                        detail=f"Match with id {match_id} not found")
  print("match precheck: ", match)

  #check if score player is in roster
  if score.goalPlayer and score.goalPlayer.playerId:
    if not any(player['player']['playerId'] == score.goalPlayer.playerId
               for player in match.get(team_flag, {}).get('roster') or []):
      raise HTTPException(
          status_code=400,
          detail=f'Goal player {score.goalPlayer.playerId} not in roster')

  if score.assistPlayer and score.assistPlayer.playerId:
    if not any(player['player']['playerId'] == score.assistPlayer.playerId
               for player in match.get(team_flag, {}).get('roster') or []):
      raise HTTPException(
          status_code=400,
          detail=f'Assist player {score.assistPlayer.playerId} not in roster')

  # set new score
  if team_flag == 'home':
    match['home']['stats']['goalsFor'] += 1
    match['away']['stats']['goalsAgainst'] += 1
  else:
    match['away']['stats']['goalsFor'] += 1
    match['home']['stats']['goalsAgainst'] += 1

  #check
  match_status = match.get('matchStatus').get('key')
  finish_type = match.get('finishType').get('key')
  home_stats = match.get('home', {}).get('stats', {})
  t_alias = match.get('tournament', {}).get('alias')
  s_alias = match.get('season', {}).get('alias')
  r_alias = match.get('round', {}).get('alias')
  md_alias = match.get('matchday', {}).get('alias')
  goal_player_id = score.goalPlayer.playerId if score.goalPlayer else None
  assist_player_id = score.assistPlayer.playerId if score.assistPlayer else None
  player_ids = [goal_player_id, assist_player_id]

  if finish_type and home_stats and t_alias:
    stats = calc_match_stats(match_status=jsonable_encoder(match_status),
                             finish_type=jsonable_encoder(finish_type),
                             home_score=home_stats.get('goalsFor', 0),
                             away_score=home_stats.get('goalsAgainst', 0),
                             standings_setting=await
                             fetch_standings_settings(t_alias, s_alias))

    match['home']['stats'] = stats['home']
    match['away']['stats'] = stats['away']
    print("score/match: ", match)

  try:
    score_data = {}
    new_score_id = str(ObjectId())
    score_data['_id'] = new_score_id
    score_data.update(score.dict())
    score_data.pop('id')

    score_data['matchSeconds'] = parse_time_to_seconds(
        score_data['matchTime'])
    score_data = jsonable_encoder(score_data)
    #score_data.pop('matchTime')
    print("XXX score_data: ", score_data)

    update_result = await mongodb['matches'].update_one(
        {"_id": match_id},
        {
            "$push": {
                f"{team_flag}.scores": score_data
            },
            #"$inc": {
            #  f"{team_flag}.stats.goalsFor": 1,
            #  f"{'home' if team_flag == 'away' else 'away'}.stats.goalsAgainst": 1
            #},
            "$set": {
                "home.stats": match['home']['stats'],
                "away.stats": match['away']['stats']
            }
        })
    print("XXX update_result: ", update_result)
    if update_result.modified_count == 0:
      raise HTTPException(
          status_code=500,
          detail="Failed to update match (scores and goalsFor/goalsAgainst)")

    # calc standings
    await calc_standings_per_round(mongodb, t_alias, s_alias, r_alias)
    await calc_standings_per_matchday(mongodb, t_alias, s_alias, r_alias,
                                      md_alias)

    # Use the reusable function to fetch and update roster
    await calc_roster_stats(mongodb, match_id, team_flag)
    player_ids = [player_id for player_id in player_ids if player_id]
    await calc_player_card_stats(mongodb, player_ids, t_alias, s_alias,
                                 r_alias, md_alias)

    # Use the reusable function to return the new score
    new_score = await get_score_object(mongodb, match_id, team_flag,
                                       new_score_id)
    return JSONResponse(status_code=status.HTTP_201_CREATED,
                        content=jsonable_encoder(new_score))

  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))


# get one score
@router.get("/{score_id}",
            response_description="Get one score",
            response_model=ScoresDB)
async def get_one_score(
    request: Request,
    match_id: str = Path(..., description="The id of the match"),
    score_id: str = Path(..., description="The id of the score"),
    team_flag: str = Path(..., description="The flag of the team")
) -> JSONResponse:
  mongodb = request.app.state.mongodb
  team_flag = team_flag.lower()
  # Use the reusable function to return the score
  score = await get_score_object(mongodb, match_id, team_flag, score_id)
  return JSONResponse(status_code=status.HTTP_200_OK,
                      content=jsonable_encoder(score))


# update one score
@router.patch("/{score_id}",
              response_description="Patch one score",
              response_model=ScoresDB)
async def patch_one_score(
    request: Request,
    match_id: str = Path(..., description="The id of the match"),
    score_id: str = Path(..., description="The id of the score"),
    team_flag: str = Path(..., description="The flag of the team"),
    score: ScoresUpdate = Body(
        ..., description="The score to be added to the scoresheet"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper)):
  mongodb = request.app.state.mongodb
  #if "ADMIN" not in token_payload.roles:
  #  raise HTTPException(status_code=403, detail="Nicht authorisiert")
  # Data validation and conversion
  team_flag = team_flag.lower()
  if team_flag not in ["home", "away"]:
    raise HTTPException(status_code=400, detail="Invalid team flag")
  match = await mongodb["matches"].find_one({"_id": match_id})
  if match is None:
    raise HTTPException(status_code=404,
                        detail=f"Match with id {match_id} not found")

  # Check if match status allows modifications
  match_status = match.get('matchStatus', {}).get('key')
  if match_status != 'INPROGRESS':
    raise HTTPException(status_code=400, 
                        detail="Scores can only be modified when match status is INPROGRESS")

  #check if score player is in roster
  if score.goalPlayer and score.goalPlayer.playerId:
    if not any(player['player']['playerId'] == score.goalPlayer.playerId
               for player in match.get(team_flag, {}).get('roster', [])):
      raise HTTPException(
          status_code=400,
          detail=f'Goal player {score.goalPlayer.playerId} not in roster')

  # Check assist player only if it's not None and has a playerId
  if score.assistPlayer is not None and score.assistPlayer.playerId:
    if not any(player['player']['playerId'] == score.assistPlayer.playerId
               for player in match.get(team_flag, {}).get('roster', [])):
      raise HTTPException(
          status_code=400,
          detail=f'Assist player {score.assistPlayer.playerId} not in roster')

  # Fetch the current score
  current_score = None
  for score_entry in match.get(team_flag, {}).get("scores", []):
    if score_entry["_id"] == score_id:
      current_score = score_entry
      print("found score: ", current_score)
      break

  if current_score is None:
    raise HTTPException(
        status_code=404,
        detail=f"Score with id {score_id} not found in match {match_id}")

  # Update data
  score_data = score.dict()
  score_data.pop('id', None)
  if 'matchTime' in score_data:
    score_data['matchSeconds'] = parse_time_to_seconds(
        score_data['matchTime'])
  #score_data.pop('matchTime')
  score_data = jsonable_encoder(score_data)
  goal_player_id = score_data.get('goalPlayer', {}).get('playerId') if score_data.get('goalPlayer') else None
  assist_player_id = score_data.get('assistPlayer', {}).get('playerId') if score_data.get('assistPlayer') else None
  player_ids = [player_id for player_id in [goal_player_id, assist_player_id] if player_id]
  print("score_data: ", score_data)

  update_data = {"$set": {}}
  for key, value in score_data.items():
    update_data["$set"][f"{team_flag}.scores.$.{key}"] = value

  print("update_data: ", update_data)
  if update_data.get("$set"):
    try:
      result = await mongodb["matches"].update_one(
          {
              "_id": match_id,
              f"{team_flag}.scores._id": score_id
          }, update_data)
      await calc_roster_stats(mongodb, match_id, team_flag)
      await calc_player_card_stats(
          mongodb,
          player_ids=player_ids,
          t_alias=match.get("tournament").get("alias"),
          s_alias=match.get("season").get("alias"),
          r_alias=match.get("round").get("alias"),
          md_alias=match.get("matchday").get("alias"))

    except HTTPException as e:
      if e.status_code == status.HTTP_304_NOT_MODIFIED:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED)
      raise
    except Exception as e:
      raise HTTPException(status_code=500, detail=str(e))
  else:
    print("No update data")
    return Response(status_code=status.HTTP_304_NOT_MODIFIED)

  # Use the reusable function to return the updated score
  updated_score = await get_score_object(mongodb, match_id, team_flag,
                                         score_id)
  return JSONResponse(status_code=status.HTTP_200_OK,
                      content=jsonable_encoder(updated_score))


# delete one score
@router.delete("/{score_id}", response_description="Delete one score")
async def delete_one_score(
    request: Request,
    match_id: str = Path(..., description="The id of the match"),
    score_id: str = Path(..., description="The id of the score"),
    team_flag: str = Path(..., description="The flag of the team"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> Response:
  mongodb = request.app.state.mongodb
  #if "ADMIN" not in token_payload.roles:
  #  raise HTTPException(status_code=403, detail="Nicht authorisiert")
  team_flag = team_flag.lower()
  if team_flag not in ["home", "away"]:
    raise HTTPException(status_code=400, detail="Invalid team flag")
  match = await mongodb["matches"].find_one({"_id": match_id})
  if match is None:
    raise HTTPException(status_code=404,
                        detail=f"Match with id {match_id} not found")

  # Check if match status allows modifications
  match_status = match.get('matchStatus', {}).get('key')
  if match_status != 'INPROGRESS':
    raise HTTPException(status_code=400, 
                        detail="Scores can only be modified when match status is INPROGRESS")

  # set new score
  if team_flag == 'home':
    match['home']['stats']['goalsFor'] -= 1
    match['away']['stats']['goalsAgainst'] -= 1
  else:
    match['away']['stats']['goalsFor'] -= 1
    match['home']['stats']['goalsAgainst'] -= 1
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

  # check
  match_status = match.get('matchStatus').get('key')
  finish_type = match.get('finishType').get('key')
  home_stats = match.get('home', {}).get('stats', {})
  t_alias = match.get('tournament', {}).get('alias')
  s_alias = match.get('season', {}).get('alias')
  r_alias = match.get('round', {}).get('alias')
  md_alias = match.get('matchday', {}).get('alias')
  goal_player_id = current_score.get('goalPlayer', {}).get('playerId')

  # Safely handle assistPlayer which might be None
  assist_player = current_score.get('assistPlayer')
  assist_player_id = assist_player.get('playerId') if assist_player else None

  player_ids = [pid for pid in [goal_player_id, assist_player_id] if pid]

  if finish_type and home_stats and t_alias:
    stats = calc_match_stats(match_status=jsonable_encoder(match_status),
                             finish_type=jsonable_encoder(finish_type),
                             home_score=home_stats.get('goalsFor', 0),
                             away_score=home_stats.get('goalsAgainst', 0),
                             standings_setting=await
                             fetch_standings_settings(t_alias, s_alias))
    match['home']['stats'] = stats['home']
    match['away']['stats'] = stats['away']
    print("del score/match: ", match)

  # Delete the score
  try:
    result = await mongodb["matches"].update_one(
        {
            "_id": match_id,
            f"{team_flag}.scores._id": score_id
        }, {
            "$pull": {
                f"{team_flag}.scores": {
                    "_id": score_id
                }
            },
            "$set": {
                "home.stats": match.get("home", {}).get("stats", {}),
                "away.stats": match.get("away", {}).get("stats", {})
            }
        })
    if result.modified_count == 0:
      raise HTTPException(
          status_code=404,
          detail=f"Score with ID {score_id} not found in match {match_id}")

    await calc_standings_per_round(mongodb, t_alias, s_alias, r_alias)
    await calc_standings_per_matchday(mongodb, t_alias, s_alias, r_alias,
                                      md_alias)
    await calc_roster_stats(mongodb, match_id, team_flag)
    await calc_player_card_stats(mongodb, player_ids, t_alias, s_alias,
                                 r_alias, md_alias)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))