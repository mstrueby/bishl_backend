from bson import ObjectId
from pydantic import Field, BaseModel, validator, HttpUrl
from typing import Optional
from datetime import datetime
from utils import prevent_empty_str, empty_str_to_none

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
  firstname: str = Field(...)
  lastname: str = Field(...)

  @validator('firstname', 'lastname', pre=True, always=True)
  def validate_null_strings(cls, v, field):
    return prevent_empty_str(v, field.name)
  
class User(BaseModel):
  user_id: str = Field(...)
  firstname: str = Field(...)
  lastname: str = Field(...)

  @validator('user_id', 'firstname', 'lastname', pre=True, always=True)
  def validate_null_strings(cls, v, field):
    return prevent_empty_str(v, field.name)

# Posts
# ------------

class PostBase(MongoBaseModel):
  title: str = Field(...)
  alias: str = Field(...)
  content: str = Field(...)
  author: Author = None
  tags: list = None
  image: HttpUrl = None
  published: bool = False
  legacyId: int = None

  @validator('title', 'alias', 'content', pre=True, always=True)
  def validate_null_strings(cls, v, field):
    return prevent_empty_str(v, field.name)

  @validator('image', pre=True, always=True)
  def validate_strings(cls, v, field):
    return empty_str_to_none(v, field.name)

class PostDB(MongoBaseModel):
  title: str = Field(...)
  alias: str = Field(...)
  content: str = Field(...)
  author: Author = None
  tags: list = None
  image: HttpUrl = None
  create_date: datetime = None
  create_user: User = Field(...)
  update_date: datetime = None
  update_user: User = None
  published: bool = False
  legacyId: int = None

class PostUpdate(MongoBaseModel):
  title: str = "DEFAULT"
  alias: str = "DEFAULT"
  content: str = "DEFAULT"
  author: Optional[Author] = None
  tags: Optional[list] = []
  image: Optional[HttpUrl] = None
  published: Optional[bool] = False

  @validator('title', 'alias', 'content', pre=True, always=True)
  def validate_null_strings(cls, v, field):
    return prevent_empty_str(v, field.name)

  @validator('image', pre=True, always=True)
  def validate_strings(cls, v, field):
    return empty_str_to_none(v, field.name)
  