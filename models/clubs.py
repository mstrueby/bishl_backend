from bson import ObjectId
from datetime import date
from pydantic import Field, BaseModel, HttpUrl, EmailStr, validator
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


# sub documents
class TeamBase(MongoBaseModel):
  name: str = Field(...)
  alias: str = Field(...)
  fullName: str = Field(...)
  shortName: str = None
  tinyName: str = None
  ageGroup: str = Field(...)
  teamNumber: int = Field(...)
  active: bool = False
  external: bool = False
  ishdId: str = None
  legacyId: int = None

class TeamDB(TeamBase):
  pass

class TeamUpdate(MongoBaseModel):
  name: Optional[str] = None
  alias: Optional[str] = None
  fullName: Optional[str] = None
  shortName: Optional[str] = None
  tinyName: Optional[str] = None
  ageGroup: Optional[str] = None
  teamNumber: Optional[int] = None
  active: Optional[bool] = None
  external: Optional[bool] = None
  ishdId: Optional[str] = None
  legacyId: Optional[int] = None

class ClubBase(MongoBaseModel):
  name: str = Field(...)
  alias: str = Field(...)
  addressName: str = None
  street: str = None
  zipCode: str = None
  city: str = None
  country: str = Field(...)
  email: EmailStr = None
  yearOfFoundation: int = None
  description: str = None
  website: HttpUrl = None
  ishdId: int = None
  active: bool = False
  teams: List[TeamBase] = None
  legacyId: int = None
  logo: HttpUrl = None

  @validator('email',
             'website',
             'yearOfFoundation',
             'ishdId',
             'logo',
             pre=True,
             always=True)
  def empty_str_to_none(cls, v):
    return None if v == "" else v


class ClubDB(ClubBase):
  pass


class ClubUpdate(MongoBaseModel):
  name: Optional[str] = None
  alias: Optional[str] = None
  addressName: Optional[str] = None
  street: Optional[str] = None
  zipCode: Optional[str] = None
  city: Optional[str] = None
  country: Optional[str] = None
  email: Optional[EmailStr] = None
  yearOfFoundation: Optional[int] = None
  description: Optional[str] = None
  website: Optional[HttpUrl] = None
  ishdId: Optional[int] = None
  active: Optional[bool] = False
  teams: Optional[List[TeamBase]] = None
  legacyId: Optional[int] = None
  logo: Optional[str] = None

  
  @validator('email', 'website', 'yearOfFoundation', 'ishdId', 'logo', pre=True, always=True)
  def empty_str_to_none(cls, v):
      return None if v == "" else v