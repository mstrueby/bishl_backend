from typing import List
from bson import ObjectId
from fastapi import APIRouter, Request, Body, status, HTTPException, Depends, Path
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from models.matches import PenaltiesBase, PenaltiesDB, PenaltiesUpdate
from authentication import AuthHandler, TokenPayload
from utils import DEBUG_LEVEL, parse_time_to_seconds, parse_time_from_seconds, fetch_standings_settings, calc_match_stats, calc_standings_per_round, calc_standings_per_matchday, calc_roster_stats, calc_player_card_stats
import os


async def populate_event_player_fields(mongodb, event_player_dict):
  """Populate display fields for EventPlayer from player data"""
  if event_player_dict and event_player_dict.get("playerId"):
    player_doc = await mongodb["players"].find_one({"_id": event_player_dict["playerId"]})
    if player_doc:
      event_player_dict["displayFirstName"] = player_doc.get("displayFirstName")
      event_player_dict["displayLastName"] = player_doc.get("displayLastName")
      event_player_dict["imageUrl"] = player_doc.get("imageUrl")
      event_player_dict["imageVisible"] = player_doc.get("imageVisible")
  return event_player_dict

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
      detail=f"Penalty with ID {penalty_id} not found in match {match_id}"
    )

  return_data = penalty[team_flag]["penalties"][0]
  print("ZZZ return_data: ", return_data)
  # Parse matchSeconds to a string format
  if 'matchSecondsStart' in return_data:
    return_data['matchTimeStart'] = parse_time_from_seconds(
      return_data['matchSecondsStart'])
  if 'matchSecondsEnd' in return_data and return_data[
      'matchSecondsEnd'] is not None:
    return_data['matchTimeEnd'] = parse_time_from_seconds(
      return_data['matchSecondsEnd'])
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
      penalty['matchTimeStart'] = parse_time_from_seconds(
        penalty['matchSecondsStart'])
    if 'matchSecondsEnd' in penalty and penalty[
        'matchSecondsEnd'] is not None:
      penalty['matchTimeEnd'] = parse_time_from_seconds(
        penalty['matchSecondsEnd'])
    if penalty.get('penaltyPlayer'):
        penalty['penaltyPlayer'] = await populate_event_player_fields(mongodb, penalty['penaltyPlayer'])

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

  # Check if match status allows modifications
  match_status = match.get('matchStatus', {}).get('key')
  if match_status != 'INPROGRESS':
    raise HTTPException(
      status_code=400,
      detail="Penalties can only be added when match status is INPROGRESS"
    )

  # check if player exists in roster
  if not any(player['player']['playerId'] == penalty.penaltyPlayer.playerId
         for player in match.get(team_flag, {}).get('roster', [])):
    raise HTTPException(
      status_code=400,
      detail=
      f"Player with id {penalty.penaltyPlayer.playerId} not in roster")

  try:
    penalty_data = {}
    new_penalty_id = str(ObjectId())
    penalty_data["_id"] = new_penalty_id
    penalty_data.update(penalty.dict())
    penalty_data.pop("id")
    print("XXX penalty_data: ", penalty_data)
    penalty_data["matchSecondsStart"] = parse_time_to_seconds(
      penalty_data["matchTimeStart"])
    if penalty_data["matchTimeEnd"] is not None:
      penalty_data["matchSecondsEnd"] = parse_time_to_seconds(
        penalty_data['matchTimeEnd'])
    #penalty_data.pop('matchTimeStart')
    #penalty_data.pop('matchTimeEnd')
    penalty_data = jsonable_encoder(penalty_data)

    update_result = await mongodb["matches"].update_one(
      {"_id": match_id},
      {"$push": {
        f"{team_flag}.penalties": penalty_data
      }})
    if update_result.modified_count == 0:
      raise HTTPException(status_code=500,
                detail="Failed to update match")
    # get the latest player data
    penalty_data['penaltyPlayer'] = await populate_event_player_fields(mongodb, penalty_data['penaltyPlayer'])

    await calc_roster_stats(mongodb, match_id, team_flag)
    await calc_player_card_stats(
      mongodb, [penalty.penaltyPlayer.playerId],
      t_alias=match.get("tournament").get("alias"),
      s_alias=match.get("season").get("alias"),
      r_alias=match.get("round").get("alias"),
      md_alias=match.get("matchday").get("alias"),
      token_payload=token_payload)

    # Use the reusable function to return the new penalty
    new_penalty = await get_penalty_object(mongodb, match_id, team_flag,
                         new_penalty_id)
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
  penalty = await get_penalty_object(mongodb, match_id, team_flag,
                     penalty_id)
  if penalty.penaltyPlayer:
    penalty.penaltyPlayer = await populate_event_player_fields(mongodb, penalty.penaltyPlayer)

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
      detail=
      "Penalties can only be modified when match status is INPROGRESS")

  # check if player exists in roster
  if penalty.penaltyPlayer and penalty.penaltyPlayer.playerId:
    if not any(
        player['player']['playerId'] == penalty.penaltyPlayer.playerId
        for player in match.get(team_flag, {}).get('roster', [])):
      raise HTTPException(
        status_code=400,
        detail=
        f"Player with id {penalty.penaltyPlayer.playerId} not in roster"
      )

  # Fetch the current penalty
  current_penalty = None
  for penalty_entry in match.get(team_flag, {}).get("penalties", []):
    if penalty_entry["_id"] == penalty_id:
      current_penalty = penalty_entry
      break

  if current_penalty is None:
    raise HTTPException(
      status_code=404,
      detail=f"Penalty with id {penalty_id} not found in match {match_id}"
    )

  # Update data
  penalty_data = penalty.dict(exclude_unset=True)
  if 'matchTimeStart' in penalty_data:
    penalty_data['matchSecondsStart'] = parse_time_to_seconds(
      penalty_data['matchTimeStart'])
    #penalty_data.pop('matchTimeStart')
  if 'matchTimeEnd' in penalty_data:
    penalty_data['matchSecondsEnd'] = parse_time_to_seconds(
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
          detail=
          f"Penalty with ID {penalty_id} not found in match {match_id}"
        )
      await calc_roster_stats(mongodb, match_id, team_flag)

    except Exception as e:
      raise HTTPException(status_code=500, detail=str(e))
  else:
    print("No update data")
    return Response(status_code=status.HTTP_304_NOT_MODIFIED)

  updated_penalty = await get_penalty_object(mongodb, match_id, team_flag,
                         penalty_id)

  await calc_player_card_stats(
    mongodb,
    player_ids=[updated_penalty.penaltyPlayer.playerId],
    t_alias=match.get("tournament").get("alias"),
    s_alias=match.get("season").get("alias"),
    r_alias=match.get("round").get("alias"),
    md_alias=match.get("matchday").get("alias"),
    token_payload=token_payload)
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
    raise HTTPException(
      status_code=400,
      detail=
      "Penalties can only be deleted when match status is INPROGRESS")

  # Fetch the current penalty
  current_penalty = None
  for penalty_entry in match.get(team_flag, {}).get("penalties", []):
    if penalty_entry["_id"] == penalty_id:
      current_penalty = penalty_entry
      break

  if current_penalty is None:
    raise HTTPException(
      status_code=404,
      detail=f"Penalty with id {penalty_id} not found in match {match_id}"
    )

  # Delete the penalty
  try:
    result = await mongodb["matches"].update_one(
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
        detail=
        f"Penalty with ID {penalty_id} not found in match {match_id}")
    else:
      await calc_roster_stats(mongodb, match_id, team_flag)
      await calc_player_card_stats(
        mongodb,
        player_ids=[current_penalty['penaltyPlayer'].get('playerId')],
        t_alias=match.get("tournament").get("alias"),
        s_alias=match.get("season").get("alias"),
        r_alias=match.get("round").get("alias"),
        md_alias=match.get("matchday").get("alias"),
        token_payload=token_payload)
      return Response(status_code=status.HTTP_204_NO_CONTENT)

  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))