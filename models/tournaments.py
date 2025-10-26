from bson import ObjectId
from datetime import datetime
from pydantic import Field, BaseModel, HttpUrl, field_validator
from typing import Optional, List, Dict
from utils import empty_str_to_none, prevent_empty_str, validate_dict_of_strings
from enum import Enum


class PyObjectId(ObjectId):

  @classmethod
  def __get_validators__(cls):
    yield cls.validate

  @classmethod
  def validate(cls, v, handler=None):
    if not ObjectId.is_valid(v):
      raise ValueError("Invalid objectid")
    return ObjectId(v)

  @classmethod
  def __get_pydantic_json_schema__(cls, core_schema, handler):
    return {"type": "string"}


class MongoBaseModel(BaseModel):
  id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")

  class Config:
    json_encoders = {ObjectId: str}


# sub documents


class Teams(BaseModel):
  fullName: str = Field(...)
  shortName: str = Field(...)
  tinyName: str = Field(...)
  logo: Optional[HttpUrl] = None

  @field_validator('logo', mode='before')
  @classmethod
  def validate_logo(cls, v, info):
    return empty_str_to_none(v, info.field_name)


class Standings(BaseModel):
  fullName: str = Field(...)
  shortName: str = Field(...)
  tinyName: str = Field(...)
  logo: Optional[HttpUrl] = None
  gamesPlayed: int = Field(...)
  goalsFor: int = Field(...)
  goalsAgainst: int = Field(...)
  points: int = Field(...)
  wins: int = Field(...)
  losses: int = Field(...)
  draws: int = Field(...)
  otWins: int = Field(...)
  otLosses: int = Field(...)
  soWins: int = Field(...)
  soLosses: int = Field(...)
  streak: Optional[List[str]] = Field(default_factory=list)


# settings at tournament level
class StandingsSettings(BaseModel):
  pointsWinReg: Optional[int] = Field(default=0)
  pointsLossReg: Optional[int] = Field(default=0)
  pointsDrawReg: Optional[int] = Field(default=0)
  pointsWinOvertime: Optional[int] = Field(default=0)
  pointsLossOvertime: Optional[int] = Field(default=0)
  pointsWinShootout: Optional[int] = Field(default=0)
  pointsLossShootout: Optional[int] = Field(default=0)


# settings on round and matchday level
class MatchSettings(BaseModel):
  numOfPeriods: Optional[int] = Field(default=0)
  periodLengthMin: Optional[int] = Field(default=0)
  overtime: Optional[bool] = Field(default=False)
  numOfPeriodsOvertime: Optional[int] = Field(default=0)
  periodLengthMinOvertime: Optional[int] = Field(default=0)
  shootout: Optional[bool] = Field(default=False)
  refereePoints: Optional[int] = Field(default=0)


# ------------
class MatchdayType(Enum):
  #PLAYOFFS = {"key": "PLAYOFFS", "value": "Playoffs", "sortOrder": 1}
  #REGULAR = {"key": "REGULAR", "value": "Regulär", "sortOrder": 2}
  PLAYOFFS = {"key": "PLAYOFFS", "value": "Playoffs"}
  REGULAR = {"key": "REGULAR", "value": "Regulär"}

class MatchdayOwner(BaseModel):
  clubId: Optional[str] = None
  clubName: Optional[str] = None
  clubAlias: Optional[str] = None

class MatchdayBase(MongoBaseModel):
  name: str = Field(...)
  alias: str = Field(...)
  type: Dict[str, str] = Field(...)
  startDate: Optional[datetime] = None
  endDate: Optional[datetime] = None
  createStandings: bool = False
  createStats: bool = False
  matchSettings: Optional[MatchSettings] = Field(default_factory=dict)
  published: bool = False
  standings: Optional[Dict[str, Standings]] = Field(default_factory=dict)
  owner: Optional[MatchdayOwner] = Field(default_factory=dict)

  @field_validator('startDate', 'endDate', mode='before')
  @classmethod
  def validate_strings(cls, v, info):
    return empty_str_to_none(v, info.field_name)

  @field_validator('name', 'alias', mode='before')
  @classmethod
  def validate_null_strings(cls, v, info):
    return prevent_empty_str(v, info.field_name)

class MatchdayDB(MatchdayBase):
  pass


class MatchdayUpdate(MongoBaseModel):
  name: Optional[str] = "DEFAULT"
  alias: Optional[str] = "DEFAULT"
  type: Optional[Dict[str, str]] = Field(default_factory=dict)
  startDate: Optional[datetime] = None
  endDate: Optional[datetime] = None
  createStandings: Optional[bool] = False
  createStats: Optional[bool] = False
  matchSettings: Optional[MatchSettings] = Field(default_factory=dict)
  published: Optional[bool] = False
  standings: Optional[Dict[str, Standings]] = Field(default_factory=dict)
  owner: Optional[MatchdayOwner] = Field(default_factory=dict)

  @field_validator('startDate', 'endDate', mode='before')
  @classmethod
  def validate_strings(cls, v, info):
    return empty_str_to_none(v, info.field_name)

  @field_validator('name', 'alias', mode='before')
  @classmethod
  def validate_null_strings(cls, v, info):
    return prevent_empty_str(v, info.field_name)


