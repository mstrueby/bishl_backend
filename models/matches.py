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


class EventPlayer(BaseModel):
  firstName: str = Field(...)
  lastName: str = Field(...)
  jerseyNumber: int = 0


class RosterPlayer(BaseModel):
  player: EventPlayer = Field(...)
  position: str = Field(...)
  isCaptain: bool = False
  isAssistant: bool = False
  passNumber: str = Field(...)
  goals: int = 0
  assists: int = 0
  penaltyMinutes: int = 0


class ScoresBase(MongoBaseModel):
  matchSeconds: int = Field(...)
  goalPlayer: EventPlayer = Field(...)
  assistPlayer: EventPlayer = None
  isPPG: bool = False
  isSHG: bool = False
  isGWG: bool = False


class ScoresDB(ScoresBase):
  pass


class ScoresUpdate(MongoBaseModel):
  matchSeconds: Optional[int] = 0
  goalPlayer: Optional[EventPlayer] = {}
  assistPlayer: Optional[EventPlayer] = None
  isPPG: Optional[bool] = False
  isSHG: Optional[bool] = False
  isGWG: Optional[bool] = False


class PenaltiesBase(MongoBaseModel):
  matchTimeStart: time = Field(...)
  matchTimeEnd: time = None
  penaltyPlayer: EventPlayer = Field(...)
  penaltyCode: str = Field(...)
  penaltyMinutes: int = Field(...)
  isGM: bool = False
  isMP: bool = False

class PenaltiesDB(PenaltiesBase):
  pass

class PenaltiesUpdate(MongoBaseModel):
  matchTimeStart: Optional[time] = None
  matchTimeEnd: Optional[time] = None
  penaltyPlayer: Optional[EventPlayer] = {}
  penaltyCode: Optional[str] = None
  penaltyMinutes: Optional[int] = 0
  isGM: Optional[bool] = False
  isMP: Optional[bool] = False

class MatchTeam(BaseModel):
  fullName: str = Field(...)
  shortName: str = Field(...)
  tinyName: str = Field(...)
  logo: HttpUrl = None
  roster: List[RosterPlayer] = []
  scores: List[ScoresBase] = []
  penalties: List[PenaltiesBase] = []


class MatchTeamUpdate(BaseModel):
  fullName: Optional[str] = "DEFAULT"
  shortName: Optional[str] = "DEFAULT"
  tinyName: Optional[str] = "DEFAULT"
  logo: Optional[HttpUrl] = None
  roster: Optional[List[RosterPlayer]] = []
  scores: Optional[List[ScoresBase]] = None
  penalties: Optional[List[PenaltiesBase]] = []


# --- main document


class MatchBase(MongoBaseModel):
  matchId: int = 0
  tournament: MatchTournament = None
  season: MatchSeason = None
  round: MatchRound = None
  matchday: MatchMatchday = None
  home: MatchTeam = None
  away: MatchTeam = None
  status: str = Field(...)
  venue: str = None
  homeScore: int = None
  awayScore: int = None
  overtime: bool = False
  shootout: bool = False
  startDate: datetime = None
  published: bool = False


class MatchDB(MatchBase):
  pass


class MatchUpdate(MongoBaseModel):
  matchId: Optional[int] = None
  tournament: Optional[MatchTournament] = None
  season: Optional[MatchSeason] = None
  round: Optional[MatchRound] = None
  matchday: Optional[MatchMatchday] = None
  home: Optional[MatchTeamUpdate] = None
  away: Optional[MatchTeamUpdate] = None
  status: Optional[str] = "DEFAULT"
  venue: Optional[str] = None
  homeScore: Optional[int] = None
  awayScore: Optional[int] = None
  overtime: Optional[bool] = False
  shootout: Optional[bool] = False
  startDate: Optional[datetime] = None
  published: Optional[bool] = False
