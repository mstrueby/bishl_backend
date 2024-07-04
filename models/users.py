from enum import Enum
from typing import Optional, List
from pydantic import EmailStr, Field, BaseModel, validator
from email_validator import validate_email, EmailNotValidError
from datetime import date
from bson import ObjectId


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

class Role(str, Enum):
  admin = "ADMIN"
  ref_admin = "REF_ADMIN"
  author = "AUTHOR"
  publisher = "PUBLISHER"
  referee = "REFEREE"
  doc_admin = "DOC_ADMIN"
  

class UserBase(MongoBaseModel):
  email: str = EmailStr(...)
  password: str = Field(...)
  firstname: str = Field(...)
  lastname: str = Field(...)
  roles: List[Role] = None

  @validator('email')
  def email_is_valid(cls, v):
    try:
      validate_email(v)
    except EmailNotValidError as e:
      raise ValueError(e)
    return v

class UserUpdate(MongoBaseModel):
  email: Optional[str] = None
  password: Optional[str] = None
  firstname: Optional[str] = None
  lastname: Optional[str] = None
  roles: Optional[List[Role]] = None

  @validator('email')
  def email_is_valid(cls, v):
    try:
      validate_email(v)
    except EmailNotValidError as e:
      raise ValueError(e)
    return v

class LoginBase(BaseModel):
  email: str = EmailStr(...)
  password: str = Field(...)

class CurrentUser(MongoBaseModel):
  email: str = EmailStr(...)
  firstname: str = Field(...)
  lastname: str = Field(...)
  roles: List[Role] = Field(...)
