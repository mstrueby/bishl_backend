# filename: routers/matches.py
from fastapi import APIRouter, Request, Body, status, HTTPException, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse, Response
from typing import List, Optional
from models.matches import MatchBase, MatchDB, MatchUpdate, MatchTeamUpdate, MatchStats, MatchTeam, MatchListBase
from authentication import AuthHandler, TokenPayload
from utils import my_jsonable_encoder, parse_time_to_seconds, parse_time_from_seconds, fetch_standings_settings, calc_match_stats, flatten_dict, calc_standings_per_round, calc_standings_per_matchday, fetch_ref_points, calc_roster_stats, calc_player_card_stats, get_sys_ref_tool_token, populate_event_player_fields
import os
import isodate
from datetime import datetime, timedelta
from bson import ObjectId
import httpx

router = APIRouter()
auth = AuthHandler()
BASE_URL = os.environ.get('BE_API_URL')
DEBUG_LEVEL = int(os.environ.get('DEBUG_LEVEL', 0))


# Prepare to convert matchSeconds to seconds for accurate comparison
def convert_times_to_seconds(data):
  for score in data.get("home", {}).get("scores", []) or []:
    score["matchSeconds"] = parse_time_to_seconds(score["matchTime"])
  for score in data.get("away", {}).get("scores", []) or []:
    score["matchSeconds"] = parse_time_to_seconds(score["matchTime"])
  for penalty in data.get("home", {}).get("penalties", []) or []:
    penalty["matchSecondsStart"] = parse_time_to_seconds(
        penalty["matchTimeStart"])
    if penalty.get('matchTimeEnd') is not None:
      penalty["matchSecondsEnd"] = parse_time_to_seconds(
          penalty["matchTimeEnd"])
  for penalty in data.get("away", {}).get("penalties", []) or []:
    penalty["matchSecondsStart"] = parse_time_to_seconds(
        penalty["matchTimeStart"])
    if penalty.get('matchTimeEnd') is not None:
      penalty["matchSecondsEnd"] = parse_time_to_seconds(
          penalty["matchTimeEnd"])
  return data


def convert_seconds_to_times(data):
  for score in (data.get("home", {}).get("scores") or []):
    if score is not None:
      score["matchTime"] = parse_time_from_seconds(score["matchSeconds"])
  for score in (data.get("away", {}).get("scores") or []):
    if score is not None:
      score["matchTime"] = parse_time_from_seconds(score["matchSeconds"])
  # parse penalties.matchSeconds[Start|End] to a string format
  for penalty in (data.get("home", {}).get("penalties") or []):
    if penalty is not None:
      penalty["matchTimeStart"] = parse_time_from_seconds(
          penalty["matchSecondsStart"])
      if penalty.get('matchSecondsEnd') is not None:
        penalty["matchTimeEnd"] = parse_time_from_seconds(
            penalty["matchSecondsEnd"])
  for penalty in (data.get("away", {}).get("penalties") or []):
    if penalty is not None:
      penalty["matchTimeStart"] = parse_time_from_seconds(
          penalty["matchSecondsStart"])
      if penalty.get('matchSecondsEnd') is not None:
        penalty["matchTimeEnd"] = parse_time_from_seconds(
            penalty["matchSecondsEnd"])
  if DEBUG_LEVEL > 100:
    print("data", data)
  return data


async def get_match_object(mongodb, match_id: str) -> MatchDB:
  match = await mongodb["matches"].find_one({"_id": match_id})
  if not match:
    raise HTTPException(status_code=404,
                        detail=f"Match with id {match_id} not found")

  # Populate EventPlayer display fields for scores and penalties
  for team_key in ["home", "away"]:
    team = match.get(team_key, {})

    # Populate roster player fields
    roster = team.get("roster", [])
    for roster_entry in roster:
      if roster_entry.get("player"):
        await populate_event_player_fields(mongodb, roster_entry["player"])

    # Populate score player fields
    scores = team.get("scores", [])
    for score in scores:
      if score.get("goalPlayer"):
        await populate_event_player_fields(mongodb, score["goalPlayer"])
      if score.get("assistPlayer"):
        await populate_event_player_fields(mongodb, score["assistPlayer"])

    # Populate penalty player fields
    penalties = team.get("penalties", [])
    for penalty in penalties:
      if penalty.get("penaltyPlayer"):
        await populate_event_player_fields(mongodb, penalty["penaltyPlayer"])

  # parse scores.matchSeconds to a string format
  match = convert_seconds_to_times(match)
  return MatchDB(**match)


