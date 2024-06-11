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


class MatchTeam(BaseModel):
  name: str = Field(...)
  alias: str = Field(...)
  fullName: str = Field(...)
  shortName: str = Field(...)
  tinyName: str = Field(...)
  logo: HttpUrl = None


class MatchHead(BaseModel):
  matchId: int = 0
  tournamant: MatchTournament = None
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
  startTime: datetime = None
  published: bool = False


class EventPlayer(BaseModel):
  firstName: str = Field(...)
  lastName: str = Field(...)
  jerseyNumber: int = 0


# --- sub documents with _id (updateable and deleteable)


class RosterPlayer(MongoBaseModel):
  firstName: str = Field(...)
  lastName: str = Field(...)
  jerseyNumber: int = Field(...)
  position: str = Field(...)
  isCaptain: bool = False
  isAssitant: bool = False
  passNumber: str = Field(...)
  goals: int = 0
  assists: int = 0
  penaltyMinutes: int = 0


class Roster(BaseModel):
  home: List[RosterPlayer] = []
  away: List[RosterPlayer] = []


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
  matchHead: MatchHead = Field(...)
  roster: Roster = {}
  scoreEvents: List[ScoreEvent] = []
  penaltyEvents: List[PenaltyEvent] = []


class MatchDB(MatchBase):
  pass


class MatchUpdate(MongoBaseModel):
  matchHead: Optional[MatchHead] = None
  roster: Optional[Roster] = None
  scoreEvents: Optional[List[ScoreEvent]] = None
  penaltyEvents: Optional[List[PenaltyEvent]] = None
