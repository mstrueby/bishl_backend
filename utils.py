from datetime import datetime
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from bson import ObjectId
from typing import List, Callable
import re
import os
import aiohttp
import httpx
import cloudinary
import cloudinary.uploader

BASE_URL = os.environ['BE_API_URL']
DEBUG_LEVEL = int(os.environ['DEBUG_LEVEL'])


def to_camel(string: str) -> str:
  components = string.split('_')
  return components[0] + ''.join(x.title() for x in components[1:])


def configure_cloudinary():
  cloudinary.config(
      cloud_name=os.environ["CLDY_CLOUD_NAME"],
      api_key=os.environ["CLDY_API_KEY"],
      api_secret=os.environ["CLDY_API_SECRET"],
  )


def parse_date(date_str):
  return datetime.strptime(date_str, '%Y-%m-%d') if date_str else None


def parse_datetime(datetime_str):
  return datetime.strptime(datetime_str,
                           '%Y-%m-%d %H:%M:%S') if datetime_str else None


def parse_time_to_seconds(time_str):
  if not time_str:
    return 0
  minutes, seconds = map(int, time_str.split(':'))
  return minutes * 60 + seconds


def parse_time_from_seconds(seconds):
  minutes = seconds // 60
  seconds = seconds % 60
  return f"{minutes:02d}:{seconds:02d}"


def flatten_dict(d, parent_key='', sep='.'):
  items = []
  for k, v in d.items():
    new_key = f'{parent_key}{sep}{k}' if parent_key else k
    if isinstance(v, dict):
      items.extend(flatten_dict(v, new_key, sep=sep).items())
    else:
      items.append((new_key, v))
  return dict(items)


def my_jsonable_encoder(obj):
  result = {}
  for field_name, val in obj.__dict__.items():
    #print(field_name, "/", val, "/", dict)
    if field_name == "id":
      # If the field name is 'id', use '_id' as the key instead.
      result["_id"] = str(val)
      continue
    if isinstance(val, datetime):
      result[field_name] = val
      continue
    if isinstance(val, BaseModel) and val:
      # Recursively encode nested collections
      result[field_name] = my_jsonable_encoder(val)
      continue
    result[field_name] = jsonable_encoder(val)
  return result


def empty_str_to_none(v, field_name: str):
  if v == "":
    print(f"Field '{field_name}' is an empty string and has been set to None.")
    return None
  return v


def prevent_empty_str(v, field_name: str):
  if v is None or v == "":
    raise ValueError(f"Field '{field_name}' cannot be null or empty string")
  return v


def validate_dict_of_strings(v, field_name: str):
  if not isinstance(v, dict):
    raise ValueError(f"Field '{field_name}' must be a dictionary")
  for key, value in v.items():
    if not isinstance(key, str) or not isinstance(value, str):
      raise ValueError(
          f"Field '{field_name}' must be a dictionary with string key-value pairs"
      )
  return v


def validate_match_time(v, field_name: str):
  if not isinstance(v, str) or not re.match(r'^\d{1,3}:[0-5][0-9]$', v):
    raise ValueError(f'Field {field_name} must be in the format MIN:SS')
  return v


async def fetch_standings_settings(tournament_alias: str, season_alias: str) -> dict:
  if not tournament_alias or not season_alias:
    raise HTTPException(status_code=400, detail="Tournament and season aliases are required")

  async with aiohttp.ClientSession() as session:
    try:
      async with session.get(
          f"{BASE_URL}/tournaments/{tournament_alias}/seasons/{season_alias}"
      ) as response:
        if response.status != 200:
          raise HTTPException(
              status_code=404,
              detail=f"Could not fetch standings settings: Tournament/Season {tournament_alias}/{season_alias} not found"
          )
        data = await response.json()
        settings = data.get('standingsSettings')
        if not settings:
          raise HTTPException(
              status_code=404,
              detail=f"No standings settings found for {tournament_alias}/{season_alias}"
          )
        return settings
    except aiohttp.ClientError as e:
      raise HTTPException(
          status_code=500,
          detail=f"Failed to fetch standings settings: {str(e)}"
      )


