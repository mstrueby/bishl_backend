from datetime import datetime

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator
from pydantic_core import core_schema

from utils import prevent_empty_str


class PyObjectId(ObjectId):

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):

        def validate_object_id(value: str, _info) -> ObjectId:
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


class Author(BaseModel):
    firstName: str = Field(...)
    lastName: str = Field(...)

    @field_validator("firstName", "lastName", mode="before")
    @classmethod
    def validate_null_strings(cls, v, info):
        return prevent_empty_str(v, info.field_name)


class User(BaseModel):
    userId: str = Field(...)
    firstName: str = Field(...)
    lastName: str = Field(...)

    @field_validator("userId", "firstName", "lastName", mode="before")
    @classmethod
    def validate_null_strings(cls, v, info):
        return prevent_empty_str(v, info.field_name)


class Revision(MongoBaseModel):
    updateData: dict = Field(...)
    updateUser: User = Field(...)
    updateDate: datetime = Field(...)


# Posts
# ------------


class PostBase(MongoBaseModel):
    title: str = Field(...)
    alias: str = Field(...)
    content: str = Field(...)
    author: Author | None = None
    tags: list | None = Field(default_factory=list)
    imageUrl: HttpUrl | None = None
    published: bool = False
    featured: bool = False
    deleted: bool = False
    publishDateFrom: datetime | None = None
    publishDateTo: datetime | None = None
    legacyId: int | None = None


"""
  @field_validator('title', 'alias', 'content', mode='before')
  @classmethod
  def validate_null_strings(cls, v, info):
    return prevent_empty_str(v, info.field_name)

  @field_validator('imageUrl', mode='before')
  @classmethod
  def validate_strings(cls, v, info):
    return empty_str_to_none(v, info.field_name)
"""


class PostDB(PostBase):
    createDate: datetime | None = None
    createUser: User = Field(...)
    updateDate: datetime | None = None
    updateUser: User | None = None
    revisions: list[Revision] = Field(default_factory=list)


class PostUpdate(MongoBaseModel):
    title: str | None = None
    alias: str | None = None
    content: str | None = None
    author: Author | None = None
    tags: list | None = Field(default_factory=list)
    imageUrl: HttpUrl | None = None
    published: bool | None = None
    featured: bool | None = None
    deleted: bool | None = None
    publishDateFrom: datetime | None = None
    publishDateTo: datetime | None = None
    """
  @field_validator('title', 'alias', 'content', mode='before')
  @classmethod
  def validate_null_strings(cls, v, info):
    return prevent_empty_str(v, info.field_name)

  @field_validator('imageUrl', mode='before')
  @classmethod
  def validate_strings(cls, v, info):
    return empty_str_to_none(v, info.field_name)
  """
