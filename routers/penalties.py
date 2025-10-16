from typing import List
from bson import ObjectId
from fastapi import APIRouter, Request, Body, status, HTTPException, Depends, Path
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from models.matches import PenaltiesBase, PenaltiesDB, PenaltiesUpdate
from authentication import AuthHandler, TokenPayload
from utils import (validate_match_time,
                   calc_player_card_stats,
                   populate_event_player_fields)
from services.stats_service import StatsService

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
    return_data['matchTimeStart'] = validate_match_time(
        return_data['matchSecondsStart'])
  if 'matchSecondsEnd' in return_data and return_data[
      'matchSecondsEnd'] is not None:
    return_data['matchTimeEnd'] = validate_match_time(
        return_data['matchSecondsEnd'])

  # Populate EventPlayer fields
  if return_data.get("penaltyPlayer"):
    await populate_event_player_fields(mongodb, return_data["penaltyPlayer"])

  return PenaltiesDB(**return_data)


# get penalty sheet of a team
@router.get("/",
            response_description="Get penalty sheet",
            response_model=List[PenaltiesDB])
async def get_penalty_sheet(
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

  # Get penalty sheet from match document
  penalties = match.get(team_flag, {}).get("penalties") or []

  for penalty in penalties:
    if 'matchSecondsStart' in penalty:
      penalty['matchTimeStart'] = validate_match_time(
          penalty['matchSecondsStart'])
    if 'matchSecondsEnd' in penalty and penalty['matchSecondsEnd'] is not None:
      penalty['matchTimeEnd'] = validate_match_time(
          penalty['matchSecondsEnd'])
    if penalty.get('penaltyPlayer'):
      penalty['penaltyPlayer'] = await populate_event_player_fields(
          mongodb, penalty['penaltyPlayer'])

  penalty_entries = [PenaltiesDB(**penalty) for penalty in penalties]

  return JSONResponse(status_code=status.HTTP_200_OK,
                      content=jsonable_encoder(penalty_entries))


# create one penalty
@router.post("/",
             response_description="Create one penalty",
             response_model=PenaltiesDB)
async def create_penalty(
    request: Request,
    match_id: str = Path(..., description="The id of the match"),
    team_flag: str = Path(..., description="The flag of the team"),
    penalty: PenaltiesBase = Body(
        ..., description="The penalty to be added to the penaltiesheet"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> JSONResponse:
  mongodb = request.app.state.mongodb

  #check
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
    raise HTTPException(
        status_code=400,
        detail="Penalties can only be added when match status is INPROGRESS")

  # check if player exists in roster
  if not any(player['player']['playerId'] == penalty.penaltyPlayer.playerId
             for player in match.get(team_flag, {}).get('roster', [])):
    raise HTTPException(
        status_code=400,
        detail=f"Player with id {penalty.penaltyPlayer.playerId} not in roster"
    )

  # Get match info for optimizations
  t_alias = match.get('tournament', {}).get('alias')
  s_alias = match.get('season', {}).get('alias')
  r_alias = match.get('round', {}).get('alias')
  md_alias = match.get('matchday', {}).get('alias')
  penalty_player_id = penalty.penaltyPlayer.playerId

  try:
    penalty_data = {}
    new_penalty_id = str(ObjectId())
    penalty_data["_id"] = new_penalty_id
    penalty_data.update(penalty.model_dump())
    penalty_data.pop("id")
    penalty_data["matchSecondsStart"] = validate_match_time(
        penalty_data["matchTimeStart"])
    if penalty_data["matchTimeEnd"] is not None:
      penalty_data["matchSecondsEnd"] = validate_match_time(
          penalty_data['matchTimeEnd'])
    penalty_data = jsonable_encoder(penalty_data)

    # PHASE 1 OPTIMIZATION: Incremental updates instead of full recalculation
    update_operations = {
        "$push": {f"{team_flag}.penalties": penalty_data},
        "$inc": {f"{team_flag}.roster.$[penaltyPlayer].penaltyMinutes": penalty.penaltyMinutes}
    }

    array_filters = [{"penaltyPlayer.player.playerId": penalty_player_id}]

    # Execute the optimized update
    update_result = await mongodb["matches"].update_one(
        {"_id": match_id},
        update_operations,
        array_filters=array_filters
    )

    if update_result.modified_count == 0:
      raise HTTPException(status_code=500, detail="Failed to update match with penalty")

    # PHASE 1 OPTIMIZATION: Skip heavy calculations for INPROGRESS penalties
    if DEBUG_LEVEL > 0:
      print(f"Penalty added with incremental updates - Player: {penalty_player_id}, Minutes: {penalty.penaltyMinutes}")

    # Use the reusable function to return the new penalty
    new_penalty = await get_penalty_object(mongodb, match_id, team_flag, new_penalty_id)
    return JSONResponse(status_code=status.HTTP_201_CREATED,
                        content=jsonable_encoder(new_penalty))

  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))


# get one penalty
@router.get("/{penalty_id}",
            response_description="Get one penalty",
            response_model=PenaltiesDB)
async def get_one_penalty(
    request: Request,
    match_id: str = Path(..., description="The id of the match"),
    penalty_id: str = Path(..., description="The id of the penalty"),
    team_flag: str = Path(..., description="The flag of the team")
) -> JSONResponse:
  mongodb = request.app.state.mongodb
  team_flag = team_flag.lower()
  # Use the reusable function to return the penalty
  penalty = await get_penalty_object(mongodb, match_id, team_flag, penalty_id)

  return JSONResponse(status_code=status.HTTP_200_OK,
                      content=jsonable_encoder(penalty))


# update one penalty
@router.patch("/{penalty_id}",
              response_description="Patch one penalty",
              response_model=PenaltiesDB)
async def patch_one_penalty(
    request: Request,
    match_id: str = Path(..., description="The id of the match"),
    penalty_id: str = Path(..., description="The id of the penalty"),
    team_flag: str = Path(..., description="The flag of the team"),
    penalty: PenaltiesUpdate = Body(
        ..., description="The penalty to be added to the penaltiesheet"),
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
    raise HTTPException(
        status_code=400,
        detail="Penalties can only be modified when match status is INPROGRESS"
    )

  # check if player exists in roster
  if penalty.penaltyPlayer and penalty.penaltyPlayer.playerId:
    if not any(player['player']['playerId'] == penalty.penaltyPlayer.playerId
               for player in match.get(team_flag, {}).get('roster', [])):
      raise HTTPException(
          status_code=400,
          detail=
          f"Player with id {penalty.penaltyPlayer.playerId} not in roster")

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
  penalty_data = penalty.model_dump(exclude_unset=True)
  if 'matchTimeStart' in penalty_data:
    penalty_data['matchSecondsStart'] = validate_match_time(
        penalty_data['matchTimeStart'])
    #penalty_data.pop('matchTimeStart')
  if 'matchTimeEnd' in penalty_data:
    penalty_data['matchSecondsEnd'] = validate_match_time(
        penalty_data['matchTimeEnd'])
    #penalty_data.pop('matchTimeEnd')
  penalty_data = jsonable_encoder(penalty_data)

  update_data = {"$set": {}}
  for key, value in penalty_data.items():
    if current_penalty.get(key) != value:
      update_data["$set"][f"{team_flag}.penalties.$.{key}"] = value

  if update_data.get("$set"):
    try:
      result = await mongodb["matches"].update_one(
          {
              "_id": match_id,
              f"{team_flag}.penalties._id": penalty_id
          }, update_data)
      if result.modified_count == 0:
        raise HTTPException(
            status_code=404,
            detail=f"Penalty with ID {penalty_id} not found in match {match_id}"
        )

      # PHASE 1 OPTIMIZATION: Skip heavy calculations for INPROGRESS matches
      # Only recalculate roster stats (lightweight operation)
      stats_service = StatsService(mongodb)
      await stats_service.calculate_roster_stats(match_id, team_flag)

    except Exception as e:
      raise HTTPException(status_code=500, detail=str(e))
  else:
    if DEBUG_LEVEL > 0:
      print("No update data")
    return Response(status_code=status.HTTP_304_NOT_MODIFIED)

  updated_penalty = await get_penalty_object(mongodb, match_id, team_flag,
                                             penalty_id)

  # PHASE 1 OPTIMIZATION: Skip heavy player calculations for INPROGRESS matches
  return JSONResponse(status_code=status.HTTP_200_OK,
                      content=jsonable_encoder(updated_penalty))


# delete one penalty
@router.delete("/{penalty_id}", response_description="Delete one penalty")
async def delete_one_penalty(
    request: Request,
    match_id: str = Path(..., description="The id of the match"),
    penalty_id: str = Path(..., description="The id of the penalty"),
    team_flag: str = Path(..., description="The flag of the team"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> Response:
  mongodb = request.app.state.mongodb

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
    raise HTTPException(
        status_code=400,
        detail="Penalties can only be deleted when match status is INPROGRESS")

  # Fetch the current penalty before deletion
  current_penalty = None
  for penalty_entry in match.get(team_flag, {}).get("penalties", []):
    if penalty_entry["_id"] == penalty_id:
      current_penalty = penalty_entry
      break

  if current_penalty is None:
    raise HTTPException(
        status_code=404,
        detail=f"Penalty with id {penalty_id} not found in match {match_id}")

  # Get match info for optimizations
  t_alias = match.get('tournament', {}).get('alias')
  s_alias = match.get('season', {}).get('alias')
  r_alias = match.get('round', {}).get('alias')
  md_alias = match.get('matchday', {}).get('alias')
  penalty_player_id = current_penalty.get('penaltyPlayer', {}).get('playerId')
  penalty_minutes = current_penalty.get('penaltyMinutes', 0)

  try:
    # PHASE 1 OPTIMIZATION: Incremental updates instead of full recalculation
    update_operations = {
        "$pull": {f"{team_flag}.penalties": {"_id": penalty_id}},
        "$inc": {f"{team_flag}.roster.$[penaltyPlayer].penaltyMinutes": -penalty_minutes}
    }

    array_filters = [{"penaltyPlayer.player.playerId": penalty_player_id}]

    # Execute the optimized update
    result = await mongodb["matches"].update_one(
        {"_id": match_id, f"{team_flag}.penalties._id": penalty_id},
        update_operations,
        array_filters=array_filters
    )

    if result.modified_count == 0:
      raise HTTPException(
          status_code=404,
          detail=f"Penalty with ID {penalty_id} not found in match {match_id}")

    # PHASE 1 OPTIMIZATION: Skip heavy calculations for INPROGRESS penalties
    if DEBUG_LEVEL > 0:
      print(f"Penalty deleted with incremental updates - Player: {penalty_player_id}, Minutes: {penalty_minutes}")

    return Response(status_code=status.HTTP_204_NO_CONTENT)

  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))