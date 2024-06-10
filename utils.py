from datetime import datetime
from fastapi.encoders import jsonable_encoder

def parse_date(date_str):
    return datetime.strptime(date_str, '%Y-%m-%d') if date_str else None
def parse_datetime(datetime_str):
    return datetime.strptime(datetime_str, '%Y-%m-%d %H:%M:%S') if datetime_str else None

def my_jsonable_encoder(obj):
    result = {}
    for field_name, val in obj.__dict__.items():
        if field_name == "id":
            # If the field name is 'id', use '_id' as the key instead.
            result["_id"] = str(val)
            continue
        if isinstance(val, datetime):
            result[field_name] = val
            continue
        result[field_name] = jsonable_encoder(val)
    return result