async def update_round_and_matchday(client, headers, t_alias, s_alias, r_alias,
                                    round_id, md_id):
  # Update round dates first
  round_response = await client.patch(
      f"{BASE_URL}/tournaments/{t_alias}/seasons/{s_alias}/rounds/{round_id}",
      json={},
      headers=headers,
      timeout=30.0)
  if round_response.status_code not in [200, 304]:
    print(
        f"Warning: Failed to update round dates: {round_response.status_code}")
    return

  # After successful round update, update matchday
  matchday_response = await client.patch(
      f"{BASE_URL}/tournaments/{t_alias}/seasons/{s_alias}/rounds/{r_alias}/matchdays/{md_id}",
      json={},
      headers=headers,
      timeout=30.0)
  if matchday_response.status_code not in [200, 304]:
    print(
        f"Warning: Failed to update matchday dates: {matchday_response.status_code}"
    )


# get today's matches
@router.get("/today",
            response_model=List[MatchListBase],
            response_description="Get today's matches")
async def get_todays_matches(request: Request,
                            tournament: Optional[str] = None,
                            season: Optional[str] = None,
                            round: Optional[str] = None,
                            matchday: Optional[str] = None,
                            referee: Optional[str] = None,
                            club: Optional[str] = None,
                            team: Optional[str] = None,
                            assigned: Optional[bool] = None) -> JSONResponse:
  mongodb = request.app.state.mongodb

  # Get today's date range
  today = datetime.now().date()
  start_of_day = datetime.combine(today, datetime.min.time())
  end_of_day = datetime.combine(today, datetime.max.time())

  query = {
    "season.alias": season if season else os.environ['CURRENT_SEASON'],
    "startDate": {
      "$gte": start_of_day,
      "$lte": end_of_day
    }
  }

  if tournament:
    query["tournament.alias"] = tournament
  if round:
    query["round.alias"] = round
  if matchday:
    query["matchday.alias"] = matchday
  if referee:
    query["$or"] = [{"referee1.userId": referee}, {"referee2.userId": referee}]
  if club:
    if team:
      query["$or"] = [{
          "$and": [{
              "home.clubAlias": club
          }, {
              "home.teamAlias": team
          }]
      }, {
          "$and": [{
              "away.clubAlias": club
          }, {
              "away.teamAlias": team
          }]
      }]
    else:
      query["$or"] = [{"home.clubAlias": club}, {"away.clubAlias": club}]
  if assigned is not None:
    if not assigned:  # assigned == False
      query["$and"] = [{
          "referee1.userId": {
              "$exists": False
          }
      }, {
          "referee2.userId": {
              "$exists": False
          }
      }]
    elif assigned:  # assigned == True
      query["$or"] = [{
          "referee1.userId": {
              "$exists": True
          }
      }, {
          "referee2.userId": {
              "$exists": True
          }
      }]

  if DEBUG_LEVEL > 20:
    print("today's matches query: ", query)

  # Project only necessary fields, excluding roster, scores, and penalties
  projection = {
    "home.roster": 0,
    "home.scores": 0,
    "home.penalties": 0,
    "away.roster": 0,
    "away.scores": 0,
    "away.penalties": 0
  }

  matches = await mongodb["matches"].find(query, projection).sort("startDate", 1).to_list(None)

  # Convert to MatchListBase objects and parse time fields
  results = []
  for match in matches:
    match = convert_seconds_to_times(match)
    results.append(MatchListBase(**match))

  return JSONResponse(status_code=status.HTTP_200_OK,
                      content=jsonable_encoder(results))


# get upcoming matches (next day with matches)
@router.get("/upcoming",
            response_model=List[MatchListBase],
            response_description="Get upcoming matches for next day where matches exist")
