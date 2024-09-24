from bson import ObjectId
from pydantic import Field, BaseModel, validator, HttpUrl
from typing import Optional, List
from datetime import datetime
from utils import prevent_empty_str, empty_str_to_none
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
  team_id: str = Field(...)
  team_name: str = Field(...)
  team_alias: str = Field(...)
  team_ishd_id: str = Field(...)
  pass_no: str = Field(...)
  source: SourceEnum = Field(default=SourceEnum.BISHL)
  modify_date: datetime = None


class AssignedClubs(BaseModel):
  club_id: str = Field(...)
  club_name: str = Field(...)
  club_alias: str = Field(...)
  club_ishd_id: int = Field(...)
  teams: list[AssignedTeams] = Field(...)


class AssignedTeamsInput(BaseModel):
  club_id: str = Field(...)
  teams: List[dict[str, str]] = Field(...)

class PlayerStatsTeam(BaseModel):
  team_id: str = Field(...)
  full_name: str = Field(...)
  short_name: str = Field(...)
  tiny_name: str = Field(...)

class PlayerStats(BaseModel):
  tournament: MatchTournament = Field(...)
  season: MatchSeason = Field(...)
  round: MatchRound = Field(...)
  matchday: MatchMatchday = Field(...)
  team: PlayerStatsTeam = Field(...)
  games_played: int = Field(0)
  goals: int = Field(0)
  assists: int = Field(0)
  points: int = Field(0)
  penalty_minutes: int = Field(0)


class PlayerBase(MongoBaseModel):
  firstname: str = Field(...)
  lastname: str = Field(...)
  birthdate: datetime = Field(..., description='format: yyyy-mm-dd hh:mi:ss')
  display_firstname: str = None
  display_lastname: str = None
  nationality: str = None
  position: PositionEnum = Field(default=PositionEnum.SKATER)
  full_face_req: bool = False
  source: SourceEnum = Field(default=SourceEnum.BISHL)
  assigned_teams: List[AssignedClubs] = []
  stats: List[PlayerStats] = []
  image: HttpUrl = None
  legacy_id: int = None
  """
  @validator('firstname', 'lastname', 'position', pre=True, always=True)
  def validate_null_strings(cls, v, field):
    return prevent_empty_str(v, field.name)

  @validator('image', pre=True, always=True)
  def validate_strings(cls, v, field):
    return empty_str_to_none(v, field.name)
"""


class PlayerDB(PlayerBase):
  create_date: datetime = None


class PlayerUpdate(MongoBaseModel):
  firstname: Optional[str]
  lastname: Optional[str]
  birthdate: Optional[datetime]
  display_firstname: Optional[str]
  display_lastname: Optional[str]
  nationality: Optional[str]
  position: Optional[PositionEnum]
  full_face_req: Optional[bool]
  source: Optional[SourceEnum]
  assigned_teams: Optional[List[AssignedClubs]]
  stats: Optional[List[PlayerStats]]
  image: Optional[HttpUrl]
  """
  @validator('firstname', 'lastname', pre=True, always=True)
  def validate_null_strings(cls, v, field):
    return prevent_empty_str(v, field.name)

  @validator('image', pre=True, always=True)
  def validate_strings(cls, v, field):
    return empty_str_to_none(v, field.name)
"""
