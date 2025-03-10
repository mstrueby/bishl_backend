from bson import ObjectId
from pydantic import Field, BaseModel, HttpUrl
from typing import Optional, List
from datetime import datetime
from enum import Enum
from models.matches import MatchTournament, MatchSeason, MatchRound, MatchMatchday


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


class PositionEnum(str, Enum):
  SKATER = 'Skater'
  GOALIE = 'Goalie'


class SourceEnum(str, Enum):
  ISHD = 'ISHD'
  BISHL = 'BISHL'


class AssignedTeams(BaseModel):
  teamId: str = Field(...)
  teamName: str = Field(...)
  teamAlias: str = Field(...)
  teamIshdId: str = Field(...)
  passNo: str = Field(...)
  source: SourceEnum = Field(default=SourceEnum.BISHL)
  modifyDate: Optional[datetime] = None
  active: bool = False
  jerseyNo: Optional[int] = None


class AssignedClubs(BaseModel):
  clubId: str = Field(...)
  clubName: str = Field(...)
  clubAlias: str = Field(...)
  clubIshdId: int = Field(...)
  teams: list[AssignedTeams] = Field(...)

class TeamInput(BaseModel):
  teamId: str = Field(...)
  passNo: str = Field(...)
  jerseyNo: Optional[int] = None
  active: Optional[bool] = False
  source: Optional[SourceEnum] = Field(default=SourceEnum.BISHL)
  modifyDate: Optional[datetime] = None

class AssignedTeamsInput(BaseModel):
  clubId: str = Field(...)
  teams: List[TeamInput] = Field(...)

class PlayerStatsTeam(BaseModel):
  #team_id: str = Field(...)
  name: str = Field(...)
  fullName: str = Field(...)
  shortName: str = Field(...)
  tinyName: str = Field(...)


class PlayerStats(BaseModel):
  tournament: MatchTournament = Field(...)
  season: MatchSeason = Field(...)
  round: MatchRound = Field(...)
  matchday: Optional[MatchMatchday] = None
  team: PlayerStatsTeam = Field(...)
  gamesPlayed: int = Field(0)
  goals: int = Field(0)
  assists: int = Field(0)
  points: int = Field(0)
  penaltyMinutes: int = Field(0)


class PlayerBase(MongoBaseModel):
  firstName: str = Field(...)
  lastName: str = Field(...)
  birthdate: datetime = Field(..., description='format: yyyy-mm-dd hh:mi:ss')
  displayFirstName: str = Field(...)
  displayLastName: str = Field(...)
  nationality: Optional[str] = None
  position: PositionEnum = Field(default=PositionEnum.SKATER)
  fullFaceReq: bool = False
  source: SourceEnum = Field(default=SourceEnum.BISHL)
  assignedTeams: Optional[List[AssignedClubs]] = Field(default_factory=list)
  stats: Optional[List[PlayerStats]] = Field(default_factory=list)
  imageUrl: Optional[HttpUrl] = None
  imageVisible: bool = False
  legacyId: Optional[int] = None
  """
  @validator('firstName', 'lastName', 'position', pre=True, always=True)
  def validate_null_strings(cls, v, field):
    return prevent_empty_str(v, field.name)

  @validator('image', pre=True, always=True)
  def validate_strings(cls, v, field):
    return empty_str_to_none(v, field.name)
"""


class PlayerDB(PlayerBase):
  createDate: Optional[datetime] = None
  @property
  def something(self) -> str:
    return 'something'
    
  @property
  def ageGroup(self) -> str:
    """Calculate age group based on birth year dynamically"""
    if not self.birthdate:
      return "UNKNOWN"

    current_year = datetime.now().year
    birth_year = self.birthdate.year
    
    # Age group classification based on birth year
    if birth_year >= current_year - 7:  # 2018+ for current year 2025
      return "U8"
    elif birth_year >= current_year - 9:  # 2016-2017 for current year 2025
      return "U10"
    elif birth_year >= current_year - 12:  # 2013-2015 for current year 2025
      return "U13"
    elif birth_year >= current_year - 15:  # 2010-2012 for current year 2025
      return "U16"
    elif birth_year >= current_year - 18:  # 2007-2009 for current year 2025
      return "U19"
    else:  # 2006 and older for current year 2025
      # For adults, we could distinguish between MEN and WOMEN based on another field if needed
      # it should be sex, but it is not included in the data
      # return "MEN" if self.position == PositionEnum.SKATER else "WOMEN"
      return "ADULT"

class PlayerUpdate(MongoBaseModel):
  firstName: Optional[str] = None
  lastName: Optional[str] = None
  birthdate: Optional[datetime] = None
  displayFirstName: Optional[str] = None
  displayLastName: Optional[str] = None
  nationality: Optional[str] = None
  position: Optional[PositionEnum] = None
  fullFaceReq: Optional[bool] = None
  source: Optional[SourceEnum] = None
  assignedTeams: Optional[List[AssignedClubs]] = None
  stats: Optional[List[PlayerStats]] = None
  imageUrl: Optional[HttpUrl] = None
  imageVisible: Optional[bool] = None
  """
  @validator('firstName', 'lastName', pre=True, always=True)
  def validate_null_strings(cls, v, field):
    return prevent_empty_str(v, field.name)

  @validator('image', pre=True, always=True)
  def validate_strings(cls, v, field):
    return empty_str_to_none(v, field.name)
"""


# ---- ISHD Log Model

class IshdActionEnum(str, Enum):
  ADD_PLAYER = 'Add new Player'
  ADD_CLUB = 'Add club/team assignment'
  ADD_TEAM = 'Add team assigment'
  DEL_TEAM = 'Remove team assigment'
  DEL_CLUB = 'Remove club assignment'
  


class IshdLogPlayer(BaseModel):
  action: Optional[IshdActionEnum] = None
  firstName: str = Field(...)
  lastName: str = Field(...)
  birthdate: datetime = Field(...)


class IshdLogTeam(BaseModel):
  teamIshdId: str = Field(...)
  url: str = Field(...)
  players: Optional[List[IshdLogPlayer]] = None


class IshdLogClub(BaseModel):
  clubName: str = Field(...)
  ishdId: int = Field(...)
  teams: Optional[List[IshdLogTeam]] = None


class IshdLogBase(MongoBaseModel):
  processDate: datetime = Field(...)
  clubs: Optional[List[IshdLogClub]] = None