async def get_upcoming_matches(request: Request,
                              tournament: Optional[str] = None,
                              season: Optional[str] = None,
                              round: Optional[str] = None,
                              matchday: Optional[str] = None,
                              referee: Optional[str] = None,
                              club: Optional[str] = None,
                              team: Optional[str] = None,
                              assigned: Optional[bool] = None) -> JSONResponse:
  mongodb = request.app.state.mongodb

  # Get current time and start searching from tomorrow
  today = datetime.now()
  tomorrow_start = datetime.combine(today.date() + timedelta(days=1), datetime.min.time())

  # Build base query to find minimum start date
  base_query = {
    "season.alias": season if season else os.environ['CURRENT_SEASON'],
    "startDate": {"$gte": tomorrow_start}
  }

  if tournament:
    base_query["tournament.alias"] = tournament
  if round:
    base_query["round.alias"] = round
  if matchday:
    base_query["matchday.alias"] = matchday
  if referee:
    base_query["$or"] = [{"referee1.userId": referee}, {"referee2.userId": referee}]
  if club:
    if team:
      base_query["$or"] = [{
          "$and": [{
              "home.clubAlias": club
          }, {
              "home.teamAlias": team
          }]
      }, {
          "$and": [{
              "away.clubAlias": club
          }, {
              "away.teamAlias": team
          }]
      }]
    else:
      base_query["$or"] = [{"home.clubAlias": club}, {"away.clubAlias": club}]
  if assigned is not None:
    if not assigned:  # assigned == False
      base_query["$and"] = [{
          "referee1.userId": {
              "$exists": False
          }
      }, {
          "referee2.userId": {
              "$exists": False
          }
      }]
    elif assigned:  # assigned == True
      base_query["$or"] = [{
          "referee1.userId": {
              "$exists": True
          }
      }, {
          "referee2.userId": {
              "$exists": True
          }
      }]

  if DEBUG_LEVEL > 20:
    print("upcoming matches base query: ", base_query)

  # Find the minimum start date for upcoming matches
  min_date_result = await mongodb["matches"].find(base_query).sort("startDate", 1).limit(1).to_list(1)

  if not min_date_result:
    # No upcoming matches found
    return JSONResponse(status_code=status.HTTP_200_OK,
                        content=jsonable_encoder([]))

  min_start_date = min_date_result[0]["startDate"]
  match_date = min_start_date.date()

  # Create date range for the found date
  start_of_day = datetime.combine(match_date, datetime.min.time())
  end_of_day = datetime.combine(match_date, datetime.max.time())

  # Build final query for matches on the found date
  final_query = base_query.copy()
  final_query["startDate"] = {
    "$gte": start_of_day,
    "$lte": end_of_day
  }

  if DEBUG_LEVEL > 20:
    print(f"upcoming matches final query for {match_date}: ", final_query)

  # Project only necessary fields, excluding roster, scores, and penalties
  projection = {
    "home.roster": 0,
    "home.scores": 0,
    "home.penalties": 0,
    "away.roster": 0,
    "away.scores": 0,
    "away.penalties": 0
  }

  matches = await mongodb["matches"].find(final_query, projection).sort("startDate", 1).to_list(None)

  # Convert to MatchListBase objects and parse time fields
  results = []
  for match in matches:
    match = convert_seconds_to_times(match)
    results.append(MatchListBase(**match))

  return JSONResponse(status_code=status.HTTP_200_OK,
                      content=jsonable_encoder(results))


# get this week's matches (tomorrow until Sunday)
@router.get("/rest-of-week",
            response_description="Get matches for rest of current week (tomorrow until Sunday)")
