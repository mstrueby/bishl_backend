from bson import ObjectId
from datetime import datetime
from pydantic import Field, BaseModel, HttpUrl, validator
from typing import Optional, List, Dict
from utils import prevent_empty_str, validate_dict_of_strings, validate_match_seconds
from models.assignments import Referee
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

class KeyValue(BaseModel):
  key: str = Field(...)
  value: str = Field(...)

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
  player_id: str = Field(...)
  firstName: str = Field(...)
  lastName: str = Field(...)
  jerseyNumber: int = 0


class RosterPlayer(BaseModel):
  player: EventPlayer = Field(...)
  playerPosition: Dict[str, str] = Field(...)
  passNumber: str = Field(...)
  goals: int = 0
  assists: int = 0
  points: int = 0
  penaltyMinutes: int = 0


class ScoresBase(MongoBaseModel):
  matchSeconds: str = Field(...)
  goalPlayer: EventPlayer = Field(...)
  assistPlayer: EventPlayer = None
  isPPG: bool = False
  isSHG: bool = False
  isGWG: bool = False

  @validator('matchSeconds', pre=True, always=True)
  def validate_match_seconds(cls, v, field):
    return validate_match_seconds(v, field.name)


class ScoresDB(ScoresBase):
  pass


class ScoresUpdate(MongoBaseModel):
  matchSeconds: Optional[str] = "00:00"
  goalPlayer: Optional[EventPlayer] = {}
  assistPlayer: Optional[EventPlayer] = None
  isPPG: Optional[bool] = False
  isSHG: Optional[bool] = False
  isGWG: Optional[bool] = False

  @validator('matchSeconds', pre=True, always=True)
  def validate_match_seconds(cls, v, field):
    return validate_match_seconds(v, field.name)


class PenaltiesBase(MongoBaseModel):
  matchSecondsStart: str = Field(...)
  matchSecondsEnd: str = None
  penaltyPlayer: EventPlayer = Field(...)
  penaltyCode: Dict[str, str] = Field(...)
  penaltyMinutes: int = Field(...)
  isGM: bool = False
  isMP: bool = False

  @validator('penaltyCode', pre=True, always=True)
  def validate_type(cls, v, field):
    return validate_dict_of_strings(v, field.name)

  @validator('matchSecondsStart', 'matchSecondsEnd', pre=True, always=True)
  def validate_match_seconds(cls, v, field):
    if field.name == 'matchSecondsEnd' and v is None:
      return None
    return validate_match_seconds(v, field.name)


class PenaltiesDB(PenaltiesBase):
  pass


class PenaltiesUpdate(MongoBaseModel):
  matchSecondsStart: Optional[str] = "00:00"
  matchSecondsEnd: Optional[str] = None
  penaltyPlayer: Optional[EventPlayer] = {}
  penaltyCode: Optional[Dict[str, str]] = {}
  penaltyMinutes: Optional[int] = 0
  isGM: Optional[bool] = False
  isMP: Optional[bool] = False

  @validator('penaltyCode', pre=True, always=True)
  def validate_type(cls, v, field):
    return validate_dict_of_strings(v, field.name)

  @validator('matchSecondsStart', 'matchSecondsEnd', pre=True, always=True)
  def validate_match_seconds(cls, v, field):
    if field.name == 'matchSecondsEnd' and v is None:
      return None
    return validate_match_seconds(v, field.name)


class MatchStats(BaseModel):
  gamePlayed: int = 0
  goalsFor: int = 0
  goalsAgainst: int = 0
  points: int = 0
  win: int = 0
  loss: int = 0
  draw: int = 0
  otWin: int = 0
  otLoss: int = 0
  soWin: int = 0
  soLoss: int = 0


class MatchStatsUpdate(BaseModel):
  gamePlayed: Optional[int] = 0
  goalsFor: Optional[int] = 0
  goalsAgainst: Optional[int] = 0
  points: Optional[int] = 0
  win: Optional[int] = 0
  loss: Optional[int] = 0
  draw: Optional[int] = 0
  otWin: Optional[int] = 0
  otLoss: Optional[int] = 0
  soWin: Optional[int] = 0
  soLoss: Optional[int] = 0


class MatchTeam(BaseModel):
  clubAlias: str = None
  teamAlias: str = Field(...)
  #teamId: str = None
  name: str = Field(...)
  fullName: str = Field(...)
  shortName: str = Field(...)
  tinyName: str = Field(...)
  logo: HttpUrl = None
  roster: List[RosterPlayer] = []
  scores: List[ScoresBase] = []
  penalties: List[PenaltiesBase] = []
  stats: MatchStats = {}

  @validator('teamAlias', 'name', 'fullName', 'shortName', 'tinyName', pre=True, always=True)
  def validate_null_strings(cls, v, field):
    return prevent_empty_str(v, field.name)


class MatchTeamUpdate(BaseModel):
  clubAlias: Optional[str] = None
  teamAlias: Optional[str] = "DEFAULT"
  #teamId: Optional[str] = None
  name: Optional[str] = "DEFAULT"
  fullName: Optional[str] = "DEFAULT"
  shortName: Optional[str] = "DEFAULT"
  tinyName: Optional[str] = "DEFAULT"
  logo: Optional[HttpUrl] = None
  roster: Optional[List[RosterPlayer]] = []
  scores: Optional[List[ScoresBase]] = []
  penalties: Optional[List[PenaltiesBase]] = []
  stats: Optional[MatchStats] = {}

  @validator('teamAlias', 'name', 'fullName', 'shortName', 'tinyName', pre=True, always=True)
  def validate_null_strings(cls, v, field):
    return prevent_empty_str(v, field.name)


# --- main document


class MatchBase(MongoBaseModel):
  matchId: int = 0
  tournament: MatchTournament = None
  season: MatchSeason = None
  round: MatchRound = None
  matchday: MatchMatchday = None
  home: MatchTeam = None
  away: MatchTeam = None
  referee1: Referee = None
  referee2: Referee = None
  matchStatus: KeyValue = Field(default_factory=lambda: KeyValue(key="SCHEDULED", value="angesetzt"))
  finishType: KeyValue = Field(default_factory=lambda: KeyValue(key='REGULAR', value='Regulär'))
  venue: str = None
  startDate: datetime = None
  published: bool = False

  ##@validator('matchStatus', pre=True, always=True)
  #def validate_type(cls, v, field):
  #  return validate_dict_of_strings(v, field.name)


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
  referee1: Optional[Referee] = None
  referee2: Optional[Referee] = None
  matchStatus: Optional[KeyValue] = {}
  finishType: Optional[KeyValue] = {}
  venue: Optional[str] = None
  startDate: Optional[datetime] = None
  published: Optional[bool] = False

  #@validator('matchStatus', pre=True, always=True)
  #def validate_type(cls, v, field):
  #  return validate_dict_of_strings(v, field.name)