class RoundBase(MongoBaseModel):
  name: str = Field(...)
  alias: str = Field(...)
  sortOrder: int = Field(0)
  createStandings: bool = False
  createStats: bool = False
  matchdaysType: Dict[str, str] = Field(...)
  matchdaysSortedBy: Dict[str, str] = Field(...)
  startDate: Optional[datetime] = None
  endDate: Optional[datetime] = None
  matchSettings: Optional[MatchSettings] = Field(default_factory=dict)
  published: bool = False
  matchdays: Optional[List[MatchdayBase]] = Field(default_factory=list)
  standings: Optional[Dict[str, Standings]] = Field(default_factory=dict)

  @field_validator('startDate', 'endDate', mode='before')
  @classmethod
  def validate_strings(cls, v, info):
    return empty_str_to_none(v, info.field_name)

  @field_validator('name', 'alias', mode='before')
  @classmethod
  def validate_null_strings(cls, v, info):
    return prevent_empty_str(v, info.field_name)

  @field_validator('matchdaysType', 'matchdaysSortedBy', mode='before')
  @classmethod
  def validate_type(cls, v, info):
    return validate_dict_of_strings(v, info.field_name)


class RoundDB(RoundBase):
  pass


class RoundUpdate(MongoBaseModel):
  name: Optional[str] = "DEFAULT"
  alias: Optional[str] = "DEFAULT"
  sortOrder: Optional[int] = None
  createStandings: Optional[bool] = False
  createStats: Optional[bool] = False
  matchdaysType: Optional[Dict[str, str]] = Field(default_factory=dict)
  matchdaysSortedBy: Optional[Dict[str, str]] = Field(default_factory=dict)
  startDate: Optional[datetime] = None
  endDate: Optional[datetime] = None
  matchSettings: Optional[MatchSettings] = Field(default_factory=dict)
  published: Optional[bool] = False
  matchdays: Optional[List[MatchdayBase]] = Field(default_factory=list)
  standings: Optional[Dict[str, Standings]] = Field(default_factory=dict)

  @field_validator('startDate', 'endDate', mode='before')
  @classmethod
  def validate_strings(cls, v, info):
    return empty_str_to_none(v, info.field_name)

  @field_validator('name', 'alias', mode='before')
  @classmethod
  def validate_null_strings(cls, v, info):
    return prevent_empty_str(v, info.field_name)

  @field_validator('matchdaysType', 'matchdaysSortedBy', mode='before')
  @classmethod
  def validate_type(cls, v, info):
    return validate_dict_of_strings(v, info.field_name)


class SeasonBase(MongoBaseModel):
  name: str = Field(...)
  alias: str = Field(...)
  standingsSettings: Optional[StandingsSettings] = Field(default_factory=dict)
  published: bool = False
  rounds: Optional[List[RoundBase]] = Field(default_factory=list)

  @field_validator('name', 'alias', mode='before')
  @classmethod
  def validate_null_strings(cls, v, info):
    return prevent_empty_str(v, info.field_name)


class SeasonDB(SeasonBase):
  pass


class SeasonUpdate(MongoBaseModel):
  name: Optional[str] = "DEFAULT"
  alias: Optional[str] = "DEFAULT"
  standingsSettings: Optional[StandingsSettings] = Field(default_factory=dict)
  published: Optional[bool] = False
  rounds: Optional[List[RoundBase]] = Field(default_factory=list)

  @field_validator('name', 'alias', mode='before')
  @classmethod
  def validate_null_strings(cls, v, info):
    return prevent_empty_str(v, info.field_name)


# --------


class TournamentBase(MongoBaseModel):
  name: str = Field(...)
  alias: str = Field(...)
  tinyName: str = Field(...)
  ageGroup: Dict[str, str] = Field(...)
  published: bool = False
  active: bool = False
  external: bool = False
  website: Optional[HttpUrl] = None
  seasons: Optional[List[SeasonBase]] = Field(default_factory=list)
  legacyId: Optional[int] = None

  @field_validator('website', mode='before')
  @classmethod
  def validate_string(cls, v, info):
    return empty_str_to_none(v, info.field_name)

  @field_validator('name', 'alias', 'tinyName', mode='before')
  @classmethod
  def validate_null_strings(cls, v, info):
    return prevent_empty_str(v, info.field_name)

  @field_validator('ageGroup', mode='before')
  @classmethod
  def validate_type(cls, v, info):
    return validate_dict_of_strings(v, info.field_name)


class TournamentDB(TournamentBase):
  pass


class TournamentUpdate(MongoBaseModel):
  name: Optional[str] = "DEFAULT"
  alias: Optional[str] = "DEFAULT"
  tinyName: Optional[str] = "DEFAULT"
  ageGroup: Optional[Dict[str, str]] = Field(default_factory=dict)
  published: Optional[bool] = False
  active: Optional[bool] = False
  external: Optional[bool] = False
  website: Optional[HttpUrl] = None
  seasons: Optional[List[SeasonBase]] = Field(default_factory=list)

  @field_validator('website', mode='before')
  @classmethod
  def validate_string(cls, v, info):
    return empty_str_to_none(v, info.field_name)

  @field_validator('name', 'alias', 'tinyName', mode='before')
  @classmethod
  def validate_null_strings(cls, v, info):
    return prevent_empty_str(v, info.field_name)

  @field_validator('ageGroup', mode='before')
  @classmethod
  def validate_type(cls, v, info):
    return validate_dict_of_strings(v, info.field_name)