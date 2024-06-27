from datetime import datetime
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
import re
import os
import aiohttp

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
        print(
            f"Field '{field_name}' is an empty string and has been set to None."
        )
        return None
    return v


def prevent_empty_str(v, field_name: str):
    if v is None or v == "":
        raise ValueError(
            f"Field '{field_name}' cannot be null or empty string")
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
      async with session.get(f"{BASE_URL}/tournaments/{tournament_alias}") as response:
        if response.status != 200:
          raise HTTPException(
            status_code=404,
            detail=f"Tournament with alias {tournament_alias} not found"
          )
        return (await response.json()).get('standingsSettings')

def apply_points(match, standingsSetting):
    match match.finishType.get('key'):
      case 'OVERTIME':
        if match.home.stats.goalsFor > match.home.stats.goalsAgainst:
          match.home.stats.otWin = 1
          match.home.stats.points = standingsSetting.get("pointsWinOvertime")
          match.away.stats.otLoss = 1
          match.away.stats.points = standingsSetting.get("pointsLossOvertime")
        else:
          match.home.stats.otLoss = 1
          match.home.stats.points = standingsSetting.get("pointsLossOvertime")
          match.away.stats.otWin = 1
          match.away.stats.points = standingsSetting.get("pointsWinOvertime")
      case 'SHOOTOUT':
        if match.home.stats.goalsFor > match.home.stats.goalsAgainst:
          match.home.stats.soWin = 1
          match.home.stats.points = standingsSetting.get("pointsWinShootout")
          match.away.stats.soLoss = 1
          match.away.stats.points = standingsSetting.get("pointsLossShootout")
        else:
          match.home.stats.soLoss = 1
          match.home.stats.points = standingsSetting.get("pointsLossShootout")
          match.away.stats.soWin = 1
          match.away.stats.points = standingsSetting.get("pointsWinShootout")
      case 'REGULAR':
        if match.home.stats.goalsFor > match.home.stats.goalsAgainst:
          match.home.stats.win = 1
          match.home.stats.points = standingsSetting.get("pointsWinReg")
          match.away.stats.loss = 1
          match.away.stats.points = standingsSetting.get("pointsLossReg")
        elif match.home.stats.goalsFor < match.home.stats.goalsAgainst:
          match.home.stats.loss = 1
          match.home.stats.points = standingsSetting.get("pointsLossReg")
          match.away.stats.win = 1
          match.away.stats.points = standingsSetting.get("pointsWinReg")
        else:
          match.home.stats.draw = 1
          match.home.stats.points = standingsSetting.get("pointsDrawReg")
          match.away.stats.draw = 1
          match.away.stats.points = standingsSetting.get("pointsDrawReg")
      case _:
        print("Unknown finishType")