async def get_rest_of_week_matches(request: Request,
                               tournament: Optional[str] = None,
                               season: Optional[str] = None,
                               round: Optional[str] = None,
                               matchday: Optional[str] = None,
                               referee: Optional[str] = None,
                               club: Optional[str] = None,
                               team: Optional[str] = None,
                               assigned: Optional[bool] = None) -> JSONResponse:
  mongodb = request.app.state.mongodb

  # Get current date and calculate tomorrow and end of week (Sunday)
  today = datetime.now().date()
  tomorrow = today + timedelta(days=1)

  # Calculate days until Sunday (0=Monday, 6=Sunday)
  days_until_sunday = 6 - today.weekday()
  if days_until_sunday <= 0:  # If today is Sunday, get next Sunday
    days_until_sunday = 7

  end_of_week = today + timedelta(days=days_until_sunday)

  # Build base query
  base_query = {
    "season.alias": season if season else os.environ['CURRENT_SEASON']
  }

  if tournament:
    base_query["tournament.alias"] = tournament
  if round:
    base_query["round.alias"] = round
  if matchday:
    base_query["matchday.alias"] = matchday
  if referee:
    base_query["$or"] = [{"referee1.userId": referee}, {"referee2.userId": referee}]
  if club:
    if team:
      base_query["$or"] = [{
          "$and": [{
              "home.clubAlias": club
          }, {
              "home.teamAlias": team
          }]
      }, {
          "$and": [{
              "away.clubAlias": club
          }, {
              "away.teamAlias": team
          }]
      }]
    else:
      base_query["$or"] = [{"home.clubAlias": club}, {"away.clubAlias": club}]
  if assigned is not None:
    if not assigned:  # assigned == False
      base_query["$and"] = [{
          "referee1.userId": {
              "$exists": False
          }
      }, {
          "referee2.userId": {
              "$exists": False
          }
      }]
    elif assigned:  # assigned == True
      base_query["$or"] = [{
          "referee1.userId": {
              "$exists": True
          }
      }, {
          "referee2.userId": {
              "$exists": True
          }
      }]

  if DEBUG_LEVEL > 20:
    print("this week matches base query: ", base_query)

  # Initialize result structure
  week_matches = []

  # Loop through each day from tomorrow until Sunday
  current_date = tomorrow
  while current_date <= end_of_week:
    start_of_day = datetime.combine(current_date, datetime.min.time())
    end_of_day = datetime.combine(current_date, datetime.max.time())

    # Build query for this specific day
    day_query = base_query.copy()
    day_query["startDate"] = {
      "$gte": start_of_day,
      "$lte": end_of_day
    }

    if DEBUG_LEVEL > 20:
      print(f"this week matches query for {current_date}: ", day_query)

    # Project only necessary fields, excluding roster, scores, and penalties
    projection = {
      "home.roster": 0,
      "home.scores": 0,
      "home.penalties": 0,
      "away.roster": 0,
      "away.scores": 0,
      "away.penalties": 0
    }

    matches = await mongodb["matches"].find(day_query, projection).sort("startDate", 1).to_list(None)

    # Convert to MatchListBase objects and parse time fields
    day_matches = []
    for match in matches:
      match = convert_seconds_to_times(match)
      day_matches.append(MatchListBase(**match))

    # Add day data to result
    week_matches.append({
      "date": current_date.isoformat(),
      "dayName": current_date.strftime("%A"),
      "matches": day_matches
    })

    # Move to next day
    current_date += timedelta(days=1)

  return JSONResponse(status_code=status.HTTP_200_OK,
                      content=jsonable_encoder(week_matches))


# get matches
@router.get("/",
            response_model=List[MatchListBase],
            response_description="List all matches")
async def list_matches(request: Request,
                       tournament: Optional[str] = None,
                       season: Optional[str] = None,
                       round: Optional[str] = None,
                       matchday: Optional[str] = None,
                       date_from: Optional[str] = None,
                       date_to: Optional[str] = None,
                       referee: Optional[str] = None,
                       club: Optional[str] = None,
                       team: Optional[str] = None,
                       assigned: Optional[bool] = None) -> JSONResponse:
  mongodb = request.app.state.mongodb
  query = {"season.alias": season if season else os.environ['CURRENT_SEASON']}
  if tournament:
    query["tournament.alias"] = tournament
  if round:
    query["round.alias"] = round
  if matchday:
    query["matchday.alias"] = matchday
  if referee:
    query["$or"] = [{"referee1.userId": referee}, {"referee2.userId": referee}]
  if club:
    if team:
      query["$or"] = [{
          "$and": [{
              "home.clubAlias": club
          }, {
              "home.teamAlias": team
          }]
      }, {
          "$and": [{
              "away.clubAlias": club
          }, {
              "away.teamAlias": team
          }]
      }]
    else:
      query["$or"] = [{"home.clubAlias": club}, {"away.clubAlias": club}]
  if assigned is not None:
    if not assigned:  # assigned == False
      query["$and"] = [{
          "referee1.userId": {
              "$exists": False
          }
      }, {
          "referee2.userId": {
              "$exists": False
          }
      }]
    elif assigned:  # assigned == True
      query["$or"] = [{
          "referee1.userId": {
              "$exists": True
          }
      }, {
          "referee2.userId": {
              "$exists": True
          }
      }]

  if date_from or date_to:
    date_query = {}
    try:
      if date_from:
        parsed_date_from = isodate.parse_date(date_from)
        date_query["$gte"] = datetime.combine(parsed_date_from,
                                              datetime.min.time())
      if date_to:
        parsed_date_to = isodate.parse_date(date_to)
        date_query["$lte"] = datetime.combine(parsed_date_to,
                                              datetime.max.time())
      query["startDate"] = date_query
    except Exception as e:
      raise HTTPException(status_code=400,
                          detail=f"Invalid date format: {str(e)}")
  if DEBUG_LEVEL > 20:
    print("query: ", query)
  # Project only necessary fields, excluding roster, scores, and penalties
  projection = {
    "home.roster": 0,
    "home.scores": 0,
    "home.penalties": 0,
    "away.roster": 0,
    "away.scores": 0,
    "away.penalties": 0
  }

  matches = await mongodb["matches"].find(query, projection).sort("startDate", 1).to_list(None)

  # Convert to MatchListBase objects and parse time fields
  results = []
  for match in matches:
    match = convert_seconds_to_times(match)
    results.append(MatchListBase(**match))

  return JSONResponse(status_code=status.HTTP_200_OK,
                      content=jsonable_encoder(results))


