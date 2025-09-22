from bson import ObjectId
from datetime import datetime
from pydantic import Field, BaseModel, HttpUrl, validator
from typing import Optional, List, Dict
from utils import prevent_empty_str, validate_dict_of_strings, validate_match_time
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
  playerId: str = Field(...)
  firstName: str = Field(...)
  lastName: str = Field(...)
  jerseyNumber: int = 0
  displayFirstName: Optional[str] = None
  displayLastName: Optional[str] = None
  imageUrl: Optional[HttpUrl] = None
  imageVisible: Optional[bool] = False


class RosterPlayer(BaseModel):
  player: EventPlayer = Field(...)
  playerPosition: Dict[str, str] = Field(...)
  passNumber: str = Field(...)
  goals: int = 0
  assists: int = 0
  points: int = 0
  penaltyMinutes: int = 0
  called: bool = False


class ScoresBase(MongoBaseModel):
  matchTime: str = Field(...)
  goalPlayer: EventPlayer = Field(...)
  assistPlayer: Optional[EventPlayer] = None
  isPPG: bool = False
  isSHG: bool = False
  isGWG: bool = False

  @validator('matchTime', pre=True, always=True)
  def validate_match_time(cls, v, field):
    return validate_match_time(v, field.name)


class ScoresDB(ScoresBase):
  pass


class ScoresUpdate(MongoBaseModel):
  matchTime: Optional[str] = "00:00"
  goalPlayer: Optional[EventPlayer] = Field(default_factory=dict)
  assistPlayer: Optional[EventPlayer] = None
  isPPG: Optional[bool] = False
  isSHG: Optional[bool] = False
  isGWG: Optional[bool] = False
"""
  @validator('matchTime', pre=True, always=True)
  def validate_match_time(cls, v, field):
    return validate_match_time(v, field.name)
"""


class PenaltiesBase(MongoBaseModel):
  matchTimeStart: str = Field(...)
  matchTimeEnd: Optional[str] = None
  penaltyPlayer: EventPlayer = Field(...)
  penaltyCode: Dict[str, str] = Field(...)
  penaltyMinutes: int = Field(...)
  isGM: bool = False
  isMP: bool = False

  @validator('penaltyCode', pre=True, always=True)
  def validate_type(cls, v, field):
    return validate_dict_of_strings(v, field.name)
"""
  @validator('matchTimeStart', 'matchTimeEnd', pre=True, always=True)
  def validate_match_time(cls, v, field):
    if field.name == 'matchTimeEnd' and v is None:
      return None
    return validate_match_time(v, field.name)

"""

class PenaltiesDB(PenaltiesBase):
  pass


class PenaltiesUpdate(MongoBaseModel):
  matchTimeStart: Optional[str] = "00:00"
  matchTimeEnd: Optional[str] = None
  penaltyPlayer: Optional[EventPlayer] = Field(default_factory=dict)
  penaltyCode: Optional[Dict[str, str]] = Field(default_factory=dict)
  penaltyMinutes: Optional[int] = 0
  isGM: Optional[bool] = False
  isMP: Optional[bool] = False

  @validator('penaltyCode', pre=True, always=True)
  def validate_type(cls, v, field):
    if v is None:
      return v
    return validate_dict_of_strings(v, field.name)

  @validator('matchTimeStart', 'matchTimeEnd', pre=True, always=True)
  def validate_match_time(cls, v, field):
    if field.name == 'matchTimeEnd' and v is None:
      return None
    return validate_match_time(v, field.name)


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


class Coach(BaseModel):
  firstName: Optional[str] = None
  lastName: Optional[str] = None
  licence: Optional[str] = None


class Staff(BaseModel):
  firstName: str = Field(...)
  lastName: str = Field(...)
  role: Optional[str] = None


class MatchTeam(BaseModel):
  clubId: Optional[str] = None
  clubName: Optional[str] = None
  clubAlias: Optional[str] = None
  teamId: Optional[str] = None
  teamAlias: str = Field(...)
  name: str = Field(...)
  fullName: str = Field(...)
  shortName: str = Field(...)
  tinyName: str = Field(...)
  logo: Optional[HttpUrl] = None
  roster: Optional[List[RosterPlayer]] = Field(default_factory=list)
  rosterPublished: Optional[bool] = False
  coach: Coach = Field(default_factory=Coach)
  staff: Optional[List[Staff]] = Field(default_factory=list)
  scores: Optional[List[ScoresBase]] = Field(default_factory=list)
  penalties: Optional[List[PenaltiesBase]] = Field(default_factory=list)
  stats: Optional[MatchStats] = Field(default_factory=dict)

  @validator('teamAlias',
             'name',
             'fullName',
             'shortName',
             'tinyName',
             pre=True,
             always=True)
  def validate_null_strings(cls, v, field):
    return prevent_empty_str(v, field.name)


