from bson import ObjectId
from datetime import datetime, date, time
from pydantic import Field, BaseModel, HttpUrl, validator
from typing import Optional, List, Dict
#from models.clubs import TeamBase


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


# --- sub documents without _id


class MatchTournament(BaseModel):
  name: str = Field(...)
  alias: str = Field(...)
  
class MatchSeason(BaseModel):
  name: str = Field(...)
  alias: str = Field(...)


class MatchRound(BaseModel):
  name: str = Field(...)
  alias: str = Field(...)


class MatchMatchday(BaseModel):
  name: str = Field(...)
  alias: str = Field(...)

class RosterPlayer(BaseModel):
  firstName: str = Field(...)
  lastName: str = Field(...)
  jerseyNumber: int = Field(...)
  position: str = Field(...)
  isCaptain: bool = False
  isAssistant: bool = False
  passNumber: str = Field(...)
  goals: int = 0
  assists: int = 0
  penaltyMinutes: int = 0


class MatchTeam(BaseModel):
  fullName: str = Field(...)
  shortName: str = Field(...)
  tinyName: str = Field(...)
  logo: HttpUrl = None,
  roster: List[RosterPlayer] = []

class MatchTeamUpdate(BaseModel):
  fullName: Optional[str] = "DEFAULT"
  shortName: Optional[str] = "DEFAULT"
  tinyName: Optional[str] = "DEFAULT"
  logo: Optional[HttpUrl] = None,
  roster: Optional[List[RosterPlayer]] = []


class EventPlayer(BaseModel):
  firstName: str = Field(...)
  lastName: str = Field(...)
  jerseyNumber: int = 0


# --- sub documents with _id (updateable and deleteable)




class ScoreEvent(MongoBaseModel):
  matchTime: time = Field(...)
  team: MatchTeam = Field(...)
  goalPlayer: EventPlayer = Field(...)
  assistPlayer: Optional[EventPlayer] = None
  isGWG: bool = False
  isPPG: bool = False
  isSHG: bool = False


class PenaltyEvent(MongoBaseModel):
  matchTimeStart: time = Field(...)
  matchTimeEnd: time = None
  team: MatchTeam = Field(...)
  penaltyPlayer: EventPlayer = Field(...)
  penaltyCode: str = Field(...)
  penaltyMinutes: int = Field(...)
  isGM: bool = False
  isMP: bool = False


# --- main document


class MatchBase(MongoBaseModel):
  matchId: int = 0
  tournament: MatchTournament = None
  season: MatchSeason = None
  round: MatchRound = None
  matchday: MatchMatchday = None
  homeTeam: MatchTeam = None
  awayTeam: MatchTeam = None
  status: str = Field(...)
  venue: str = None
  homeScore: int = None
  awayScore: int = None
  overtime: bool = False
  shootout: bool = False
  startDate: datetime = None
  published: bool = False
  scoreEvents: List[ScoreEvent] = []
  penaltyEvents: List[PenaltyEvent] = []


class MatchDB(MatchBase):
  pass


class MatchUpdate(MongoBaseModel):
  matchId: Optional[int] = None
  tournament: Optional[MatchTournament] = None
  season: Optional[MatchSeason] = None
  round: Optional[MatchRound] = None
  matchday: Optional[MatchMatchday] = None
  homeTeam: Optional[MatchTeamUpdate] = None
  awayTeam: Optional[MatchTeamUpdate] = None
  status: Optional[str] = "DEFAULT"
  venue: Optional[str] = None
  homeScore: Optional[int] = None
  awayScore: Optional[int] = None
  overtime: Optional[bool] = False
  shootout: Optional[bool] = False
  startDate: Optional[datetime] = None
  published: Optional[bool] = False
  scoreEvents: Optional[List[ScoreEvent]] = None
  penaltyEvents: Optional[List[PenaltyEvent]] = None