# get one match by id
@router.get("/{match_id}",
            response_description="Get one match by id",
            response_model=MatchDB)
async def get_match(request: Request, match_id: str) -> JSONResponse:
  mongodb = request.app.state.mongodb
  match = await get_match_object(mongodb, match_id)
  if match is None:
    raise HTTPException(status_code=404,
                        detail=f"Match with ID {match_id} not found.")
  return JSONResponse(status_code=status.HTTP_200_OK,
                      content=jsonable_encoder(match))


# create new match
@router.post("/", response_description="Add new match", response_model=MatchDB)
async def create_match(
    request: Request,
    match: MatchBase = Body(...),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> JSONResponse:
  mongodb = request.app.state.mongodb
  if "ADMIN" not in token_payload.roles:
    raise HTTPException(status_code=403, detail="Nicht authorisiert")
  try:
    # get standingsSettings and set points per team
    if (match.tournament is not None and match.season is not None
        and match.home is not None and match.away is not None
        and hasattr(match.tournament, 'alias')
        and hasattr(match.season, 'alias')):
      if DEBUG_LEVEL > 10:
        print("get standingsSettings")
      standings_settings = await fetch_standings_settings(
          match.tournament.alias, match.season.alias)
      if DEBUG_LEVEL > 10:
        print(standings_settings)
      home_score = 0 if match.home is None or not match.home.stats or match.home.stats.goalsFor is None else match.home.stats.goalsFor
      away_score = 0 if match.away is None or not match.away.stats or match.away.stats.goalsFor is None else match.away.stats.goalsFor
      if DEBUG_LEVEL > 10:
        print("calc_match_stats")
      stats = calc_match_stats(match.matchStatus.key, match.finishType.key,
                               standings_settings, home_score, away_score)
      if DEBUG_LEVEL > 20:
        print("stats: ", stats)

      # Now safely assign the stats
      match.home.stats = MatchStats(**stats['home'])
      match.away.stats = MatchStats(**stats['away'])

    t_alias = match.tournament.alias if match.tournament is not None else None
    s_alias = match.season.alias if match.season is not None else None
    r_alias = match.round.alias if match.round is not None else None
    md_alias = match.matchday.alias if match.matchday is not None else None

    if t_alias and s_alias and r_alias and md_alias:
      try:
        ref_points = await fetch_ref_points(t_alias=t_alias,
                                            s_alias=s_alias,
                                            r_alias=r_alias,
                                            md_alias=md_alias)
        if DEBUG_LEVEL > 20:
          print("ref_points: ", ref_points)
        if match.matchStatus.key in ['FINISHED', 'FORFEITED']:
          if match.referee1 is not None:
            match.referee1.points = ref_points
          if match.referee2 is not None:
            match.referee2.points = ref_points
      except HTTPException as e:
        if e.status_code == 404:
          raise HTTPException(
              status_code=404,
              detail=
              f"Could not fetch referee points: Matchday {md_alias} not found for {t_alias} / {s_alias} / {r_alias}"
          )
        raise e

    if DEBUG_LEVEL > 20:
      print("xxx match", match)
    match_data = my_jsonable_encoder(match)
    match_data = convert_times_to_seconds(match_data)

    # convert startDate to the required datetime format
    if 'startDate' in match_data and match_data['startDate'] is not None:
      start_date_str = match_data['startDate']
      print(start_date_str)
      try:
        start_date_parts = datetime.fromisoformat(str(start_date_str))
        if DEBUG_LEVEL > 100:
          print(start_date_parts)
        match_data['startDate'] = datetime(start_date_parts.year,
                                           start_date_parts.month,
                                           start_date_parts.day,
                                           start_date_parts.hour,
                                           start_date_parts.minute,
                                           start_date_parts.second,
                                           start_date_parts.microsecond,
                                           tzinfo=start_date_parts.tzinfo)
      except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if DEBUG_LEVEL > 0:
      print("xxx match_data: ", match_data)

    # add match to collection matches
    result = await mongodb["matches"].insert_one(match_data)

    # Update rounds and matchdays dates, and calc standings
    if t_alias and s_alias and r_alias and md_alias:
      token = await get_sys_ref_tool_token(
          email=os.environ['SYS_ADMIN_EMAIL'],
          password=os.environ['SYS_ADMIN_PASSWORD'])
      headers = {
          'Authorization': f'Bearer {token}',
          'Content-Type': 'application/json'
      }
      tournament = await mongodb['tournaments'].find_one({"alias": t_alias})
      if tournament:
        season = next((s for s in tournament.get("seasons", [])
                       if s.get("alias") == s_alias), None)
        if season:
          round_data = next(
              (r
               for r in season.get("rounds", []) if r.get("alias") == r_alias),
              None)
          if round_data and "_id" in round_data:
            round_id = round_data["_id"]
            matchday_data = next((md for md in round_data.get("matchdays", [])
                                  if md.get("alias") == md_alias), None)
            if matchday_data and "_id" in matchday_data:
              md_id = matchday_data["_id"]
              async with httpx.AsyncClient() as client:
                await update_round_and_matchday(client, headers, t_alias,
                                                s_alias, r_alias, round_id,
                                                md_id)
            else:
              print(f"Warning: Matchday {md_alias} not found or has no ID")
          else:
            print(f"Warning: Round {r_alias} not found or has no ID")

    if DEBUG_LEVEL > 0:
      print("calc_roster_stats (home) ...")
    await calc_roster_stats(mongodb, result.inserted_id, 'home')
    if DEBUG_LEVEL > 0:
      print("calc_roster_stats (away) ...")
    await calc_roster_stats(mongodb, result.inserted_id, 'away')

    # get all player_ids from home and away roster of match
    if t_alias and s_alias and r_alias and md_alias:
      home_players = [
          player.player.playerId for player in match.home.roster
      ] if match.home is not None and match.home.roster is not None else []
      away_players = [
          player.player.playerId for player in match.away.roster
      ] if match.away is not None and match.away.roster is not None else []
      player_ids = home_players + away_players
      if DEBUG_LEVEL > 0:
        print("calc_player_card_stats ...")
      await calc_player_card_stats(mongodb, player_ids, t_alias, s_alias,
                                   r_alias, md_alias, token_payload)
      if DEBUG_LEVEL > 0:
        print("calc_player_card_stats DONE ...")

    # return complete match document
    new_match = await get_match_object(mongodb, result.inserted_id)
    return JSONResponse(status_code=status.HTTP_201_CREATED,
                        content=jsonable_encoder(new_match))

  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))


