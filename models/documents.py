from bson import ObjectId
from pydantic import Field, BaseModel, field_validator, HttpUrl
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
  def __get_pydantic_json_schema__(cls, core_schema, handler):
    return {"type": "string"}


class MongoBaseModel(BaseModel):
  id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")

  class Config:
    json_encoders = {ObjectId: str}



class User(BaseModel):
  userId: str = Field(...)
  firstName: str = Field(...)
  lastName: str = Field(...)

  @field_validator('userId', 'firstName', 'lastName', mode='before')
  @classmethod
  def validate_null_strings(cls, v, info):
    return prevent_empty_str(v, info.field_name)


class DocumentBase(MongoBaseModel):
  title: str = Field(...)
  alias: str = Field(...)
  category: Optional[str] = None
  url: HttpUrl = Field(...)
  publicId: str = Field(...)
  fileName: str = Field(...)
  fileType: str = Field(...)
  fileSizeByte: int = Field(...)
  published: bool = False


class DocumentDB(DocumentBase):
  createDate: Optional[datetime] = None
  createUser: User = Field(...)
  updateDate: Optional[datetime] = None
  updateUser: Optional[User] = None


class DocumentUpdate(MongoBaseModel):
  title: Optional[str] = None
  alias: Optional[str] = None
  category: Optional[str] = None
  url: Optional[HttpUrl] = None
  publicId: Optional[str] = None
  filename: Optional[str] = None
  fileType: Optional[str] = None
  fileSizeByte: Optional[int] = None
  published: Optional[bool] = None