def calc_match_stats(match_status,
                     finish_type,
                     standings_setting,
                     home_score: int = 0,
                     away_score: int = 0):
  stats = {'home': {}, 'away': {}}

  def reset_points():
    stats['home']['gamePlayed'] = 0
    # reassign goals
    stats['home']['goalsFor'] = home_score
    stats['home']['goalsAgainst'] = away_score
    stats['away']['goalsFor'] = away_score
    stats['away']['goalsAgainst'] = home_score
    stats['home']['points'] = 0
    stats['home']['win'] = 0
    stats['home']['loss'] = 0
    stats['home']['draw'] = 0
    stats['home']['otWin'] = 0
    stats['home']['otLoss'] = 0
    stats['home']['soWin'] = 0
    stats['home']['soLoss'] = 0
    stats['away']['gamePlayed'] = 0
    stats['away']['points'] = 0
    stats['away']['win'] = 0
    stats['away']['loss'] = 0
    stats['away']['draw'] = 0
    stats['away']['otWin'] = 0
    stats['away']['otLoss'] = 0
    stats['away']['soWin'] = 0
    stats['away']['soLoss'] = 0

  if match_status in ['FINISHED', 'INPROGRESS', 'FORFEITED']:
    print("set match stats")
    # matchStats goals are always for the home team!
    if finish_type == 'REGULAR':
      reset_points()
      stats['home']['gamePlayed'] = 1
      stats['away']['gamePlayed'] = 1
      if stats['home']['goalsFor'] > stats['away']['goalsFor']:
        # home team wins in regulation
        stats['home']['win'] = 1
        stats['home']['points'] = standings_setting.get("pointsWinReg")
        stats['away']['loss'] = 1
        stats['away']['points'] = standings_setting.get("pointsLossReg")
      elif stats['home']['goalsFor'] < stats['away']['goalsFor']:
        # away team wins in regulation
        stats['home']['loss'] = 1
        stats['home']['points'] = standings_setting.get("pointsLossReg")
        stats['away']['win'] = 1
        stats['away']['points'] = standings_setting.get("pointsWinReg")
      else:
        # draw
        stats['home']['draw'] = 1
        stats['home']['points'] = standings_setting.get("pointsDrawReg")
        stats['away']['draw'] = 1
        stats['away']['points'] = standings_setting.get("pointsDrawReg")
    elif finish_type == 'OVERTIME':
      reset_points()
      stats['home']['gamePlayed'] = 1
      stats['away']['gamePlayed'] = 1
      if stats['home']['goalsFor'] > stats['away']['goalsFor']:
        # home team wins in OT
        stats['home']['otWin'] = 1
        stats['home']['points'] = standings_setting.get("pointsWinOvertime")
        stats['away']['otLoss'] = 1
        stats['away']['points'] = standings_setting.get("pointsLossOvertime")
      else:
        # away team wins in OT
        stats['home']['otLoss'] = 1
        stats['home']['points'] = standings_setting.get("pointsLossOvertime")
        stats['away']['otWin'] = 1
        stats['away']['points'] = standings_setting.get("pointsWinOvertime")
    elif finish_type == 'SHOOTOUT':
      reset_points()
      stats['home']['gamePlayed'] = 1
      stats['away']['gamePlayed'] = 1
      if stats['home']['goalsFor'] > stats['away']['goalsFor']:
        # home team wins in shootout
        stats['home']['soWin'] = 1
        stats['home']['points'] = standings_setting.get("pointsWinShootout")
        stats['away']['soLoss'] = 1
        stats['away']['points'] = standings_setting.get("pointsLossShootout")
      else:
        # away team wins in shootout
        stats['home']['soLoss'] = 1
        stats['home']['points'] = standings_setting.get("pointsLossShootout")
        stats['away']['soWin'] = 1
        stats['away']['points'] = standings_setting.get("pointsWinShootout")
    else:
      print("Unknown finish_type:", finish_type)
  else:
    print("no match stats for matchStatus", match_status)
    reset_points()
  return stats


async def fetch_ref_points(t_alias: str, s_alias: str, r_alias: str,
                           md_alias: str) -> int:
  async with aiohttp.ClientSession() as session:
    async with session.get(
        f"{BASE_URL}/tournaments/{t_alias}/seasons/{s_alias}/rounds/{r_alias}/matchdays/{md_alias}"
    ) as response:
      if response.status != 200:
        raise HTTPException(
            status_code=404,
            detail=
            f"Matchday {md_alias} not found for {t_alias} / {s_alias} / {r_alias}"
        )
      return (await response.json()).get('matchSettings').get('refereePoints')


