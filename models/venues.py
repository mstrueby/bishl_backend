from datetime import datetime

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from pydantic_core import core_schema


class PyObjectId(ObjectId):

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):

        def validate_object_id(value: str) -> ObjectId:
            if isinstance(value, ObjectId):
                return value
            if not ObjectId.is_valid(value):
                raise ValueError("Invalid ObjectId")
            return ObjectId(value)

        return core_schema.with_info_plain_validator_function(
            validate_object_id,
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda x: str(x), return_schema=core_schema.str_schema()
            ),
        )

    @classmethod
    def __get_pydantic_json_schema__(cls, schema, handler):
        return {"type": "string", "format": "objectid"}


class MongoBaseModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True, arbitrary_types_allowed=True, json_encoders={ObjectId: str}
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
    imageUrl: HttpUrl | None = None
    description: str | None = None
    active: bool = False
    usageApprovalId: str | None = None
    usageApprovalValidTo: datetime | None = None
    legacyId: int | None = None

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
    name: str | None = "DEFAULT"
    alias: str | None = "DEFAULT"
    shortName: str | None = "DEFAULT"
    street: str | None = "DEFAULT"
    zipCode: str | None = "DEFAULT"
    city: str | None = "DEFAULT"
    country: str | None = "DEFAULT"
    latitude: str | None = "DEFAULT"
    longitude: str | None = "DEFAULT"
    imageUrl: HttpUrl | None = None
    description: str | None = None
    active: bool | None = False
    usageApprovalId: str | None = None
    usageApprovalValidTo: datetime | None = None

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
