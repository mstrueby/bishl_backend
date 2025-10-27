from bson import ObjectId
from pydantic import Field, BaseModel, HttpUrl, ConfigDict
from pydantic_core import core_schema
from typing import Optional
from datetime import datetime


class PyObjectId(ObjectId):

  @classmethod
  def __get_pydantic_core_schema__(cls, source_type, handler):
    from pydantic_core import core_schema
    
    def validate_object_id(value: str) -> ObjectId:
      if isinstance(value, ObjectId):
        return value
      if not ObjectId.is_valid(value):
        raise ValueError("Invalid ObjectId")
      return ObjectId(value)
    
    return core_schema.with_info_plain_validator_function(
      validate_object_id,
      serialization=core_schema.plain_serializer_function_ser_schema(
        lambda x: str(x),
        return_schema=core_schema.str_schema()
      )
    )

  @classmethod
  def __get_pydantic_json_schema__(cls, schema, handler):
    return {'type': 'string', 'format': 'objectid'}


class MongoBaseModel(BaseModel):
  model_config = ConfigDict(
    populate_by_name=True,
    arbitrary_types_allowed=True,
    json_encoders={ObjectId: str}
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