async def check_create_standings_for_round(mongodb, round_filter: dict,
                                           s_alias: str, r_alias: str) -> bool:
  if (tournament := await
      mongodb['tournaments'].find_one(round_filter)) is not None:
    for season in tournament.get('seasons', []):
      if season.get("alias") == s_alias:
        for round in season.get("rounds", []):
          if round.get("alias") == r_alias:
            return round.get("createStandings")
  return False


async def check_create_standings_for_matchday(mongodb, md_filter: dict,
                                              s_alias: str, r_alias: str,
                                              md_alias: str) -> bool:
  tournament = await mongodb['tournaments'].find_one(md_filter)
  if tournament is not None:
    for season in tournament.get('seasons', []):
      if season.get("alias") == s_alias:
        for round in season.get("rounds", []):
          if round.get("alias") == r_alias:
            for matchday in round.get("matchdays", []):
              if matchday.get("alias") == md_alias:
                return matchday.get("createStandings")
  return False


def update_streak(team_standings, match_stats):
  if 'win' in match_stats and match_stats['win'] == 1:
    result = 'W'
  elif 'loss' in match_stats and match_stats['loss'] == 1:
    result = 'L'
  elif 'draw' in match_stats and match_stats['draw'] == 1:
    result = 'D'
  elif 'otWin' in match_stats and match_stats['otWin'] == 1:
    result = 'OTW'
  elif 'otLoss' in match_stats and match_stats['otLoss'] == 1:
    result = 'OTL'
  elif 'soWin' in match_stats and match_stats['soWin'] == 1:
    result = 'SOW'
  elif 'soLoss' in match_stats and match_stats['soLoss'] == 1:
    result = 'SOL'
  else:
    result = None
  if result:
    team_standings['streak'].append(result)
    if len(team_standings['streak']) > 5:
      team_standings['streak'].pop(0)


def init_team_standings(team_data: dict) -> dict:
  from models.tournaments import Standings
  return Standings(
      fullName=team_data['fullName'],
      shortName=team_data['shortName'],
      tinyName=team_data['tinyName'],
      logo=team_data['logo'],
      gamesPlayed=0,
      goalsFor=0,
      goalsAgainst=0,
      points=0,
      wins=0,
      losses=0,
      draws=0,
      otWins=0,
      otLosses=0,
      soWins=0,
      soLosses=0,
      streak=[],
  ).dict()


def calc_standings(matches):
  standings = {}

  for match in matches:
    home_team = {
        'fullName': match['home']['fullName'],
        'shortName': match['home']['shortName'],
        'tinyName': match['home']['tinyName'],
        'logo': match['home']['logo']
    }
    away_team = {
        'fullName': match['away']['fullName'],
        'shortName': match['away']['shortName'],
        'tinyName': match['away']['tinyName'],
        'logo': match['away']['logo']
    }
    h_key = home_team['fullName']
    a_key = away_team['fullName']

    if h_key not in standings:
      standings[h_key] = init_team_standings(home_team)
    if a_key not in standings:
      standings[a_key] = init_team_standings(away_team)

    standings[h_key]['gamesPlayed'] += match['home']['stats'].get(
        'gamePlayed', 0)
    standings[a_key]['gamesPlayed'] += match['away']['stats'].get(
        'gamePlayed', 0)
    standings[h_key]['goalsFor'] += match['home']['stats'].get('goalsFor', 0)
    standings[h_key]['goalsAgainst'] += match['home']['stats'].get(
        'goalsAgainst', 0)
    standings[a_key]['goalsFor'] += match['away']['stats'].get('goalsFor', 0)
    standings[a_key]['goalsAgainst'] += match['away']['stats'].get(
        'goalsAgainst', 0)
    standings[h_key]['points'] += match['home']['stats'].get('points', 0)
    standings[a_key]['points'] += match['away']['stats'].get('points', 0)
    standings[h_key]['wins'] += match['home']['stats'].get('win', 0)
    standings[a_key]['wins'] += match['away']['stats'].get('win', 0)
    standings[h_key]['losses'] += match['home']['stats'].get('loss', 0)
    standings[a_key]['losses'] += match['away']['stats'].get('loss', 0)
    standings[h_key]['draws'] += match['home']['stats'].get('draw', 0)
    standings[a_key]['draws'] += match['away']['stats'].get('draw', 0)
    standings[h_key]['otWins'] += match['home']['stats'].get('otWin', 0)
    standings[a_key]['otWins'] += match['away']['stats'].get('otWin', 0)
    standings[h_key]['otLosses'] += match['home']['stats'].get('otLoss', 0)
    standings[a_key]['otLosses'] += match['away']['stats'].get('otLoss', 0)
    standings[h_key]['soWins'] += match['home']['stats'].get('soWin', 0)
    standings[a_key]['soWins'] += match['away']['stats'].get('soWin', 0)
    standings[h_key]['soLosses'] += match['home']['stats'].get('soLoss', 0)
    standings[a_key]['soLosses'] += match['away']['stats'].get('soLoss', 0)

    # update streak
    update_streak(standings[h_key], match['home']['stats'])
    update_streak(standings[a_key], match['away']['stats'])

  sorted_standings = {
      k: v
      for k, v in sorted(standings.items(),
                         key=lambda item: (item[1]['points'], item[1][
                             'goalsFor'] - item[1]['goalsAgainst'], item[1][
                                 'goalsFor'], -ord(item[1]['fullName'][0])),
                         reverse=True)
  }
  return sorted_standings


