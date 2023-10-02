from bson import ObjectId
from datetime import date
from pydantic import Field, BaseModel, HttpUrl
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


# sub documents
  
class Standings(BaseModel):
  team: str = Field(...)
  games_played: int = Field(...)
  goals_for: int = Field(...)
  goals_against: int = Field(...)
  points: int = Field(...)


# ------------

class Matches(BaseModel):
  match_id: str = Field(...)
  home_team: str = Field(...)
  away_team: str = Field(...)
  status: str = Field(...)
  venue: str = None
  home_score: int = None
  away_score: int = None
  start_time: date = None
  published: bool = Field(...)
  
class Matchdays(BaseModel):
  matchday_name: str = Field(...)
  matchday_type: str = Field(...)
  start_date: date = None
  end_date: date = None
  published: bool = Field(...)
  matches: List[Matches] = None
  standings: List[Standings] = None
  
class Rounds(BaseModel):
  name: str = Field(...)
  create_standings: bool = Field(...)
  create_stats: bool = Field(...)
  published: bool = Field(...)
  matchdays: List[Matchdays] = None
  standings: List[Standings] = None

class Seasons(BaseModel):
  year: int = Field(...)
  published: bool = Field(...)
  rounds: List[Rounds] = None


# --------

class TournamentBase(MongoBaseModel):
  name: str = Field(...)
  alias: str = Field(...)
  tiny_name: str = Field(...)
  age_group: str = Field(...)
  published: bool = False
  active: bool = False
  external: bool = False
  website: HttpUrl = None
  seasons: List[Seasons] = None

class TournamentDB(TournamentBase):
  pass

class TournamentUpdate(MongoBaseModel):
  name: Optional[str] = None
  alias: Optional[str] = None
  tiny_name: Optional[str] = None
  age_group: Optional[str] = None
  published: Optional[bool] = None
  active: Optional[bool] = None
  external: Optional[bool] = None
  website: Optional[HttpUrl] = None
  seasons: Optional[List[Seasons]] = None
  