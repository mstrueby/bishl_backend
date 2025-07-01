# filename: routers/roster.py
from typing import List
from fastapi import APIRouter, Request, Body, Response, status, HTTPException, Depends, Path
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from models.matches import RosterPlayer
from authentication import AuthHandler, TokenPayload
import httpx
import os
from utils import calc_player_card_stats

router = APIRouter()
auth = AuthHandler()
BASE_URL = os.environ['BE_API_URL']


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
  all_players = added_player_ids + list(new_player_ids)
  # temporary process always all players
  all_effected_player_ids = all_players

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

  # do update
  try:
    roster_data = jsonable_encoder(roster)
    await mongodb["matches"].update_one(
        {"_id": match_id}, {"$set": {
            f"{team_flag}.roster": roster_data
        }})
    # print("calc_roster_stats...") - muss nicht
    # await calc_roster_stats(mongodb, match_id, team_flag)
    # print("calc_player_card_stats...")
    # do this only if match_status is INPROGRESS or FINISHED
    if match.get("matchStatus").get("key") in ["INPROGRESS", "FINISHED"]:
      await calc_player_card_stats(
          mongodb,
          player_ids=all_effected_player_ids,
          t_alias=match.get("tournament").get("alias"),
          s_alias=match.get("season").get("alias"),
          r_alias=match.get("round").get("alias"),
          md_alias=match.get("matchday").get("alias"))
      
      # Check calledMatches for affected players and update assignedTeams if needed
      for player_id in all_effected_player_ids:
        try:
          # Get player object from API
          async with httpx.AsyncClient() as client:
            player_response = await client.get(f"{BASE_URL}/players/{player_id}")
            if player_response.status_code == 200:
              player_data = player_response.json()
              
              # Check if player has stats for current tournament/season
              current_team = match.get(team_flag, {}).get("team", {})
              tournament_alias = match.get("tournament", {}).get("alias")
              season_alias = match.get("season", {}).get("alias")
              
              if current_team and tournament_alias and season_alias:
                # Look for stats matching current tournament, season and team
                player_stats = player_data.get("stats", [])
                for stat in player_stats:
                  if (stat.get("tournament", {}).get("alias") == tournament_alias and
                      stat.get("season", {}).get("alias") == season_alias and
                      stat.get("team", {}).get("name") == current_team.get("name") and
                      stat.get("calledMatches", 0) >= 5):
                    
                    # Check if team is already in assignedTeams
                    assigned_teams = player_data.get("assignedTeams", [])
                    team_exists = False
                    
                    for club in assigned_teams:
                      for team in club.get("teams", []):
                        if team.get("teamId") == current_team.get("teamId"):
                          team_exists = True
                          break
                      if team_exists:
                        break
                    
                    # If team doesn't exist, add it with CALLED source
                    if not team_exists:
                      # Find or create club entry
                      current_club = match.get(team_flag, {}).get("club", {})
                      club_found = False
                      
                      for club in assigned_teams:
                        if club.get("clubId") == current_club.get("clubId"):
                          # Add team to existing club
                          new_team = {
                            "teamId": current_team.get("teamId"),
                            "teamName": current_team.get("name"),
                            "teamAlias": current_team.get("alias"),
                            "teamAgeGroup": current_team.get("ageGroup", ""),
                            "teamIshdId": current_team.get("ishdId"),
                            "passNo": "",
                            "source": "CALLED",
                            "modifyDate": None,
                            "active": True,
                            "jerseyNo": None
                          }
                          club["teams"].append(new_team)
                          club_found = True
                          break
                      
                      if not club_found and current_club:
                        # Create new club entry
                        new_club = {
                          "clubId": current_club.get("clubId"),
                          "clubName": current_club.get("name"),
                          "clubAlias": current_club.get("alias"),
                          "clubIshdId": current_club.get("ishdId"),
                          "teams": [{
                            "teamId": current_team.get("teamId"),
                            "teamName": current_team.get("name"),
                            "teamAlias": current_team.get("alias"),
                            "teamAgeGroup": current_team.get("ageGroup", ""),
                            "teamIshdId": current_team.get("ishdId"),
                            "passNo": "",
                            "source": "CALLED",
                            "modifyDate": None,
                            "active": True,
                            "jerseyNo": None
                          }]
                        }
                        assigned_teams.append(new_club)
                      
                      # Update player with new assignedTeams
                      async with httpx.AsyncClient() as update_client:
                        update_response = await update_client.patch(
                          f"{BASE_URL}/players/{player_id}",
                          json={"assignedTeams": assigned_teams}
                        )
                        if update_response.status_code == 200:
                          print(f"Added CALLED team assignment for player {player_id}")
                    break
        except Exception as e:
          print(f"Error processing called matches for player {player_id}: {str(e)}")
          # Continue with other players if one fails
          continue
    
    #async with httpx.AsyncClient() as client:
    #  return await client.get(f"{BASE_URL}/matches/{match_id}/{team_flag}/roster/")
    return await get_roster(request, match_id, team_flag)

  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))