async def calc_standings_per_round(mongodb, t_alias: str, s_alias: str,
                                   r_alias: str) -> None:
  r_filter = {
      'alias': t_alias,
      'seasons.alias': s_alias,
      'seasons.rounds.alias': r_alias,
      'seasons': {
          '$elemMatch': {
              'alias': s_alias,
              'rounds': {
                  '$elemMatch': {
                      'alias': r_alias
                  }
              }
          }
      }
  }

  if await check_create_standings_for_round(mongodb, r_filter, s_alias,
                                            r_alias):
    matches = await mongodb["matches"].find({
        "tournament.alias": t_alias,
        "season.alias": s_alias,
        "round.alias": r_alias
    }).sort("startDate", 1).to_list(length=None)

    if not matches:
      print(f"No matches for {t_alias}, {s_alias}, {r_alias}")
      standings = {}
    else:
      standings = calc_standings(matches)

  else:
    standings = {}
    if DEBUG_LEVEL > 0:
      print(f"No standings for {t_alias}, {s_alias}, {r_alias}")

  if DEBUG_LEVEL > 20:
    print(f"Standings for {t_alias}, {s_alias}, {r_alias}: {standings}")

  response = await mongodb["tournaments"].update_one(
      r_filter,
      {'$set': {
          "seasons.$[season].rounds.$[round].standings": standings
      }},
      array_filters=[{
          'season.alias': s_alias
      }, {
          'round.alias': r_alias
      }],
      upsert=False)
  if not response.acknowledged:
    raise HTTPException(status_code=500,
                        detail="Failed to update tournament standings.")
  else:
    if DEBUG_LEVEL > 10:
      print("update r.standings: ", standings)


async def calc_standings_per_matchday(mongodb, t_alias: str, s_alias: str,
                                      r_alias: str, md_alias: str) -> None:
  md_filter = {
      'alias': t_alias,
      'seasons.alias': s_alias,
      'seasons.rounds.alias': r_alias,
      'seasons.rounds.matchdays.alias': md_alias,
      'seasons': {
          '$elemMatch': {
              'alias': s_alias,
              'rounds': {
                  '$elemMatch': {
                      'alias': r_alias,
                      'matchdays': {
                          '$elemMatch': {
                              'alias': md_alias
                          }
                      }
                  }
              }
          }
      }
  }

  if await check_create_standings_for_matchday(mongodb, md_filter, s_alias,
                                               r_alias, md_alias):
    matches = await mongodb["matches"].find({
        "tournament.alias": t_alias,
        "season.alias": s_alias,
        "round.alias": r_alias,
        "matchday.alias": md_alias
    }).sort("startDate").to_list(1000)

    if not matches:
      print(f"No matches for {t_alias}, {s_alias}, {r_alias}, {md_alias}")
      standings = {}
    else:
      print("calc standings")
      standings = calc_standings(matches)
  else:
    print(f"No standings for {t_alias}, {s_alias}, {r_alias}, {md_alias}")
    standings = {}

  response = await mongodb["tournaments"].update_one(md_filter, {
      '$set': {
          "seasons.$[season].rounds.$[round].matchdays.$[matchday].standings":
          standings
      }
  },
                                                     array_filters=[{
                                                         'season.alias':
                                                         s_alias
                                                     }, {
                                                         'round.alias':
                                                         r_alias
                                                     }, {
                                                         'matchday.alias':
                                                         md_alias
                                                     }],
                                                     upsert=False)
  if not response.acknowledged:
    raise HTTPException(status_code=500,
                        detail="Failed to update tournament standings.")
  else:
    print("update md.standings: ", standings)


