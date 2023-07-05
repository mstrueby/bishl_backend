from bson import ObjectId
from datetime import date
from pydantic import Field, BaseModel, HttpUrl, EmailStr
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


# Clubs
# ------------


class ClubBase(MongoBaseModel):
  name: str = Field(...)
  addressName: str = None
  street: str = None
  zipCode: str = None
  city: str = None
  country: str = Field(...)
  email: EmailStr = None
  dateOfFoundation: date = None
  description: str = None
  website: HttpUrl = None
  ishdId: int = None
  active: bool = False
  legacyId: int = None


class ClubDB(ClubBase):
  pass


class ClubUpdate(MongoBaseModel):
  name: Optional[str] = None
  addressName: Optional[str] = None
  street: Optional[str] = None
  zipCode: Optional[str] = None
  city: Optional[str] = None
  country: Optional[str] = None
  email: Optional[EmailStr] = None
  dateOfFoundation: Optional[date] = None
  description: Optional[str] = None
  website: Optional[HttpUrl] = None
  ishdId: Optional[int] = None
  active: Optional[bool] = False
  legacyId: Optional[int] = None


# Teams
# --------


class TeamBase(MongoBaseModel):
  name: str = Field(...)
  shortName: str = Field(...)
  tinyName: str = Field(...)
  teamNumber: int = Field(...)
  ageGroup: str = Field(...)
  clubName: str = None
  contact_name: str = None
  phone_num: str = None
  email: str = None
  description: str = None
  extern: bool = False
  ishdId: str = None
  active: bool = False
  legacyId: int = None


class TeamDB(TeamBase):
  pass


class TeamUpdate(MongoBaseModel):
  name: Optional[str] = None
  shortName: Optional[str] = None
  tinyName: Optional[str] = None
  teamNumber: Optional[int] = None
  ageGroup: Optional[str] = None
  clubName: Optional[str] = None
  contact_name: Optional[str] = None
  phone_num: Optional[str] = None
  email: Optional[str] = None
  description: Optional[str] = None
  extern: Optional[bool] = False
  ishdId: Optional[str] = None
  active: Optional[bool] = False
  legacyId: Optional[int] = None


# Venues
# ------------


class VenueBase(MongoBaseModel):
  name: str = Field(...)
  shortName: str = Field(...)
  street: str = Field(...)
  zipCode: str = Field(...)
  city: str = Field(...)
  country: str = Field(...)
  latitude: float = Field(...)
  longitude: float = Field(...)
  image: str = None
  description: str = None
  active: bool = False
  legacyId: int = None


class VenueDB(VenueBase):
  pass


class VenueUpdate(MongoBaseModel):
  name: Optional[str] = None
  shortName: Optional[str] = None
  street: Optional[str] = None
  zipCode: Optional[str] = None
  city: Optional[str] = None
  country: Optional[str] = None
  latitude: Optional[float] = None
  longitude: Optional[float] = None
  image: Optional[str] = None
  description: Optional[str] = None
  active: Optional[bool] = None


# Tournaments
# ------------

# sub documents
class Standings(BaseModel):
  team: str = Field(...)
  games_played: int = Field(...)
  goals_for: int = Field(...)
  goals_against: int = Field(...)
  points: int = Field(...)

class Matches(BaseModel):
  match_id: str = Field(...)
  home_team: str = Field(...)
  away_team: str = Field(...)
  status: str = Field(...)
  venue: str = None
  home_score: int = None
  away_score: int = None
  start_time: date = None
  
class Matchday(BaseModel):
  matchday_name: str = Field(...)
  matchday_type: str = Field(...)
  start_date: date = None
  end_date: date = None
  matches: List[Matches] = None
  standings: List[Standings] = None

class Tournaments(BaseModel):
  name: str = Field(...)
  create_table: bool = Field(...)
  published: bool = Field(...)
  matchdays: List[Matchday] = None
  matches: List[Matches] = None
  standings: List[Standings] = None
  
# --------

class SeasonBase(MongoBaseModel):
  name: str = Field(...)
  year: int = Field(...)
  alias: str = Field(...)
  age_group: str = Field(...)
  published: bool = False
  active: bool = False
  tournaments: List[Tournaments] = None

class SeasonDB(SeasonBase):
  pass

class SeasonUpdate(MongoBaseModel):
  name: Optional[str] = None
  year: Optional[int] = None
  alias: Optional[str] = None
  age_group: Optional[str] = None
  published: Optional[bool] = None
  active: Optional[bool] = None
  tournaments: Optional[List[Tournaments]] = None
  