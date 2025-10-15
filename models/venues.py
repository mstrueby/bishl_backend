
from bson import ObjectId
from pydantic import Field, BaseModel, HttpUrl, ConfigDict
from pydantic_core import core_schema
from typing import Optional
from datetime import datetime


class PyObjectId(ObjectId):

  @classmethod
  def __get_pydantic_core_schema__(cls, source_type, handler):
    return core_schema.no_info_plain_validator_function(
      cls.validate,
      serialization=core_schema.plain_serializer_function_ser_schema(
        lambda x: str(x)
      )
    )

  @classmethod
  def validate(cls, v):
    if isinstance(v, ObjectId):
      return v
    if not ObjectId.is_valid(v):
      raise ValueError("Invalid objectid")
    return ObjectId(v)


class MongoBaseModel(BaseModel):
  model_config = ConfigDict(
    populate_by_name=True,
    arbitrary_types_allowed=True
  )
  
  id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")


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
  @field_validator('imageUrl', 'description', mode='before')
  @classmethod
  def empty_str_to_none(cls, v):
    return None if v == "" else v
  """

  """
  @field_validator('name',
             'alias',
             'shortName',
             'street',
             'zipCode',
             'city',
             'country',
             'latitude',
             'longitude',
             mode='before')
  @classmethod
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
  @field_validator('imageUrl', 'description', mode='before')
  @classmethod
  def empty_str_to_none(cls, v):
    return None if v == "" else v

  @field_validator('name',
             'alias',
             'shortName',
             'street',
             'zipCode',
             'city',
             'country',
             'latitude',
             'longitude',
             mode='before')
  @classmethod
  def prevent_null_value(cls, v):
    if v is None or v == "":
      raise ValueError("Field cannot be null or empty string")
    return v
  """