async def get_sys_ref_tool_token(email: str, password: str):
  login_url = f"{os.environ['BE_API_URL']}/users/login"
  login_data = {
      "email": email,
      "password": password
  }
  async with httpx.AsyncClient() as client:
    login_response = await client.post(login_url, json=login_data)

  if login_response.status_code != 200:
    raise Exception(f"Error logging in: {login_response.json()}")
  return login_response.json()['token']

# refresh player stats in roster
async def calc_roster_stats(mongodb, match_id: str, team_flag: str) -> None:
  """
  Fetches the team's roster, updates goals and assists for players, and saves back to the database.

  Parameters
  - mongodb: FastAPI Request object (monogdb)
  - match_id: The ID of the match
  - team_flag: The team flag ('home'/'away')
  """
  async with httpx.AsyncClient() as client:

    response = await client.get(
        f"{BASE_URL}/matches/{match_id}/{team_flag}/roster/")
    if response.status_code != 200:
      raise HTTPException(status_code=response.status_code,
                          detail=response.text)
    roster = response.json()

    response = await client.get(
        f"{BASE_URL}/matches/{match_id}/{team_flag}/scores/")
    if response.status_code != 200:
      raise HTTPException(
          status_code=response.status_code,
          detail=
          f"Failed to fetch scoreboard for {team_flag} team in match {match_id}"
      )
    scoreboard = response.json()

    response = await client.get(
        f"{BASE_URL}/matches/{match_id}/{team_flag}/penalties/")
    if response.status_code != 200:
      raise HTTPException(
          status_code=response.status_code,
          detail=
          f"Failed to fetch penaltysheet for {team_flag} team in match {match_id}"
      )
    penaltysheet = response.json()

    # Summing up all goals and assists for each player from scoreboard
    player_stats = {}
    # Initialize each player from roster in player_stats
    for roster_player in roster:
      player_id = roster_player['player']['playerId']
      if player_id not in player_stats:
        player_stats[player_id] = {
            'goals': 0,
            'assists': 0,
            'points': 0,
            'penaltyMinutes': 0
        }

    for score in scoreboard:
      goal_player_id = score['goalPlayer']['playerId']
      if goal_player_id not in player_stats:
        player_stats[goal_player_id] = {'goals': 0, 'assists': 0}
      player_stats[goal_player_id]['goals'] += 1
      player_stats[goal_player_id][
          'points'] = player_stats[goal_player_id].get('points', 0) + 1

      assist_player = score.get('assistPlayer')
      assist_player_id = assist_player.get(
          'playerId') if assist_player else None
      if assist_player_id:
        if assist_player_id not in player_stats:
          player_stats[assist_player_id] = {'goals': 0, 'assists': 0}
        player_stats[assist_player_id]['assists'] += 1
        player_stats[assist_player_id][
            'points'] = player_stats[assist_player_id].get('points', 0) + 1

    for penalty in penaltysheet:
      pen_player_id = penalty['penaltyPlayer']['playerId']
      if pen_player_id not in player_stats:
        player_stats[pen_player_id] = {'penaltyMinutes': 0}
      player_stats[pen_player_id]['penaltyMinutes'] += penalty[
          'penaltyMinutes']

  # Update roster with summed goals and assists
  for roster_player in roster:
    player_id = roster_player['player']['playerId']
    if player_id in player_stats:
      roster_player.update(player_stats[player_id])

  if DEBUG_LEVEL > 10:
    print("### player_stats", player_stats)
    print("### roster: ", roster)

  # update roster for match in mongodb
  if roster:
    try:
      await mongodb["matches"].update_one(
          {"_id": match_id}, {"$set": {
              f"{team_flag}.roster": roster
          }})
    except Exception as e:
      raise HTTPException(
          status_code=500,
          detail=f"Could not update roster in mongoDB, {str(e)}")


