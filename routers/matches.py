# filename: routers/matches.py
from fastapi import APIRouter, Request, Body, status, HTTPException, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse, Response
from typing import List, Optional
from models.matches import MatchBase, MatchDB, MatchUpdate, MatchTeamUpdate, MatchStats, MatchTeam
from authentication import AuthHandler, TokenPayload
from utils import my_jsonable_encoder, parse_time_to_seconds, parse_time_from_seconds, fetch_standings_settings, calc_match_stats, flatten_dict, calc_standings_per_round, calc_standings_per_matchday, fetch_ref_points, calc_roster_stats, calc_player_card_stats
import os
import isodate
from datetime import datetime
from bson import ObjectId

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
  return data


async def get_match_object(mongodb, match_id: str) -> MatchDB:
  match = await mongodb["matches"].find_one({"_id": match_id})
  if not match:
    raise HTTPException(status_code=404,
                        detail=f"Match with id {match_id} not found")

  # parse scores.matchSeconds to a string format
  match = convert_seconds_to_times(match)
  return MatchDB(**match)


# get matches
@router.get("/",
            response_model=List[MatchDB],
            response_description="List all matches")
async def list_matches(request: Request,
                       tournament: Optional[str] = None,
                       season: Optional[str] = None,
                       round: Optional[str] = None,
                       matchday: Optional[str] = None,
                       date_from: Optional[str] = None,
                       date_to: Optional[str] = None,
                       referee: Optional[str] = None) -> JSONResponse:
  mongodb = request.app.state.mongodb
  query = {"season.alias": season if season else os.environ['CURRENT_SEASON']}
  if tournament:
    query["tournament.alias"] = tournament
  if round:
    query["round.alias"] = round
  if matchday:
    query["matchday.alias"] = matchday
  if referee:
    query["$or"] = [{
        "referee1.user_id": referee
    }, {
        "referee2.user_id": referee
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
                                              datetime.min.time())
      query["startDate"] = date_query
    except Exception as e:
      raise HTTPException(status_code=400,
                          detail=f"Invalid date format: {str(e)}")
  if DEBUG_LEVEL> 10:
    print("query: ", query)
  matches = await mongodb["matches"].find(query).to_list(None)
  results = [MatchDB(**match) for match in matches]
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
  if token_payload.roles not in [["ADMIN"]]:
    raise HTTPException(status_code=403, detail="Not authorized")
  try:
    # get standingsSettings and set points per team
    if (match.tournament is not None and match.season is not None
        and match.home is not None and match.away is not None
        and hasattr(match.tournament, 'alias')
        and hasattr(match.season, 'alias')):
      standings_settings = await fetch_standings_settings(
          match.tournament.alias, match.season.alias)
      home_score = 0 if match.home is None or not match.home.stats or match.home.stats.goalsFor is None else match.home.stats.goalsFor
      away_score = 0 if match.away is None or not match.away.stats or match.away.stats.goalsFor is None else match.away.stats.goalsFor
      stats = calc_match_stats(match.matchStatus.key, match.finishType.key,
                               standings_settings, home_score, away_score)
      if DEBUG_LEVEL > 10:
        print("stats: ", stats)

      # Now safely assign the stats
      match.home.stats = MatchStats(**stats['home'])
      match.away.stats = MatchStats(**stats['away'])

    t_alias = match.tournament.alias if match.tournament is not None else None
    s_alias = match.season.alias if match.season is not None else None
    r_alias = match.round.alias if match.round is not None else None
    md_alias = match.matchday.alias if match.matchday is not None else None

    if t_alias and s_alias and r_alias and md_alias:
      ref_points = await fetch_ref_points(t_alias=t_alias,
                                          s_alias=s_alias,
                                          r_alias=r_alias,
                                          md_alias=md_alias)
      if match.matchStatus.key in ['FINISHED', 'FORFEITED']:
        if match.referee1 is not None:
          match.referee1.points = ref_points
        if match.referee2 is not None:
          match.referee2.points = ref_points

    print("xxx match", match)
    match_data = jsonable_encoder(match)
    match_data = convert_times_to_seconds(match_data)

    # convert startDate to the required datetime format
    if 'startDate' in match_data:
      start_date_str = match_data['startDate']
      start_date_parts = datetime.fromisoformat(start_date_str)
      match_data['startDate'] = datetime(start_date_parts.year,
                                         start_date_parts.month,
                                         start_date_parts.day,
                                         start_date_parts.hour,
                                         start_date_parts.minute,
                                         start_date_parts.second,
                                         start_date_parts.microsecond,
                                         tzinfo=start_date_parts.tzinfo)

    if DEBUG_LEVEL > 0:
      print("xxx match_data: ", match_data)

    # add match to collection matches
    result = await mongodb["matches"].insert_one(match_data)
    print("result: ", result)

    # calc standings and set it in round if createStandings is true
    if t_alias and s_alias and r_alias and md_alias:
      print("calc standings ...")
      await calc_standings_per_round(mongodb, t_alias, s_alias, r_alias)
      await calc_standings_per_matchday(mongodb, t_alias, s_alias, r_alias,
                                        md_alias)

    #TODO: Insert calc_roster_stats
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
                                   r_alias, md_alias)
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
  if token_payload.roles not in [["ADMIN"]]:
    raise HTTPException(status_code=403, detail="Not authorized")

  # Helper function to add _id to new nested documents
  def add_id_to_scores(scores):
    for score in scores:
      if '_id' not in score:
        score['_id'] = str(ObjectId())

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

  home_stats = getattr(match.home, 'stats',
                       existing_match.get('home', {}).get(
                           'stats',
                           None))  # if getattr(match, 'home', None) else None
  away_stats = getattr(match.away, 'stats',
                       existing_match.get('away', {}).get(
                           'stats',
                           None))  # if getattr(match, 'away', None) else None
  """
  print("exisiting_match: ", existing_match)
  print("t_alias: ", t_alias)
  print("match_status: ", match_status)
  print("finish_type: ", finish_type)
  print("home_stats: ", home_stats)
  print("away_stats: ", away_stats)
  """
  home_goals = home_stats.get('goalsFor', 0) if home_stats else 0
  away_goals = away_stats.get('goalsFor', 0) if away_stats else 0

  if finish_type and home_stats and t_alias:
    stats = calc_match_stats(match_status, finish_type, await
                             fetch_standings_settings(t_alias, s_alias),
                             home_goals, away_goals)
    if getattr(match, 'home', None) is None:
      match.home = MatchTeamUpdate()
    if getattr(match, 'away', None) is None:
      match.away = MatchTeamUpdate()

    if stats is not None:
      match.home.stats = stats['home']
      match.away.stats = stats['away']
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
    add_id_to_scores(match_data["home"]["scores"])
  if match_data.get("away") and match_data["away"].get("scores"):
    add_id_to_scores(match_data["away"]["scores"])

  def check_nested_fields(data, existing, path=""):
    for key, value in data.items():
      full_key = f"{path}.{key}" if path else key
      if existing is None or key not in existing:
        match_to_update[full_key] = value
      elif isinstance(value, dict):
        #print("val: ", value)
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
      if DEBUG_LEVEL > 0: print("calc_roster_stats (home) ...")
      await calc_roster_stats(mongodb, match_id, 'home')
      if DEBUG_LEVEL > 0: print("calc_roster_stats (away) ...")
      await calc_roster_stats(mongodb, match_id, 'away')

    except Exception as e:
      raise HTTPException(status_code=500, detail=str(e))
  else:
    print("No changes to update")
    return Response(status_code=status.HTTP_304_NOT_MODIFIED)

  updated_match = await get_match_object(mongodb, match_id)
  # calc standings and set it in round
  await calc_standings_per_round(mongodb, t_alias, s_alias, r_alias)
  await calc_standings_per_matchday(mongodb, t_alias, s_alias, r_alias,
                                    md_alias)
  # get all player_ids from home and away roster of match
  home_players = [
      player.player.playerId for player in (updated_match.home.roster or [])
  ] if updated_match.home is not None else []
  away_players = [
      player.player.playerId for player in (updated_match.away.roster or [])
  ] if updated_match.away is not None else []
  player_ids = home_players + away_players
  await calc_player_card_stats(mongodb, player_ids, t_alias, s_alias, r_alias,
                               md_alias)

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
  if token_payload.roles not in [["ADMIN"]]:
    raise HTTPException(status_code=403, detail="Not authorized")
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
      if DEBUG_LEVEL > 10: print("player_id: ", player_id)
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
                                 r_alias, md_alias)

    return Response(status_code=status.HTTP_204_NO_CONTENT)

  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))