class MatchTeamUpdate(BaseModel):
  clubId: Optional[str] = None
  clubName: Optional[str] = None
  clubAlias: Optional[str] = None
  teamId: Optional[str] = None
  teamAlias: Optional[str] = "DEFAULT"
  name: Optional[str] = "DEFAULT"
  fullName: Optional[str] = "DEFAULT"
  shortName: Optional[str] = "DEFAULT"
  tinyName: Optional[str] = "DEFAULT"
  logo: Optional[HttpUrl] = None
  roster: Optional[List[RosterPlayer]] = Field(default_factory=list)
  rosterPublished: Optional[bool] = None
  coach: Optional[Coach] = Field(default_factory=Coach)
  staff: Optional[List[Staff]] = Field(default_factory=list)
  scores: Optional[List[ScoresBase]] = Field(default_factory=list)
  penalties: Optional[List[PenaltiesBase]] = Field(default_factory=list)
  stats: Optional[MatchStats] = Field(default_factory=dict)

  @validator('teamAlias',
             'name',
             'fullName',
             'shortName',
             'tinyName',
             pre=True,
             always=True)
  def validate_null_strings(cls, v, field):
    return prevent_empty_str(v, field.name)


class MatchVenue(BaseModel):
  venueId: Optional[str] = None
  name: str = Field(...)
  alias: str = Field(...)


# --- main document


class MatchBase(MongoBaseModel):
  matchId: int = 0
  tournament: Optional[MatchTournament] = None
  season: Optional[MatchSeason] = None
  round: Optional[MatchRound] = None
  matchday: Optional[MatchMatchday] = None
  home: Optional[MatchTeam] = None
  away: Optional[MatchTeam] = None
  referee1: Optional[Referee] = None
  referee2: Optional[Referee] = None
  matchStatus: KeyValue = Field(
      default_factory=lambda: KeyValue(key="SCHEDULED", value="angesetzt"))
  finishType: KeyValue = Field(
      default_factory=lambda: KeyValue(key='REGULAR', value='Regulär'))
  venue: Optional[MatchVenue] = None
  startDate: Optional[datetime] = None
  published: bool = False
  matchSheetComplete: bool = False

  ##@validator('matchStatus', pre=True, always=True)
  #def validate_type(cls, v, field):
  #  return validate_dict_of_strings(v, field.name)


class MatchDB(MatchBase):
  pass


class MatchListTeam(BaseModel):
  clubId: Optional[str] = None
  clubName: Optional[str] = None
  clubAlias: Optional[str] = None
  teamId: Optional[str] = None
  teamAlias: str = Field(...)
  name: str = Field(...)
  fullName: str = Field(...)
  shortName: str = Field(...)
  tinyName: str = Field(...)
  logo: Optional[HttpUrl] = None
  rosterPublished: Optional[bool] = False
  stats: Optional[MatchStats] = Field(default_factory=dict)

  @validator('teamAlias',
             'name',
             'fullName',
             'shortName',
             'tinyName',
             pre=True,
             always=True)
  def validate_null_strings(cls, v, field):
    return prevent_empty_str(v, field.name)


class MatchListBase(MongoBaseModel):
  matchId: int = 0
  tournament: Optional[MatchTournament] = None
  season: Optional[MatchSeason] = None
  round: Optional[MatchRound] = None
  matchday: Optional[MatchMatchday] = None
  home: Optional[MatchListTeam] = None
  away: Optional[MatchListTeam] = None
  referee1: Optional[Referee] = None
  referee2: Optional[Referee] = None
  matchStatus: KeyValue = Field(
      default_factory=lambda: KeyValue(key="SCHEDULED", value="angesetzt"))
  finishType: KeyValue = Field(
      default_factory=lambda: KeyValue(key='REGULAR', value='Regulär'))
  venue: Optional[MatchVenue] = None
  startDate: Optional[datetime] = None
  published: bool = False
  matchSheetComplete: bool = False


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
  matchStatus: Optional[KeyValue] = Field(default_factory=dict)
  finishType: Optional[KeyValue] = Field(default_factory=dict)
  venue: Optional[MatchVenue] = None
  startDate: Optional[datetime] = None
  published: Optional[bool] = False
  matchSheetComplete: Optional[bool] = False

  #@validator('matchStatus', pre=True, always=True)
  #def validate_type(cls, v, field):
  #  return validate_dict_of_strings(v, field.name)
