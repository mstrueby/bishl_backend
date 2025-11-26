import re
from datetime import datetime

import cloudinary
import cloudinary.uploader
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel

from config import settings

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
