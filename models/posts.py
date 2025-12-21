from bson import ObjectId
from pydantic import Field, BaseModel, ConfigDict, field_validator, HttpUrl
from pydantic_core import core_schema
from typing import Optional, Any
from datetime import datetime
from utils import prevent_empty_str


class PyObjectId(ObjectId):

  @classmethod
  def __get_pydantic_core_schema__(cls, source_type: Any, handler: Any) -> core_schema.CoreSchema:
    return core_schema.no_info_plain_validator_function(
      cls.validate,
      serialization=core_schema.plain_serializer_function_ser_schema(
        lambda x: str(x), return_schema=core_schema.str_schema()
      ),
    )

  @classmethod
  def validate(cls, v: Any) -> ObjectId:
    if isinstance(v, ObjectId):
      return v
    if not ObjectId.is_valid(v):
      raise ValueError("Invalid ObjectId")
    return ObjectId(v)

  @classmethod
  def __get_pydantic_json_schema__(cls, schema: Any, handler: Any) -> dict:
    return {"type": "string", "format": "objectid"}


class MongoBaseModel(BaseModel):
  model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)
  
  id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")


class Author(BaseModel):
  firstName: str = Field(...)
  lastName: str = Field(...)

  @field_validator('firstName', 'lastName', mode='before')
  @classmethod
  def validate_null_strings(cls, v, info):
    return prevent_empty_str(v, info.field_name)


class User(BaseModel):
  userId: str = Field(...)
  firstName: str = Field(...)
  lastName: str = Field(...)

  @field_validator('userId', 'firstName', 'lastName', mode='before')
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
  author: Optional[Author] = None
  tags: Optional[list] = Field(default_factory=list)
  imageUrl: Optional[HttpUrl] = None
  published: bool = False
  featured: bool = False
  deleted: bool = False
  publishDateFrom: Optional[datetime] = None
  publishDateTo: Optional[datetime] = None
  legacyId: Optional[int] = None


"""
  @validator('title', 'alias', 'content', pre=True, always=True)
  def validate_null_strings(cls, v, field):
    return prevent_empty_str(v, field.name)

  @validator('imageUrl', pre=True, always=True)
  def validate_strings(cls, v, field):
    return empty_str_to_none(v, field.name)
"""


class PostDB(PostBase):
  createDate: Optional[datetime] = None
  createUser: User = Field(...)
  updateDate: Optional[datetime] = None
  updateUser: Optional[User] = None
  revisions: list[Revision] = Field(default_factory=list)


class PostUpdate(MongoBaseModel):
  title: Optional[str] = None
  alias: Optional[str] = None
  content: Optional[str] = None
  author: Optional[Author] = None
  tags: Optional[list] = Field(default_factory=list)
  imageUrl: Optional[HttpUrl] = None
  published: Optional[bool] = None
  featured: Optional[bool] = None
  deleted: Optional[bool] = None
  publishDateFrom: Optional[datetime] = None
  publishDateTo: Optional[datetime] = None
  """
  @validator('title', 'alias', 'content', pre=True, always=True)
  def validate_null_strings(cls, v, field):
    return prevent_empty_str(v, field.name)

  @validator('imageUrl', pre=True, always=True)
  def validate_strings(cls, v, field):
    return empty_str_to_none(v, field.name)
  """