# ------ update match
@router.patch("/{match_id}",
              response_description="Update match",
              response_model=MatchDB)
async def update_match(request: Request,
                       match_id: str,
                       match: MatchUpdate = Body(...),
                       token_payload: TokenPayload = Depends(
                           auth.auth_wrapper)):
  mongodb = request.app.state.mongodb
  if not any(role in token_payload.roles
             for role in ["ADMIN", "LEAGUE_ADMIN", "CLUB_ADMIN"]):
    raise HTTPException(status_code=403, detail="Nicht authorisiert")

  # Helper function to add _id to new nested documents and clean up ObjectId id fields
  def add_id_to_scores_and_penalties(items):
    for item in items:
      if '_id' not in item:
        item['_id'] = str(ObjectId())
      # Remove ObjectId id field if it exists
      if 'id' in item and isinstance(item['id'], ObjectId):
        item.pop('id')

  # Firstly, check if match exists and get this match
  existing_match = await mongodb["matches"].find_one({"_id": match_id})
  if existing_match is None:
    raise HTTPException(status_code=404,
                        detail=f"Match with id {match_id} not found")
  t_alias = getattr(match.tournament, 'alias',
                    existing_match.get('tournament', {}).get('alias', None))
  s_alias = getattr(match.season, 'alias',
                    existing_match.get('season', {}).get('alias', None))
  r_alias = getattr(match.round, 'alias',
                    existing_match.get('round', {}).get('alias', None))
  md_alias = getattr(match.matchday, 'alias',
                     existing_match.get('matchday', {}).get('alias', None))
  match_status = getattr(
      match.matchStatus, 'key',
      existing_match.get('matchStatus', {}).get('key', None))
  finish_type = getattr(match.finishType, 'key',
                        existing_match.get('finishType', {}).get('key', None))

  home_stats_data = match.home.stats if (
      match.home and match.home.stats
      and match.home.stats != {}) else existing_match.get('home', {}).get(
          'stats', {})
  away_stats_data = match.away.stats if (
      match.away and match.away.stats
      and match.away.stats != {}) else existing_match.get('away', {}).get(
          'stats', {})

  home_stats = home_stats_data if isinstance(
      home_stats_data, MatchStats) else MatchStats(**(home_stats_data or {}))
  away_stats = away_stats_data if isinstance(
      away_stats_data, MatchStats) else MatchStats(**(away_stats_data or {}))
  """
  print("exisiting_match: ", existing_match)
  print("t_alias: ", t_alias)
  print("match_status: ", match_status)
  print("finish_type: ", finish_type)
  print("home_stats: ", home_stats)
  print("away_stats: ", away_stats)
  print("type of home_stats: ", type(home_stats))
  """

  home_goals = home_stats.goalsFor if (
      home_stats and home_stats.goalsFor
      is not None) else existing_match['home']['stats']['goalsFor']
  away_goals = away_stats.goalsFor if (
      away_stats and away_stats.goalsFor
      is not None) else existing_match['away']['stats']['goalsFor']

  if finish_type and home_stats and t_alias:
    stats = calc_match_stats(match_status, finish_type, await
                             fetch_standings_settings(t_alias, s_alias),
                             home_goals, away_goals)
    if getattr(match, 'home', None) is None:
      match.home = MatchTeamUpdate()
    if getattr(match, 'away', None) is None:
      match.away = MatchTeamUpdate()

    if match.home and match.away and stats is not None:
      match.home.stats = MatchStats(**stats['home'])
      match.away.stats = MatchStats(**stats['away'])
    else:
      raise ValueError("Calculating match statistics returned None")

  if DEBUG_LEVEL > 0:
    print("### match/after stats: ", match)

  match.referee1 = existing_match['referee1']
  match.referee2 = existing_match['referee2']

  match_data = match.dict(exclude_unset=True)
  match_data.pop("id", None)

  # set ref points
  if match_status in ['FINISHED', 'FORFEITED']:
    ref_points = await fetch_ref_points(t_alias, s_alias, r_alias, md_alias)
    """
    print("ref_points: ", ref_points)
    print("ref1:", existing_match['referee1'])
    print("ref2:", existing_match['referee2'])
    """
    if existing_match['referee1'] is not None:
      match_data['referee1']['points'] = ref_points
    if existing_match['referee2'] is not None:
      match_data['referee2']['points'] = ref_points

  if DEBUG_LEVEL > 10:
    print("match_data: ", match_data)
  match_data = convert_times_to_seconds(match_data)

  if match_data.get("home") and match_data["home"].get("scores"):
    add_id_to_scores_and_penalties(match_data["home"]["scores"])
  if match_data.get("away") and match_data["away"].get("scores"):
    add_id_to_scores_and_penalties(match_data["away"]["scores"])
  if match_data.get("home") and match_data["home"].get("penalties"):
    add_id_to_scores_and_penalties(match_data["home"]["penalties"])
  if match_data.get("away") and match_data["away"].get("penalties"):
    add_id_to_scores_and_penalties(match_data["away"]["penalties"])

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
  if DEBUG_LEVEL > 0:
    print("match_to_update: ", match_to_update)

  if match_to_update:
    try:
      set_data = {"$set": flatten_dict(match_to_update)}
      update_result = await mongodb["matches"].update_one({"_id": match_id},
                                                          set_data)

      if update_result.modified_count == 0:
        raise HTTPException(status_code=404,
                            detail=f"Match with id {match_id} not found")

      if t_alias and s_alias and r_alias and md_alias:
        token = await get_sys_ref_tool_token(
            email=os.environ['SYS_ADMIN_EMAIL'],
            password=os.environ['SYS_ADMIN_PASSWORD'])
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        tournament = await mongodb['tournaments'].find_one({"alias": t_alias})
        if tournament:
          season = next((s for s in tournament.get("seasons", [])
                         if s.get("alias") == s_alias), None)
          if season:
            round_data = next((r for r in season.get("rounds", [])
                               if r.get("alias") == r_alias), None)
            if round_data and "_id" in round_data:
              round_id = round_data["_id"]
              matchday_data = next((md
                                    for md in round_data.get("matchdays", [])
                                    if md.get("alias") == md_alias), None)
              if matchday_data and "_id" in matchday_data:
                md_id = matchday_data["_id"]
                async with httpx.AsyncClient() as client:
                  await update_round_and_matchday(client, headers, t_alias,
                                                  s_alias, r_alias, round_id,
                                                  md_id)
              else:
                print(f"Warning: Matchday {md_alias} not found or has no ID")
            else:
              print(f"Warning: Round {r_alias} not found or has no ID")

      # Keep roster stats calculation for match document consistency (relatively fast)
      if DEBUG_LEVEL > 0:
        print("calc_roster_stats (home) ...")
      await calc_roster_stats(mongodb, match_id, 'home')
      if DEBUG_LEVEL > 0:
        print("calc_roster_stats (away) ...")
      await calc_roster_stats(mongodb, match_id, 'away')

    except Exception as e:
      raise HTTPException(status_code=500, detail=str(e))
  else:
    if DEBUG_LEVEL > 0:
      print("No changes to update")
    return Response(status_code=status.HTTP_304_NOT_MODIFIED)

  updated_match = await get_match_object(mongodb, match_id)
  
  # PHASE 1 OPTIMIZATION: Only update standings, skip all heavy player calculations
  # Standings updates are relatively fast and needed for live standings
  await calc_standings_per_round(mongodb, t_alias, s_alias, r_alias)
  await calc_standings_per_matchday(mongodb, t_alias, s_alias, r_alias, md_alias)

  if DEBUG_LEVEL > 0:
    current_match_status = updated_match.matchStatus.key if updated_match.matchStatus else None
    print(f"Match updated - skipped heavy player calculations for {current_match_status} match {match_id}")

  return JSONResponse(status_code=status.HTTP_200_OK,
                      content=jsonable_encoder(updated_match))


