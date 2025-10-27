
from bson import ObjectId
from pydantic import Field, BaseModel, field_validator, HttpUrl, ConfigDict
from pydantic_core import core_schema
from typing import Optional
from datetime import datetime
from utils import prevent_empty_str


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
  @field_validator('title', 'alias', 'content', mode='before')
  @classmethod
  def validate_null_strings(cls, v, info):
    return prevent_empty_str(v, info.field_name)

  @field_validator('imageUrl', mode='before')
  @classmethod
  def validate_strings(cls, v, info):
    return empty_str_to_none(v, info.field_name)
  """
