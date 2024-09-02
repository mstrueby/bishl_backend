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

class User(BaseModel):
  user_id: str = Field(...)
  firstname: str = Field(...)
  lastname: str = Field(...)

  @validator('user_id', 'firstname', 'lastname', pre=True, always=True)
  def validate_null_strings(cls, v, field):
    return prevent_empty_str(v, field.name)

class DocumentBase(MongoBaseModel):
  title: str = Field(...)
  alias: str = Field( ...)
  category: Optional[str] = None
  url: HttpUrl = Field(...)
  public_id: str = Field(...)
  filename: str = Field(...)
  file_type: str = Field(...)
  file_size_byte: int = Field(...)

class DocumentDB(DocumentBase):
  create_date: datetime = None
  create_user: User = Field(...)
  update_date: datetime = None
  update_user: User = None  

class DocumentUpdate(DocumentBase):
  title: Optional[str] = None
  alias: Optional[str] = None
  category: Optional[str] = None
  url: Optional[HttpUrl] = None
  public_id: Optional[str] = None
  filename: Optional[str] = None
  file_type: Optional[str] = None
  file_size_byte: Optional[int] = None