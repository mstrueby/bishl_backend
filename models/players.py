from bson import ObjectId
from pydantic import Field, BaseModel, validator, HttpUrl
from typing import Optional
from datetime import datetime
from utils import prevent_empty_str, empty_str_to_none
from enum import Enum


class PyObjectId(ObjectId):

  @classmethod
  def __get_validators__(cls):
    yield cls.validate

  @classmethod
  def validate(cls, v):
    if not ObjectId.is_valid(v):
      raise ValueError("Invalid objectid")
    return ObjectId(v)

  @classmethod
  def __modify_schema__(cls, field_schema):
    field_schema.update(type="string")


class MongoBaseModel(BaseModel):
  id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")

  class Config:
    json_encoders = {ObjectId: str}

class PositionEnum(str, Enum):
  SKATER = 'Skater'
  GOALIE = 'Goalie'

class PlayerBase(MongoBaseModel):
  firstname: str = Field(...)
  lastname: str = Field(...)
  birthdate: datetime = Field(..., description='format: yyyy-mm-dd')
  nationality: str = None
  position: PositionEnum = Field(default=PositionEnum.SKATER)
  team: str = None
  club: str = None
  image: HttpUrl = None
  legacyId: int = None

  @validator('firstname', 'lastname', 'position', pre=True, always=True)
  def validate_null_strings(cls, v, field):
    return prevent_empty_str(v, field.name)

  @validator('image', pre=True, always=True)
  def validate_strings(cls, v, field):
    return empty_str_to_none(v, field.name)

class PlayerDB(PlayerBase):
  download_date: datetime = None
  modify_date: datetime = None

class PlayerUpdate(MongoBaseModel):
  firstname: Optional[str] = "DEFAULT"
  lastname: Optional[str] = "DEFAULT"
  birthdate: Optional[datetime] = "DEFAULT"
  nationality: Optional[str] = None
  position: Optional[PositionEnum] = None
  download_date: Optional[datetime] = None
  modify_date: Optional[datetime] = "DEFAULT"
  team: Optional[str] = None
  club: Optional[str] = None
  image: Optional[HttpUrl] = None

  @validator('firstname', 'lastname', 'position', pre=True, always=True)
  def validate_null_strings(cls, v, field):
    return prevent_empty_str(v, field.name)

  @validator('image', pre=True, always=True)
  def validate_strings(cls, v, field):
    return empty_str_to_none(v, field.name)