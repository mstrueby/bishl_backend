from bson import ObjectId
from pydantic import Field, BaseModel, HttpUrl, EmailStr, validator, field_validator
from typing import Optional, List


class PyObjectId(ObjectId):

  @classmethod
  def __get_validators__(cls):
    yield cls.validate

  @classmethod
  def validate(cls, v, handler=None):
    if not ObjectId.is_valid(v):
      raise ValueError("Invalid objectid")
    return ObjectId(v)

  @classmethod
  def __get_pydantic_json_schema__(cls, core_schema, handler):
    return {"type": "string"}


class MongoBaseModel(BaseModel):
  id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")

  class Config:
    json_encoders = {ObjectId: str}


# Clubs
# ------------

class TeamPartnerships(BaseModel):
  clubId: str = Field(...)
  clubAlias: str = Field(...)
  clubName: str = Field(...)
  teamId: str = Field(...)
  teamAlias: str = Field(...)
  teamName: str = Field(...)


# sub documents
class TeamBase(MongoBaseModel):
  name: str = Field(...)
  alias: str = Field(...)
  fullName: str = Field(...)
  shortName: str = Field(...)
  tinyName: str = Field(...)
  ageGroup: str = Field(...)
  teamNumber: int = Field(...)
  teamPartnership: List[TeamPartnerships] = Field(default_factory=list)
  active: Optional[bool] = False
  external: Optional[bool] = False
  logoUrl: Optional[HttpUrl] = None
  ishdId: Optional[str] = None
  legacyId: Optional[int] = None

  @field_validator('ishdId', mode='before')
  @classmethod
  def empty_str_to_none(cls, v):
    return None if v == "" else v


"""
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
"""


@field_validator('teamNumber', mode='before')
def int_must_be_positive(cls, v):
  if v < 1 or v is None:
    raise ValueError("Field must be positive")


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
  teamPartnership: Optional[List[TeamPartnerships]] = None
  active: Optional[bool] = False
  external: Optional[bool] = False
  logoUrl: Optional[HttpUrl] = None
  ishdId: Optional[str] = None
  legacyId: Optional[int] = None

  @field_validator('ishdId', mode='before')
  @classmethod
  def empty_str_to_none(cls, v):
    return None if v == "" else v

  """  

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

  """

class ClubBase(MongoBaseModel):
  name: str = Field(...)
  alias: str = Field(...)
  addressName: Optional[str] = None
  street: Optional[str] = None
  zipCode: Optional[str] = None
  city: Optional[str] = None
  country: str = Field(...)
  email: Optional[EmailStr] = None
  yearOfFoundation: Optional[int] = None
  description: Optional[str] = None
  website: Optional[HttpUrl] = None
  ishdId: Optional[int] = None
  active: Optional[bool] = False
  teams: Optional[List[TeamBase]] = Field(default_factory=list)
  legacyId: Optional[int] = None
  logoUrl: Optional[HttpUrl] = None

  @field_validator('email',
             'website',
             'yearOfFoundation',
             'ishdId',
             'logoUrl',
             mode='before')
  @classmethod
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
  legacyId: Optional[int] = None
  logoUrl: Optional[str] = None

  @field_validator('email', 'website', 'logoUrl', mode='before')
  @classmethod
  def empty_str_to_none(cls, v):
    return None if v == "" else v

  """
  @validator('name', 'alias', 'country', pre=True, always=True)
  def prevent_null_value(cls, v):
    if v is None or v == "":
      raise ValueError("Field cannot be null or empty string")
    return v
"""