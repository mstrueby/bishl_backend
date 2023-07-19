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
