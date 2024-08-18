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

# Posts
# ------------

class PostBase(MongoBaseModel):
  title: str = Field(...)
  alias: str = Field(...)
  content: str = Field(...)
  author: str = Field(...)
  tags: list = None
  image: HttpUrl = None
  create_date: datetime = Field(default_factory=datetime.utcnow)
  update_date: datetime = None
  published: bool = False
  legacyId: int = None

  @validator('title', 'alias', 'content', 'author', pre=True, always=True)
  def validate_null_strings(cls, v, field):
    return prevent_empty_str(v, field.name)

  @validator('image', pre=True, always=True)
  def validate_strings(cls, v, field):
    return empty_str_to_none(v, field.name)

class PostDB(PostBase):
  pass

class PostUpdate(MongoBaseModel):
  title: Optional[str] = "DEFAULT"
  alias: Optional[str] = "DEFAULT"
  content: Optional[str] = "DEFAULT"
  author: Optional[str] = "DEFAULT"
  tags: Optional[list] = "DEFAULT"
  image: Optional[HttpUrl] = None
  create_date: Optional[datetime] = None
  update_date: Optional[datetime] = None
  published: Optional[bool] = False

  @validator('title', 'alias', 'content', 'author', pre=True, always=True)
  def validate_null_strings(cls, v, field):
    return prevent_empty_str(v, field.name)

  @validator('image', pre=True, always=True)
  def validate_strings(cls, v, field):
    return empty_str_to_none(v, field.name)
  