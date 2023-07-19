from bson import ObjectId
from datetime import date
from pydantic import Field, BaseModel, HttpUrl, EmailStr
from typing import Optional, List


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
    

# Tournaments
# ------------

# sub documents
class Standings(BaseModel):
  team: str = Field(...)
  games_played: int = Field(...)
  goals_for: int = Field(...)
  goals_against: int = Field(...)
  points: int = Field(...)

class Matches(BaseModel):
  match_id: str = Field(...)
  home_team: str = Field(...)
  away_team: str = Field(...)
  status: str = Field(...)
  venue: str = None
  home_score: int = None
  away_score: int = None
  start_time: date = None
  
class Matchday(BaseModel):
  matchday_name: str = Field(...)
  matchday_type: str = Field(...)
  start_date: date = None
  end_date: date = None
  matches: List[Matches] = None
  standings: List[Standings] = None

class Tournaments(BaseModel):
  name: str = Field(...)
  create_table: bool = Field(...)
  published: bool = Field(...)
  matchdays: List[Matchday] = None
  matches: List[Matches] = None
  standings: List[Standings] = None
  
# --------

class SeasonBase(MongoBaseModel):
  name: str = Field(...)
  year: int = Field(...)
  alias: str = Field(...)
  age_group: str = Field(...)
  published: bool = False
  active: bool = False
  tournaments: List[Tournaments] = None

class SeasonDB(SeasonBase):
  pass

class SeasonUpdate(MongoBaseModel):
  name: Optional[str] = None
  year: Optional[int] = None
  alias: Optional[str] = None
  age_group: Optional[str] = None
  published: Optional[bool] = None
  active: Optional[bool] = None
  tournaments: Optional[List[Tournaments]] = None
  