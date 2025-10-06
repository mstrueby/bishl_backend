from bson import ObjectId
from pydantic import Field, BaseModel, HttpUrl, validator
from typing import Optional
from datetime import datetime


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


# Venues
# ------------


class VenueBase(MongoBaseModel):
  name: str = Field(...)
  alias: str = Field(...)
  shortName: str = Field(...)
  street: str = Field(...)
  zipCode: str = Field(...)
  city: str = Field(...)
  country: str = Field(...)
  latitude: str = Field(...)
  longitude: str = Field(...)
  imageUrl: Optional[HttpUrl] = None
  description: Optional[str] = None
  active: bool = False
  usageApprovalId: Optional[str] = None
  usageApprovalValidTo: Optional[datetime] = None
  legacyId: Optional[int] = None

  """
  @validator('image', 'description', pre=True, always=True)
  def empty_str_to_none(cls, v):
    return None if v == "" else v
  """

  """
  @validator('name',
             'alias',
             'shortName',
             'street',
             'zipCode',
             'city',
             'country',
             'latitude',
             'longitude',
             pre=True,
             always=True)
  def prevent_null_value(cls, v):
    if v is None or v == "":
      raise ValueError("Field cannot be null or empty string")
    return v
  """


class VenueDB(VenueBase):
  pass


class VenueUpdate(MongoBaseModel):
  name: Optional[str] = "DEFAULT"
  alias: Optional[str] = "DEFAULT"
  shortName: Optional[str] = "DEFAULT"
  street: Optional[str] = "DEFAULT"
  zipCode: Optional[str] = "DEFAULT"
  city: Optional[str] = "DEFAULT"
  country: Optional[str] = "DEFAULT"
  latitude: Optional[str] = "DEFAULT"
  longitude: Optional[str] = "DEFAULT"
  imageUrl: Optional[HttpUrl] = None
  description: Optional[str] = None
  active: Optional[bool] = False
  usageApprovalId: Optional[str] = None
  usageApprovalValidTo: Optional[datetime] = None

  """
  @validator('image', 'description', pre=True, always=True)
  def empty_str_to_none(cls, v):
    return None if v == "" else v

  @validator('name',
             'alias',
             'shortName',
             'street',
             'zipCode',
             'city',
             'country',
             'latitude',
             'longitude',
             pre=True,
             always=True)
  def prevent_null_value(cls, v):
    if v is None or v == "":
      raise ValueError("Field cannot be null or empty string")
    return v
  """
