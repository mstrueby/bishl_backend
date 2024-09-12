from bson import ObjectId
#from datetime import date
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
  shortName: str = Field(...)
  tinyName: str = Field(...)
  ageGroup: str = Field(...)
  teamNumber: int = Field(...)
  active: bool = False
  external: bool = False
  ishdId: str = None
  legacyId: int = None

  @validator('ishdId', pre=True, always=True)
  def empty_str_to_none(cls, v):
    return None if v == "" else v

  @validator('name',
             'alias',
             'fullName',
             'shortName',
             'tinyName',
             'ageGroup',
             pre=True,
             always=True)
  def prevent_null_value(cls, v):
    if v is None or v == "":
      raise ValueError("Field cannot be null or empty string")
    return v


@validator('teamNumber', pre=True, always=True)
def int_must_be_positive(cls, v):
  if v < 1 or v is None:
    raise ValueError("Field must be positive")


class TeamDB(TeamBase):
  pass


class TeamUpdate(MongoBaseModel):
  name: Optional[str] = "DEFAULT"
  alias: Optional[str] = "DEFAULT"
  fullName: Optional[str] = "DEFAULT"
  shortName: Optional[str] = "DEFAULT"
  tinyName: Optional[str] = "DEFAULT"
  ageGroup: Optional[str] = "DEFAULT"
  teamNumber: Optional[int] = 1
  active: Optional[bool] = False
  external: Optional[bool] = False
  ishdId: Optional[str] = None
  legacyId: Optional[int] = None

  @validator('ishdId', pre=True, always=True)
  def empty_str_to_none(cls, v):
    return None if v == "" else v

  @validator('name',
             'alias',
             'fullName',
             'shortName',
             'tinyName',
             'ageGroup',
             pre=True,
             always=True)
  def prevent_null_value(cls, v):
    if v is None or v == "":
      raise ValueError("Field cannot be null or empty string")
    return v

  @validator('teamNumber', pre=True, always=True)
  def int_must_be_positive(cls, v):
    if v < 1 or v is None:
      raise ValueError("Field must be positive")


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

  """
  @validator('name', 'alias', 'country', pre=True, always=True)
  def prevent_null_value(cls, v):
    if v is None or v == "":
      raise ValueError("Field cannot be null or empty string")
    return v
  """


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
  active: Optional[bool] = None
  teams: Optional[List[TeamBase]] = None
  legacyId: Optional[int] = None
  logo: Optional[str] = None

  @validator('email', 'website', 'logo', pre=True, always=True)
  def empty_str_to_none(cls, v):
    return None if v == "" else v

  """
  @validator('name', 'alias', 'country', pre=True, always=True)
  def prevent_null_value(cls, v):
    if v is None or v == "":
      raise ValueError("Field cannot be null or empty string")
    return v
"""
