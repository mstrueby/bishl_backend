import asyncio
import re
from datetime import datetime

import aiohttp
import cloudinary
import cloudinary.uploader
import httpx
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel

from config import settings
from logging_config import logger

BASE_URL = settings.BE_API_URL
DEBUG_LEVEL = settings.DEBUG_LEVEL


async def populate_event_player_fields(mongodb, event_player_dict):
    """Populate display fields for EventPlayer from player data"""
    if event_player_dict and event_player_dict.get("playerId"):
        player_doc = await mongodb["players"].find_one({"_id": event_player_dict["playerId"]})
        if player_doc:
            event_player_dict["displayFirstName"] = player_doc.get("displayFirstName")
            event_player_dict["displayLastName"] = player_doc.get("displayLastName")
            event_player_dict["imageUrl"] = player_doc.get("imageUrl")
            event_player_dict["imageVisible"] = bool(player_doc.get("imageVisible", False))
    return event_player_dict


def to_camel(string: str) -> str:
    components = string.split("_")
    return components[0] + "".join(x.title() for x in components[1:])


def configure_cloudinary():
    cloudinary.config(
        cloud_name=settings.CLDY_CLOUD_NAME,
        api_key=settings.CLDY_API_KEY,
        api_secret=settings.CLDY_API_SECRET,
    )


def parse_date(date_str):
    return datetime.strptime(date_str, "%Y-%m-%d") if date_str else None


def parse_datetime(datetime_str):
    return datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S") if datetime_str else None


def parse_time_to_seconds(time_str: str | None) -> int:
    if not time_str:
        return 0
    parts = time_str.split(":")
    minutes: int = int(parts[0])
    seconds: int = int(parts[1])
    return minutes * 60 + seconds


def parse_time_from_seconds(seconds: int) -> str:
    minutes: int = seconds // 60
    remaining_seconds: int = seconds % 60
    return f"{minutes:02d}:{remaining_seconds:02d}"


def flatten_dict(d, parent_key="", sep="."):
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def my_jsonable_encoder(obj):
    result: dict = {}
    for field_name, val in obj.__dict__.items():
        # print(field_name, "/", val, "/", dict)
        if field_name == "id":
            # If the field name is 'id', use '_id' as the key instead.
            result["_id"] = str(val)
            continue
        if isinstance(val, datetime):
            # Use jsonable_encoder to properly serialize datetime
            result[field_name] = jsonable_encoder(val)
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
    if not isinstance(v, str) or not re.match(r"^\d{1,3}:[0-5][0-9]$", v):
        raise ValueError(f"Field {field_name} must be in the format MIN:SS")
    return v


# fetch_standings_settings has been moved to services.stats_service.StatsService.get_standings_settings()
# This function is deprecated - import StatsService directly instead


# calc_match_stats has been moved to services.stats_service.StatsService.calculate_match_stats()
# This function is deprecated - import StatsService directly instead
def calculate_match_stats(
    match_status: str,
    finish_type: str,
    standings_setting: dict,
    home_score: int = 0,
    away_score: int = 0,
) -> dict[str, dict]:
    """
    DEPRECATED: Use StatsService.calculate_match_stats() instead
    This wrapper maintains backward compatibility
    """
    logger.warning(
        "Deprecated function called - use StatsService instead",
        extra={"function": "calculate_match_stats"},
    )

    from services.stats_service import StatsService

    stats_service = StatsService()
    return stats_service.calculate_match_stats(
        match_status, finish_type, standings_setting, home_score, away_score
    )


# calc_standings_per_round has been moved to services.stats_service.StatsService.aggregate_round_standings()
# This function is deprecated - import StatsService directly instead


# calc_standings_per_matchday has been moved to services.stats_service.StatsService.aggregate_matchday_standings()
# This function is deprecated - import StatsService directly instead


async def fetch_ref_points(t_alias: str, s_alias: str, r_alias: str, md_alias: str) -> int:
    if DEBUG_LEVEL > 0:
        logger.debug("Fetching referee points...")
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{BASE_URL}/tournaments/{t_alias}/seasons/{s_alias}/rounds/{r_alias}/matchdays/{md_alias}"
        ) as response:
            if response.status != 200:
                raise HTTPException(
                    status_code=404,
                    detail=f"Matchday {md_alias} not found for {t_alias} / {s_alias} / {r_alias}",
                )
            return (await response.json()).get("matchSettings").get("refereePoints")


async def get_sys_ref_tool_token(email: str, password: str):
    login_url = f"{settings.BE_API_URL}/users/login"
    login_data = {"email": email, "password": password}
    async with httpx.AsyncClient() as client:
        login_response = await client.post(login_url, json=login_data)

    if login_response.status_code != 200:
        raise Exception(f"Error logging in: {login_response.json()}")
    return login_response.json()["access_token"]


# calc_roster_stats has been moved to services.stats_service.StatsService.calculate_roster_stats()
# This function is deprecated - import StatsService directly instead
async def calculate_roster_stats(match_id: str, team_flag: str, db) -> dict:
    """
    DEPRECATED: Use StatsService.calculate_roster_stats() instead
    This wrapper maintains backward compatibility
    """
    logger.warning(
        "Deprecated function called - use StatsService instead",
        extra={"function": "calculate_roster_stats", "match_id": match_id, "team_flag": team_flag},
    )

    from services.stats_service import StatsService

    stats_service = StatsService(db)
    return asyncio.run(stats_service.calculate_roster_stats(match_id, team_flag))


async def calculate_player_card_stats(
    player_ids: list[str],
    t_alias: str,
    s_alias: str,
    r_alias: str,
    md_alias: str,
    token_payload=None,
) -> None:
    """
    DEPRECATED: Use StatsService.calculate_player_card_stats() instead

    This is a temporary wrapper for backward compatibility.
    """
    from services.stats_service import StatsService

    stats_service = StatsService(None)  # Assuming db is not needed here based on the original stub
    await stats_service.calculate_player_card_stats(
        player_ids, t_alias, s_alias, r_alias, md_alias, token_payload
    )
