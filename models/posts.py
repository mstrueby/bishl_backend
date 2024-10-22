from bson import ObjectId
from pydantic import Field, BaseModel, validator, HttpUrl
from typing import Optional
from datetime import datetime
from utils import prevent_empty_str


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


class Author(BaseModel):
  firstName: str = Field(...)
  lastName: str = Field(...)

  @validator('firstName', 'lastName', pre=True, always=True)
  def validate_null_strings(cls, v, field):
    return prevent_empty_str(v, field.name)


class User(BaseModel):
  userId: str = Field(...)
  firstName: str = Field(...)
  lastName: str = Field(...)

  @validator('userId', 'firstName', 'lastName', pre=True, always=True)
  def validate_null_strings(cls, v, field):
    return prevent_empty_str(v, field.name)


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
  image: Optional[HttpUrl] = None
  published: bool = False
  legacyId: Optional[int] = None


"""
  @validator('title', 'alias', 'content', pre=True, always=True)
  def validate_null_strings(cls, v, field):
    return prevent_empty_str(v, field.name)

  @validator('image', pre=True, always=True)
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
  image: Optional[HttpUrl] = None
  published: Optional[bool] = None
  """
  @validator('title', 'alias', 'content', pre=True, always=True)
  def validate_null_strings(cls, v, field):
    return prevent_empty_str(v, field.name)

  @validator('image', pre=True, always=True)
  def validate_strings(cls, v, field):
    return empty_str_to_none(v, field.name)
  """