# Refresh Stats for EACH PLAYER(!) in a tournament/season/round/matchday
# calc stats for round / matchday if createStats is true
# ----------------------------------------------------------
async def calc_player_card_stats(mongodb, player_ids: List[str], t_alias: str,
                                 s_alias: str, r_alias: str,
                                 md_alias: str, token_payload=None) -> None:
  """
  Calculate and update player statistics for a given tournament/season/round/matchday.
  Also handles called matches logic for assignedTeams updates.
  """

  def _create_team_dict(match_team_data: dict) -> dict:
    """Create a standardized team dictionary from match data."""
    return {
        'name': match_team_data.get('name'),
        'fullName': match_team_data.get('fullName'),
        'shortName': match_team_data.get('shortName'),
        'tinyName': match_team_data.get('tinyName')
    }

  def _initialize_player_stats(player_id: str, team_key: str, team: dict, 
                               match_info: dict, player_card_stats: dict) -> None:
    """Initialize player stats structure if it doesn't exist."""
    if player_id not in player_card_stats:
      player_card_stats[player_id] = {}

    if team_key not in player_card_stats[player_id]:
      player_card_stats[player_id][team_key] = {
          'tournament': match_info['tournament'],
          'season': match_info['season'],
          'round': match_info['round'],
          'matchday': match_info['matchday'],
          'team': team,
          'gamesPlayed': 0,
          'goals': 0,
          'assists': 0,
          'points': 0,
          'penaltyMinutes': 0,
          'calledMatches': 0,
      }

  def _update_player_stats(player_id: str, team: dict, roster_player: dict, 
                          match_info: dict, player_card_stats: dict) -> None:
    """Update individual player statistics from roster data."""
    team_key = team['fullName']
    _initialize_player_stats(player_id, team_key, team, match_info, player_card_stats)

    # Only count stats for finished/active matches
    if match_info['match_status']['key'] in ['FINISHED', 'INPROGRESS', 'FORFEITED']:
      stats = player_card_stats[player_id][team_key]
      stats['gamesPlayed'] += 1
      stats['goals'] += roster_player.get('goals', 0)
      stats['assists'] += roster_player.get('assists', 0)
      stats['points'] += roster_player.get('points', 0)
      stats['penaltyMinutes'] += roster_player.get('penaltyMinutes', 0)

      # Track called matches
      if roster_player.get('called', False):
        stats['calledMatches'] += 1

  def _process_roster_for_team(matches: List[dict], team_flag: str, player_ids: List[str], 
                              player_card_stats: dict, flag: str) -> None:
    """Process roster data for a specific team (home/away) across all matches."""
    for match in matches:
      match_info = {
          'tournament': match.get('tournament', {}),
          'season': match.get('season', {}),
          'round': match.get('round', {}),
          'matchday': match.get('matchday', {}) if flag == 'MATCHDAY' else None,
          'match_status': match.get('matchStatus', {})
      }

      roster = match.get(team_flag, {}).get('roster', [])
      team = _create_team_dict(match.get(team_flag, {}))

      if DEBUG_LEVEL > 10:
        print(f"### {team_flag}_roster", roster)

      for roster_player in roster:
        player_id = roster_player.get('player', {}).get('playerId')
        if player_id and player_id in player_ids:
          if DEBUG_LEVEL > 10:
            print(f"### {team_flag}_roster_player", roster_player)
          _update_player_stats(player_id, team, roster_player, match_info, player_card_stats)

  async def _save_player_stats_to_db(mongodb, player_card_stats: dict, 
                                    t_alias: str, s_alias: str, r_alias: str, 
                                    md_alias: str, flag: str) -> None:
    """Save calculated player statistics to the database."""
    for player_id, stats_by_team in player_card_stats.items():
      for team_key, stats in stats_by_team.items():
        player = await mongodb['players'].find_one({"_id": player_id})
        if not player:
          raise HTTPException(
              status_code=404,
              detail=f"Player {player_id} not found in mongoDB")

        # Merge with existing stats or create new ones
        existing_stats = player.get('stats', [])
        updated_stats = []
        stat_found = False

        for existing_stat in existing_stats:
          # Check if this stat entry should be updated
          if (_should_update_stat(existing_stat, stats, t_alias, s_alias, 
                                 r_alias, md_alias, flag)):
            merged_stat = {**existing_stat, **stats, 
                          'team': existing_stat.get('team', stats['team'])}
            updated_stats.append(merged_stat)
            stat_found = True
          else:
            updated_stats.append(existing_stat)

        # Add new stat if no existing one was updated
        if not stat_found:
          updated_stats.append(stats)

        # Save to database
        result = await mongodb['players'].update_one(
            {"_id": player_id}, 
            {"$set": {"stats": updated_stats}}
        )
        if not result.acknowledged:
          print(f"Warning: Failed to update stats for player {player_id}")

  def _should_update_stat(existing_stat: dict, new_stats: dict, 
                         t_alias: str, s_alias: str, r_alias: str, 
                         md_alias: str, flag: str) -> bool:
    """Check if an existing stat entry should be updated with new data."""
    return (existing_stat.get('tournament', {}).get('alias') == t_alias and
            existing_stat.get('season', {}).get('alias') == s_alias and
            existing_stat.get('round', {}).get('alias') == r_alias and
            existing_stat.get('team', {}).get('fullName') == new_stats['team']['fullName'] and
            (existing_stat.get('matchday', {}).get('alias') == md_alias if flag == 'MATCHDAY' else True))

  async def _process_called_teams_assignments(player_ids: List[str], matches: List[dict],
                                            t_alias: str, s_alias: str) -> None:
    """Check calledMatches for affected players and update assignedTeams if needed."""
    base_url = os.environ.get('BE_API_URL', '')
    if not base_url or not token_payload:
      return

    # Prepare authentication headers
    from authentication import AuthHandler
    auth_handler = AuthHandler()
    auth_token = auth_handler.encode_token({
        "_id": token_payload.sub,
        "roles": token_payload.roles,
        "firstName": token_payload.firstName,
        "lastName": token_payload.lastName,
        "club": {
            "clubId": token_payload.clubId,
            "clubName": token_payload.clubName
        } if token_payload.clubId else None
    })
    headers = {"Authorization": f"Bearer {auth_token}"}

    for player_id in player_ids:
      try:
        async with httpx.AsyncClient() as client:
          player_response = await client.get(f"{base_url}/players/{player_id}", headers=headers)
          if player_response.status_code != 200:
            continue

          player_data = player_response.json()
          teams_to_check = _find_called_teams(player_id, matches)

          await _update_assigned_teams_for_called_matches(
              client, player_id, player_data, teams_to_check, t_alias, s_alias, base_url, headers)

      except Exception as e:
        if DEBUG_LEVEL > 0:
          print(f"Error processing called matches for player {player_id}: {str(e)}")
        continue

  def _find_called_teams(player_id: str, matches: List[dict]) -> set:
    """Find all teams this player was called for across matches."""
    teams_to_check = set()

    for match in matches:
      for team_flag in ['home', 'away']:
        roster = match.get(team_flag, {}).get('roster', [])
        for roster_player in roster:
          if (roster_player.get('player', {}).get('playerId') == player_id and
              roster_player.get('called', False)):
            current_team = match.get(team_flag, {}).get('team', {})
            current_club = match.get(team_flag, {}).get('club', {})
            if current_team and current_club:
              teams_to_check.add((
                current_team.get('teamId'),
                current_team.get('name'),
                current_team.get('alias'),
                current_team.get('ageGroup', ''),
                current_team.get('ishdId'),
                current_club.get('clubId'),
                current_club.get('name'),
                current_club.get('alias'),
                current_club.get('ishdId')
              ))

    return teams_to_check

  async def _update_assigned_teams_for_called_matches(client, player_id: str, player_data: dict,
                                                     teams_to_check: set, t_alias: str, 
                                                     s_alias: str, base_url: str, headers: dict) -> None:
    """Update assignedTeams for players with 5+ called matches."""
    for team_info in teams_to_check:
      (team_id, team_name, team_alias, team_age_group, team_ishd_id,
       club_id, club_name, club_alias, club_ishd_id) = team_info

      # Check if player has 5+ called matches for this team
      player_stats = player_data.get('stats', [])
      for stat in player_stats:
        if (_has_enough_called_matches(stat, t_alias, s_alias, team_name) and
            not _team_already_assigned(player_data, team_id)):

          await _add_called_team_assignment(
              client, player_id, player_data, team_info, base_url, headers)
          break

  def _has_enough_called_matches(stat: dict, t_alias: str, s_alias: str, team_name: str) -> bool:
    """Check if a player has enough called matches for a team."""
    return (stat.get('tournament', {}).get('alias') == t_alias and
            stat.get('season', {}).get('alias') == s_alias and
            stat.get('team', {}).get('name') == team_name and
            stat.get('calledMatches', 0) >= 5)

  def _team_already_assigned(player_data: dict, team_id: str) -> bool:
    """Check if team is already in player's assignedTeams."""
    assigned_teams = player_data.get('assignedTeams', [])
    for club in assigned_teams:
      for team in club.get('teams', []):
        if team.get('teamId') == team_id:
          return True
    return False

  async def _add_called_team_assignment(client, player_id: str, player_data: dict,
                                       team_info: tuple, base_url: str, headers: dict) -> None:
    """Add a new team assignment with CALLED source."""
    (team_id, team_name, team_alias, team_age_group, team_ishd_id,
     club_id, club_name, club_alias, club_ishd_id) = team_info

    assigned_teams = player_data.get('assignedTeams', [])

    # Try to add to existing club or create new club
    club_found = False
    for club in assigned_teams:
      if club.get('clubId') == club_id:
        club['teams'].append(_create_team_assignment(team_info))
        club_found = True
        break

    if not club_found and club_id:
      assigned_teams.append(_create_club_assignment(team_info))

    # Update player in database
    update_response = await client.patch(
        f"{base_url}/players/{player_id}",
        json={"assignedTeams": assigned_teams},
        headers=headers
    )
    if update_response.status_code == 200 and DEBUG_LEVEL > 0:
      print(f"Added CALLED team assignment for player {player_id}")

  def _create_team_assignment(team_info: tuple) -> dict:
    """Create a team assignment dictionary."""
    team_id, team_name, team_alias, team_age_group, team_ishd_id = team_info[:5]
    return {
        "teamId": team_id,
        "teamName": team_name,
        "teamAlias": team_alias,
        "teamAgeGroup": team_age_group,
        "teamIshdId": team_ishd_id,
        "passNo": "",
        "source": "CALLED",
        "modifyDate": None,
        "active": True,
        "jerseyNo": None
    }

  def _create_club_assignment(team_info: tuple) -> dict:
    """Create a club assignment dictionary with team."""
    club_id, club_name, club_alias, club_ishd_id = team_info[5:]
    return {
        "clubId": club_id,
        "clubName": club_name,
        "clubAlias": club_alias,
        "clubIshdId": club_ishd_id,
        "teams": [_create_team_assignment(team_info)]
    }

  async def _update_player_card_stats(flag: str, matches: List[dict], 
                                     player_card_stats: dict) -> None:
    """Main function to update player card statistics."""
    if flag not in ['ROUND', 'MATCHDAY']:
      raise ValueError("Invalid flag, only 'ROUND' or 'MATCHDAY' are accepted.")

    if DEBUG_LEVEL > 10:
      print("count matches", len(matches))

    # Process rosters for both home and away teams
    _process_roster_for_team(matches, 'home', player_ids, player_card_stats, flag)
    _process_roster_for_team(matches, 'away', player_ids, player_card_stats, flag)

    if DEBUG_LEVEL > 10:
      print("### player_card_stats", player_card_stats)

    # Save statistics to database
    await _save_player_stats_to_db(mongodb, player_card_stats, t_alias, s_alias, 
                                  r_alias, md_alias, flag)

  # Main execution logic
  if not all([t_alias, s_alias, r_alias, md_alias]):
    return

  # Fetch round information
  async with httpx.AsyncClient() as client:
    response = await client.get(
        f"{BASE_URL}/tournaments/{t_alias}/seasons/{s_alias}/rounds/{r_alias}")
    if response.status_code != 200:
      raise HTTPException(status_code=response.status_code,
                          detail="Could not fetch the round information")
    round_info = response.json()

  # Process round statistics
  matches = []
  if round_info.get('createStats', False):
    matches = await mongodb["matches"].find({
        "tournament.alias": t_alias,
        "season.alias": s_alias,
        "round.alias": r_alias
    }).to_list(length=None)

    player_card_stats = {}
    await _update_player_card_stats("ROUND", matches, player_card_stats)

    if DEBUG_LEVEL > 0:
      print("### round - player_card_stats", player_card_stats)
  elif DEBUG_LEVEL > 0:
    print("### no round stats")

  # Process matchday statistics
  for matchday in round_info.get('matchdays', []):
    if matchday.get('createStats', False):
      matchday_matches = await mongodb["matches"].find({
          "tournament.alias": t_alias,
          "season.alias": s_alias,
          "round.alias": r_alias,
          "matchday.alias": md_alias
      }).to_list(length=None)

      player_card_stats = {}
      await _update_player_card_stats("MATCHDAY", matchday_matches, player_card_stats)

      if DEBUG_LEVEL > 0:
        print("### matchday - player_card_stats", player_card_stats)

      # Update matches for called teams processing
      if not matches:
        matches = matchday_matches
    elif DEBUG_LEVEL > 0:
      print("### no matchday stats")

  # Process called teams assignments
  if matches:
    await _process_called_teams_assignments(player_ids, matches, t_alias, s_alias)