# filename: routers/roster.py
from typing import List
from fastapi import APIRouter, Request, Body, Response, status, HTTPException, Depends, Path
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from models.matches import RosterPlayer
from authentication import AuthHandler, TokenPayload
import httpx
import os
from utils import calc_player_card_stats, populate_event_player_fields

router = APIRouter()
auth = AuthHandler()
BASE_URL = os.environ['BE_API_URL']
DEBUG_LEVEL = int(os.environ.get('DEBUG_LEVEL', 0))

# get roster of a team
@router.get("/",
            response_description="Get roster of a team",
            response_model=List[RosterPlayer])
async def get_roster(
    request: Request,
    match_id: str = Path(..., description="The match id of the roster"),
    team_flag: str = Path(
        ..., description="The team flag (home/away) of the roster")
) -> JSONResponse:
  mongodb = request.app.state.mongodb
  team_flag = team_flag.lower()
  if team_flag not in ["home", "away"]:
    raise HTTPException(status_code=400, detail="Invalid team flag")
  match = await mongodb["matches"].find_one({"_id": match_id})
  if match is None:
    raise HTTPException(status_code=404,
                        detail=f"Match with id {match_id} not found")

  roster = match.get(team_flag, {}).get("roster") or []

  if not isinstance(roster, list):
    raise HTTPException(status_code=500,
                        detail="Unexpected data structure in roster")
  
  # Populate display fields from player data
  for roster_entry in roster:
    if roster_entry.get("player"):
      await populate_event_player_fields(mongodb, roster_entry["player"])
  
  roster_players = [RosterPlayer(**player) for player in roster]
  return JSONResponse(status_code=status.HTTP_200_OK,
                      content=jsonable_encoder(roster_players))


# update roster of a team
@router.put("/",
            response_description="Update roster of a team",
            response_model=List[RosterPlayer])
async def update_roster(
    request: Request,
    match_id: str = Path(..., description="The match id of the roster"),
    team_flag: str = Path(
        ..., description="The team flag (home/away) of the roster"),
    roster: List[RosterPlayer] = Body(...,
                                      description="The roster to be updated"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> Response:
  mongodb = request.app.state.mongodb
  if not any(role in token_payload.roles
             for role in ["ADMIN", "LEAGUE_ADMIN", "CLUB_ADMIN"]):
    raise HTTPException(status_code=403, detail="Nicht authorisiert")
  print("new roster: ", roster)
  team_flag = team_flag.lower()
  if team_flag not in ["home", "away"]:
    raise HTTPException(status_code=400, detail="Invalid team flag")
  match = await mongodb["matches"].find_one({"_id": match_id})
  if match is None:
    raise HTTPException(status_code=404,
                        detail=f"Match with id {match_id} not found")

  # check if any player from the new roster exists in scores or penalties array of the match
  scores = match.get(team_flag, {}).get("scores") or []
  penalties = match.get(team_flag, {}).get("penalties") or []
  existing_player_ids = {
      player['player']['playerId']
      for player in (match.get(team_flag, {}).get('roster') or [])
  }
  new_player_ids = {player.player.playerId for player in roster}
  added_player_ids = list(new_player_ids - existing_player_ids)
  removed_player_ids = list(existing_player_ids - new_player_ids)
  all_effected_player_ids = added_player_ids + removed_player_ids
  all_players = removed_player_ids + list(new_player_ids)
  # temporary process always all players:
  all_effected_player_ids = all_players
  if DEBUG_LEVEL > 10:
    print("xxx new player_ids: ", new_player_ids)
    print("xxx added_player_ids: ", added_player_ids)
    print("xxx removed_player_ids: ", removed_player_ids)
    print("all_effected_player_ids: ", all_effected_player_ids)

  for score in scores:
    if score['goalPlayer']['playerId'] not in new_player_ids or \
       (score['assistPlayer'] and score['assistPlayer']['playerId'] not in new_player_ids):
      raise HTTPException(
          status_code=400,
          detail=
          "Roster can not be updated. All players in scores must be in roster")

  for penalty in penalties:
    if penalty['penaltyPlayer']['playerId'] not in new_player_ids:
      raise HTTPException(
          status_code=400,
          detail=
          "Roster can not be updated. All players in penalties must be in roster"
      )

  # Populate display fields from player data before saving
  roster_data = jsonable_encoder(roster)
  for roster_entry in roster_data:
    if roster_entry.get("player"):
      await populate_event_player_fields(mongodb, roster_entry["player"])

  # do update
  try:
    await mongodb["matches"].update_one(
        {"_id": match_id}, {"$set": {
            f"{team_flag}.roster": roster_data
        }})
    # print("calc_roster_stats...") - muss nicht
    # await calc_roster_stats(mongodb, match_id, team_flag)
    print("xxx calc_player_card_stats...")
    # do this only if match_status is INPROGRESS or FINISHED
    if match.get("matchStatus").get("key") in ["INPROGRESS", "FINISHED"]:
      await calc_player_card_stats(
          mongodb,
          player_ids=all_effected_player_ids,
          t_alias=match.get("tournament").get("alias"),
          s_alias=match.get("season").get("alias"),
          r_alias=match.get("round").get("alias"),
          md_alias=match.get("matchday").get("alias"),
          token_payload=token_payload)
    
    #async with httpx.AsyncClient() as client:
    #  return await client.get(f"{BASE_URL}/matches/{match_id}/{team_flag}/roster/")
    return await get_roster(request, match_id, team_flag)

  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))
