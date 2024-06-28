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


def apply_points(finishType, matchStats, standingsSetting):
    stats = {
        'home': {},
        'away': {}
    }
    def reset_points():
        stats['home']['points'] = 0
        stats['home']['win'] = 0
        stats['home']['loss'] = 0
        stats['home']['draw'] = 0
        stats['home']['otWin'] = 0
        stats['home']['otLoss'] = 0
        stats['home']['soWin'] = 0
        stats['home']['soLoss'] = 0
        stats['away']['points'] = 0
        stats['away']['win'] = 0
        stats['away']['loss'] = 0
        stats['away']['draw'] = 0
        stats['away']['otWin'] = 0
        stats['away']['otLoss'] = 0
        stats['away']['soWin'] = 0
        stats['away']['soLoss'] = 0

    # reassign goals
    stats['home']['goalsFor'] = matchStats.get('goalsFor', 0)
    stats['home']['goalsAgainst'] = matchStats.get('goalsAgainst', 0)
    stats['away']['goalsFor'] = matchStats.get('goalsAgainst', 0)
    stats['away']['goalsAgainst'] = matchStats.get('goalsFor', 0)

    # matchStats goals are always for the home team!
    if finishType.get('key') == 'REGULAR':
        reset_points()
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
    elif finishType.get('key') == 'OVERTIME':
        reset_points()
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
    elif finishType.get('key') == 'SHOOTOUT':
        reset_points()
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
        print("Unknown finishType")
    return stats