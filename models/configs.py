# models/configs.py

from pydantic import BaseModel


class ConfigValue(BaseModel):
    key: str
    value: str | int | float  # Adjust types as needed
    sortOrder: int


class Config(BaseModel):
    key: str
    name: str
    value: list[ConfigValue]
