# models/configs.py
from pydantic import BaseModel
from typing import List, Union

class ConfigValue(BaseModel):
    key: str
    value: Union[str, int, float]  # Adjust types as needed
    sortOrder: int

class Config(BaseModel):
    key: str
    name: str
    value: List[ConfigValue]