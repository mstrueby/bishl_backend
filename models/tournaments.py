from bson import ObjectId
from datetime import datetime, date
from pydantic import Field, BaseModel, HttpUrl, validator
from typing import Optional, List, Dict
from models.matches import MatchBase
from utils import empty_str_to_none, prevent_empty_str, validate_dict_of_strings


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


class Teams(BaseModel):
  fullName: str = Field(...)
  shortName: str = Field(...)
  tinyName: str = Field(...)
  logo: HttpUrl = None

  @validator('logo', pre=True, always=True)
  def validate_logo(cls, v):
    return empty_str_to_none(v, 'logo')


class Settings(BaseModel):
  numOfPeriods: int = None
  periodLengthMin: int = None
  pointsWinReg: int = None
  pointsLossReg: int = None
  pointsDrawReg: int = None
  overtime: bool = None
  numOfPeriodsOvertime: int = None
  periodLengthMinOvertime: int = None
  pointsWinOvertime: int = None
  pointsLossOvertime: int = None
  shootout: bool = None
  pointsWinShootout: int = None
  pointsLossShootout: int = None


# ------------


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
  type: Dict[str, str] = Field(...)  # enum, "Playoffs", "Round Robin"
  startDate: datetime = None
  endDate: datetime = None
  createStandings: bool = False
  createStats: bool = False
  settings: Settings = None
  published: bool = False
  matches: List[MatchBase] = []
  standings: List[Standings] = []

  @validator('startDate', 'endDate', pre=True, always=True)
  def validate_strings(cls, v, field):
    return empty_str_to_none(v, field.name)

  @validator('name', 'alias', pre=True, always=True)
  def validate_null_strings(cls, v, field):
    return prevent_empty_str(v, field.name)

  @validator('type', pre=True, always=True)
  def validate_type(cls, v, field):
    return validate_dict_of_strings(v, field.name)


class MatchdayDB(MatchdayBase):
  pass


class MatchdayUpdate(MongoBaseModel):
  name: Optional[str] = "DEFAULT"
  alias: Optional[str] = "DEFAULT"
  type: Optional[Dict[str, str]] = {}
  startDate: Optional[datetime] = None
  endDate: Optional[datetime] = None
  createStandings: Optional[bool] = False
  createStats: Optional[bool] = False
  settings: Optional[Settings] = None
  published: Optional[bool] = False
  matches: Optional[List[MatchBase]] = []
  standings: Optional[List[Standings]] = []

  @validator('startDate', 'endDate', pre=True, always=True)
  def validate_strings(cls, v, field):
    return empty_str_to_none(v, field.name)

  @validator('name', 'alias', pre=True, always=True)
  def validate_null_strings(cls, v, field):
    return prevent_empty_str(v, field.name)

  @validator('type', pre=True, always=True)
  def validate_type(cls, v, field):
    return validate_dict_of_strings(v, field.name)


class RoundBase(MongoBaseModel):
  name: str = Field(...)
  alias: str = Field(...)
  createStandings: bool = False
  createStats: bool = False
  matchdaysType: Dict[str, str] = Field(...)
  matchdaysSortedBy: Dict[str, str] = Field(...)
  startDate: datetime = None
  endDate: datetime = None
  settings: Settings = None
  published: bool = False
  matchdays: List[MatchdayBase] = []
  standings: List[Standings] = []

  @validator('startDate', 'endDate', pre=True, always=True)
  def validate_strings(cls, v, field):
    return empty_str_to_none(v, field.name)

  @validator('name', 'alias', pre=True, always=True)
  def validate_null_strings(cls, v, field):
    return prevent_empty_str(v, field.name)

  @validator('matchdaysType', 'matchdaysSortedBy', pre=True, always=True)
  def validate_type(cls, v, field):
    return validate_dict_of_strings(v, field.name)


class RoundDB(RoundBase):
  pass


class RoundUpdate(MongoBaseModel):
  name: Optional[str] = "DEFAULT"
  alias: Optional[str] = "DEFAULT"
  createStandings: Optional[bool] = False
  createStats: Optional[bool] = False
  matchdaysType: Optional[Dict[str, str]] = {}
  matchdaysSortedBy: Optional[Dict[str, str]] = {}
  startDate: Optional[datetime] = None
  endDate: Optional[datetime] = None
  settings: Optional[Settings] = None
  published: Optional[bool] = False
  matchdays: Optional[List[MatchdayBase]] = []
  standings: Optional[List[Standings]] = []

  @validator('startDate', 'endDate', pre=True, always=True)
  def validate_strings(cls, v, field):
    return empty_str_to_none(v, field.name)

  @validator('name', 'alias', pre=True, always=True)
  def validate_null_strings(cls, v, field):
    return prevent_empty_str(v, field.name)

  @validator('matchdaysType', 'matchdaysSortedBy', pre=True, always=True)
  def validate_type(cls, v, field):
    return validate_dict_of_strings(v, field.name)


class SeasonBase(MongoBaseModel):
  name: str = Field(...)
  alias: str = Field(...)
  published: bool = False
  rounds: List[RoundBase] = []

  @validator('name', 'alias', pre=True, always=True)
  def validate_null_strings(cls, v, field):
    return prevent_empty_str(v, field.name)


class SeasonDB(SeasonBase):
  pass


class SeasonUpdate(MongoBaseModel):
  name: Optional[str] = "DEFAULT"
  alias: Optional[str] = "DEFAULT"
  published: Optional[bool] = False
  rounds: Optional[List[RoundBase]] = []

  @validator('name', 'alias', pre=True, always=True)
  def validate_null_strings(cls, v, field):
    return prevent_empty_str(v, field.name)


# --------


class TournamentBase(MongoBaseModel):
  name: str = Field(...)
  alias: str = Field(...)
  tinyName: str = Field(...)
  ageGroup: Dict[str, str] = Field(...)
  published: bool = False
  active: bool = False
  external: bool = False
  website: HttpUrl = None
  defaultSettings: Settings = None
  seasons: List[SeasonBase] = None
  legacyId: int = None

  @validator('website', pre=True, always=True)
  def validate_string(cls, v, field):
    return empty_str_to_none(v, field.name)

  @validator('name', 'alias', 'tinyName', pre=True, always=True)
  def validate_null_strings(cls, v, field):
    return prevent_empty_str(v, field.name)

  @validator('ageGroup', pre=True, always=True)
  def validate_type(cls, v, field):
    return validate_dict_of_strings(v, field.name)


class TournamentDB(TournamentBase):
  pass


class TournamentUpdate(MongoBaseModel):
  name: Optional[str] = "DEFAULT"
  alias: Optional[str] = "DEFAULT"
  tinyName: Optional[str] = "DEFAULT"
  ageGroup: Optional[Dict[str, str]] = {}
  published: Optional[bool] = False
  active: Optional[bool] = False
  external: Optional[bool] = False
  website: Optional[HttpUrl] = None
  defaultSettings: Optional[Settings] = None
  seasons: Optional[List[SeasonBase]] = None

  @validator('website', pre=True, always=True)
  def validate_string(cls, v, field):
    return empty_str_to_none(v, field.name)

  @validator('name', 'alias', 'tinyName', pre=True, always=True)
  def validate_null_strings(cls, v, field):
    return prevent_empty_str(v, field.name)

  @validator('ageGroup', pre=True, always=True)
  def validate_type(cls, v, field):
    return validate_dict_of_strings(v, field.name)
