from bson import ObjectId
from datetime import date
from pydantic import Field, BaseModel, HttpUrl, validator
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

  
class Matches(BaseModel):
  matchId: str = Field(...)
  homeTeam: Teams = Field(...)
  awayTeam: Teams = Field(...)
  status: str = Field(...)
  venue: str = None
  homeScore: int = None
  awayScore: int = None
  overtime: bool = None
  shootout: bool = None
  startTime: date = None
  published: bool = Field(...)


class Matchdays(BaseModel):
  name: str = Field(...)
  type: str = Field(...)  # make enum, "Playoffs", "Round Robin"
  startDate: date = None
  endDate: date = None
  createStandings: bool = Field(...)
  createStats: bool = Field(...)
  published: bool = Field(...)
  matches: List[Matches] = None
  standings: List[Standings] = None


class Rounds(BaseModel):
  name: str = Field(...)
  createStandings: bool = Field(...)
  createStats: bool = Field(...)
  matchdaysType: str = Field(...)
  matchdaysSortedBy: str = Field(...)
  startDate: date = None
  endDate: date = None
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
  tinyName: str = Field(...)
  ageGroup: str = Field(...)
  published: bool = False
  active: bool = False
  external: bool = False
  website: HttpUrl = None
  seasons: List[Seasons] = None
  legacyId: int = None

class TournamentDB(TournamentBase):
  pass


class TournamentUpdate(MongoBaseModel):
  name: Optional[str] = None
  alias: Optional[str] = None
  tinyName: Optional[str] = None
  ageGroup: Optional[str] = None
  published: Optional[bool] = None
  active: Optional[bool] = None
  external: Optional[bool] = None
  website: Optional[HttpUrl] = None
  seasons: Optional[List[Seasons]] = None