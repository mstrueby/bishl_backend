from datetime import datetime, time
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel


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
    return f"{minutes}:{seconds:02d}"


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