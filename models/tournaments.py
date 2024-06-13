from bson import ObjectId
from datetime import datetime, date
from pydantic import Field, BaseModel, HttpUrl, validator
from typing import Optional, List
from models.matches import MatchBase


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
  gamesPlayed: int = Field(...)
  goalsFor: int = Field(...)
  goalsAgainst: int = Field(...)
  points: int = Field(...)


# ------------
class Teams(BaseModel):
  fullName: str = Field(...)
  shortName: str = Field(...)
  tinyName: str = Field(...)
  logo: HttpUrl = None

  @validator('logo', pre=True, always=True)
  def empty_str_to_none(cls, v):
    return None if v == "" else v


class MatchDB(MatchBase):
  pass


class MatchUpdate(MongoBaseModel):
  homeTeam: Optional[Teams] = {}
  awayTeam: Optional[Teams] = {}
  status: Optional[str] = None
  venue: Optional[str] = None
  homeScore: Optional[int] = None
  awayScore: Optional[int] = None
  overtime: Optional[bool] = None
  shootout: Optional[bool] = None
  startTime: Optional[datetime] = None
  published: Optional[bool] = False


class MatchdayBase(MongoBaseModel):
  name: str = Field(...)
  alias: str = Field(...)
  type: str = Field(...)  # make enum, "Playoffs", "Round Robin"
  startDate: datetime = None
  endDate: datetime = None
  createStandings: bool = False
  createStats: bool = False
  published: bool = False
  matches: List[MatchBase] = []
  standings: List[Standings] = []

  @validator('startDate', 'endDate', pre=True, always=True)
  def empty_str_to_none(cls, v):
    return None if v == "" else v

  @validator('name', 'alias', 'type', pre=True, always=True)
  def prevent_null_value(cls, v):
    if v is None or v == "":
      raise ValueError("Field cannot be null or empty string")
    return v


class MatchdayDB(MatchdayBase):
  pass


class MatchdayUpdate(MongoBaseModel):
  name: Optional[str] = "DEFAULT"
  alias: Optional[str] = "DEFAULT"
  type: Optional[str] = "DEFAULT"
  startDate: Optional[datetime] = None
  endDate: Optional[datetime] = None
  createStandings: Optional[bool] = False
  createStats: Optional[bool] = False
  published: Optional[bool] = False
  matches: Optional[List[MatchBase]] = []
  standings: Optional[List[Standings]] = []


  @validator('startDate', 'endDate', pre=True, always=True)
  def empty_str_to_none(cls, v):
    return None if v == "" else v

  @validator('name', 'alias', 'type', pre=True, always=True)
  def prevent_null_value(cls, v):
    if v is None or v == "":
      raise ValueError("Field cannot be null or empty string")
    return v


class RoundBase(MongoBaseModel):
  name: str = Field(...)
  alias: str = Field(...)
  createStandings: bool = False
  createStats: bool = False
  matchdaysType: str = Field(...)
  matchdaysSortedBy: str = Field(...)
  startDate: datetime = None
  endDate: datetime = None
  published: bool = False
  matchdays: List[MatchdayBase] = []
  standings: List[Standings] = []

  @validator('startDate', 'endDate', pre=True, always=True)
  def empty_str_to_none(cls, v):
    return None if v == "" else v

  @validator('name', 'alias', 'matchdaysType', 'matchdaysSortedBy', pre=True, always=True)
  def prevent_null_value(cls, v):
    if v is None or v == "":
      raise ValueError("Field cannot be null or empty string")
    return v
  

class RoundDB(RoundBase):
  pass


class RoundUpdate(MongoBaseModel):
  name: Optional[str] = "DEFAULT"
  alias: Optional[str] = "DEFAULT"
  createStandings: Optional[bool] = False
  createStats: Optional[bool] = False
  matchdaysType: Optional[str] = "DEFAULT"
  matchdaysSortedBy: Optional[str] = "DEFAULT"
  startDate: Optional[datetime] = None
  endDate: Optional[datetime] = None
  published: Optional[bool] = False
  matchdays: Optional[List[MatchdayBase]] = []
  standings: Optional[List[Standings]] = []

  @validator('startDate', 'endDate', pre=True, always=True)
  def empty_str_to_none(cls, v):
    return None if v == "" else v

  @validator('name', 'alias', 'matchdaysType', 'matchdaysSortedBy', pre=True, always=True)
  def prevent_null_value(cls, v):
    if v is None or v == "":
      raise ValueError("Field cannot be null or empty string")
    return v
  

class SeasonBase(MongoBaseModel):
  name: str = Field(...)
  alias: str = Field(...)
  published: bool = False
  rounds: List[RoundBase] = []

  @validator('name', 'alias', pre=True, always=True)
  def prevent_null_value(cls, v):
    if v is None or v == "":
      raise ValueError("Field cannot be null or empty string")
    return v
  
class SeasonDB(SeasonBase):
  pass


class SeasonUpdate(MongoBaseModel):
  name: Optional[str] = "DEFAULT"
  alias: Optional[str] = "DEFAULT"
  published: Optional[bool] = False
  rounds: Optional[List[RoundBase]] = []
  
  @validator('name', 'alias', pre=True, always=True)
  def prevent_null_value(cls, v):
    if v is None or v == "":
      raise ValueError("Field cannot be null or empty string")
    return v
  
# --------


class TournamentBase(MongoBaseModel):
  name: str = Field(...)
  alias: str = Field(...)
  tinyName: str = Field(...)
  ageGroup: str = Field(...)
  published: bool = False
  active: bool = False
  external: bool = False
  website: HttpUrl = None
  seasons: List[SeasonBase] = []
  legacyId: int = None

  @validator('website', pre=True, always=True)
  def empty_str_to_none(cls, v):
    return None if v == "" else v

  @validator('name', 'alias', 'tinyName', 'ageGroup', pre=True, always=True)
  def prevent_null_value(cls, v):
    if v is None or v == "":
      raise ValueError("Field cannot be null or empty string")
    return v
    

class TournamentDB(TournamentBase):
  pass


class TournamentUpdate(MongoBaseModel):
  name: Optional[str] = "DEFAULT"
  alias: Optional[str] = "DEFAULT"
  tinyName: Optional[str] = "DEFAULT"
  ageGroup: Optional[str] = "DEFAULT"
  published: Optional[bool] = False
  active: Optional[bool] = False
  external: Optional[bool] = False
  website: Optional[HttpUrl] = None
  seasons: Optional[List[SeasonBase]] = None

  @validator('website', pre=True, always=True)
  def empty_str_to_none(cls, v):
    return None if v == "" else v

  @validator('name', 'alias', 'tinyName', 'ageGroup', pre=True, always=True)
  def prevent_null_value(cls, v):
    if v is None or v == "":
      raise ValueError("Field cannot be null or empty string")
    return v