# delete match
@router.delete("/{match_id}", response_description="Delete match")
async def delete_match(
    request: Request,
    match_id: str,
    token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> Response:
  mongodb = request.app.state.mongodb
  if "ADMIN" not in token_payload.roles:
    raise HTTPException(status_code=403, detail="Nicht authorisiert")
  # check and get match
  match = await mongodb["matches"].find_one({"_id": match_id})
  if match is None:
    raise HTTPException(status_code=404,
                        detail=f"Match with ID {match_id} not found.")

  try:
    t_alias = match.get('tournament', {}).get('alias', None)
    s_alias = match.get('season', {}).get('alias', None)
    r_alias = match.get('round', {}).get('alias', None)
    md_alias = match.get('matchday', {}).get('alias', None)
    home_players = [
        player['player']['playerId']
        for player in match.get('home', {}).get('roster') or []
    ]
    away_players = [
        player['player']['playerId']
        for player in match.get('away', {}).get('roster') or []
    ]
    if DEBUG_LEVEL > 0:
      print("### home_players: ", home_players)
      print("### away_players: ", away_players)

    player_ids = home_players + away_players

    # delete in matches
    result = await mongodb["matches"].delete_one({"_id": match_id})
    if result.deleted_count == 0:
      raise HTTPException(status_code=404,
                          detail=f"Match with id {match_id} not found")

    await calc_standings_per_round(mongodb, t_alias, s_alias, r_alias)
    await calc_standings_per_matchday(mongodb, t_alias, s_alias, r_alias,
                                      md_alias)
    # for each player in player_ids loop through stats list and compare tournament, season and round. if found then remove item from list
    for player_id in player_ids:
      if DEBUG_LEVEL > 10:
        print("player_id: ", player_id)
      player = await mongodb['players'].find({
          '_id': player_id
      }).to_list(length=1)
      if DEBUG_LEVEL > 10:
        print("player: ", player)
      updated_stats = [
          entry for entry in player[0]['stats']
          if entry['tournament'].get('alias') != t_alias and entry['season'].
          get('alias') != s_alias and entry['round'].get('alias') != r_alias
      ]
      if DEBUG_LEVEL > 10:
        print("### DEL / updated_stats: ", updated_stats)
      await mongodb['players'].update_one({'_id': player_id},
                                          {'$set': {
                                              'stats': updated_stats
                                          }})
    await calc_player_card_stats(mongodb, player_ids, t_alias, s_alias,
                                 r_alias, md_alias, token_payload)

    return Response(status_code=status.HTTP_204_NO_CONTENT)

  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))