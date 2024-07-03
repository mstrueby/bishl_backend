from datetime import datetime
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from typing import List
import re
import os
import aiohttp
from pymongo.database import Database

BASE_URL = os.environ['BE_API_URL']


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


def validate_match_seconds(v, field_name: str):
  if not isinstance(v, str) or not re.match(r'^\d{1,3}:[0-5][0-9]$', v):
    raise ValueError(f'Field {field_name} must be in the format MIN:SS')
  return v


async def fetch_standings_settings(tournament_alias):
  async with aiohttp.ClientSession() as session:
    async with session.get(
        f"{BASE_URL}/tournaments/{tournament_alias}") as response:
      if response.status != 200:
        raise HTTPException(
          status_code=404,
          detail=f"Tournament with alias {tournament_alias} not found")
      return (await response.json()).get('standingsSettings')


def calc_match_stats(match_status, finish_type, matchStats, standingsSetting):
  stats = {'home': {}, 'away': {}}

  def reset_points():
    stats['home']['gamePlayed'] = 0
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
    # reassign goals
    stats['home']['goalsFor'] = matchStats.get('goalsFor', 0)
    stats['home']['goalsAgainst'] = matchStats.get('goalsAgainst', 0)
    stats['away']['goalsFor'] = matchStats.get('goalsAgainst', 0)
    stats['away']['goalsAgainst'] = matchStats.get('goalsFor', 0)

    # matchStats goals are always for the home team!
    if finish_type == 'REGULAR':
      reset_points()
      stats['home']['gamePlayed'] = 1
      stats['away']['gamePlayed'] = 1
      if stats['home']['goalsFor'] > stats['away']['goalsFor']:
        # home team wins in regulation
        stats['home']['win'] = 1
        stats['home']['points'] = standingsSetting.get("pointsWinReg")
        stats['away']['loss'] = 1
        stats['away']['points'] = standingsSetting.get("pointsLossReg")
      elif stats['home']['goalsFor'] < stats['away']['goalsFor']:
        # away team wins in regulation
        stats['home']['loss'] = 1
        stats['home']['points'] = standingsSetting.get("pointsLossReg")
        stats['away']['win'] = 1
        stats['away']['points'] = standingsSetting.get("pointsWinReg")
      else:
        # draw
        stats['home']['draw'] = 1
        stats['home']['points'] = standingsSetting.get("pointsDrawReg")
        stats['away']['draw'] = 1
        stats['away']['points'] = standingsSetting.get("pointsDrawReg")
    elif finish_type == 'OVERTIME':
      reset_points()
      stats['home']['gamePlayed'] = 1
      stats['away']['gamePlayed'] = 1
      if stats['home']['goalsFor'] > stats['away']['goalsFor']:
        # home team wins in OT
        stats['home']['otWin'] = 1
        stats['home']['points'] = standingsSetting.get("pointsWinOvertime")
        stats['away']['otLoss'] = 1
        stats['away']['points'] = standingsSetting.get("pointsLossOvertime")
      else:
        # away team wins in OT
        stats['home']['otLoss'] = 1
        stats['home']['points'] = standingsSetting.get("pointsLossOvertime")
        stats['away']['otWin'] = 1
        stats['away']['points'] = standingsSetting.get("pointsWinOvertime")
    elif finish_type == 'SHOOTOUT':
      reset_points()
      stats['home']['gamePlayed'] = 1
      stats['away']['gamePlayed'] = 1
      if stats['home']['goalsFor'] > stats['away']['goalsFor']:
        # home team wins in shootout
        stats['home']['soWin'] = 1
        stats['home']['points'] = standingsSetting.get("pointsWinShootout")
        stats['away']['soLoss'] = 1
        stats['away']['points'] = standingsSetting.get("pointsLossShootout")
      else:
        # away team wins in shootout
        stats['home']['soLoss'] = 1
        stats['home']['points'] = standingsSetting.get("pointsLossShootout")
        stats['away']['soWin'] = 1
        stats['away']['points'] = standingsSetting.get("pointsWinShootout")
    else:
      print("Unknown finish_type:", finish_type)
  else:
    print("no match stats for matchStatus", match_status)
    reset_points()
  return stats


async def check_create_standings_for_round(mongodb: Database,
                                           round_filter: dict, s_alias: str,
                                           r_alias: str) -> bool:
  if (tournament := await
      mongodb['tournaments'].find_one(round_filter)) is not None:
    for season in tournament.get('seasons', []):
      if season.get("alias") == s_alias:
        for round in season.get("rounds", []):
          if round.get("alias") == r_alias:
            return round.get("createStandings")
  return False


async def check_create_standings_for_matchday(mongodb: Database,
                                              md_filter: dict, s_alias: str,
                                              r_alias: str,
                                              md_alias: str) -> bool:
  if (tournament := await
      mongodb['tournaments'].find_one(md_filter)) is not None:
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
    for k, v in sorted(
      standings.items(),
      key=lambda item: (item[1]['points'], item[1]['goalsFor'] - item[1][
        'goalsAgainst'], item[1]['goalsFor'], -ord(item[1]['fullName'][0])),
      reverse=True)
  }
  return sorted_standings


async def calc_standings_per_round(mongodb: Database, t_alias: str,
                                   s_alias: str, r_alias: str) -> List[dict]:
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
    }).sort("startDate", 1).to_list(1000)

    if not matches:
      print(f"No matches for {t_alias}, {s_alias}, {r_alias}")
      standings = {}
    else:
      standings = calc_standings(matches)
  else:
    print(f"No standings for {t_alias}, {s_alias}, {r_alias}")
    standings = {}

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
    print("update r.standings: ", standings)


async def calc_standings_per_matchday(mongodb: Database, t_alias: str,
                                      s_alias: str, r_alias: str,
                                      md_alias: str) -> List[dict]:
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
