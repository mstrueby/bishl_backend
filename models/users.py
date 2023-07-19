from enum import Enum
from typing import Optional
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
  admin = "admin"
  user = "user"
  guest = "guest"

class UserBase(MongoBaseModel):
  #username: str = Field(..., min_length=3, max_length=20)
  email: str = EmailStr(...)
  password: str = Field(...)
  firstname: str = Field(...)
  lastname: str = Field(...)
  role: Role

  @validator('email')
  def email_is_valid(cls, v):
    try:
      validate_email(v)
    except EmailNotValidError as e:
      raise ValueError(e)
    return v

class LoginBase(BaseModel):
  # username: str = Field(...)
  email: str = EmailStr(...)
  password: str = Field(...)

class CurrentUser(MongoBaseModel):
  email: str = EmailStr(...)
  #username: str = Field(...)
  firstname: str = Field(...)
  lastname: str = Field(...)
  role: str = Field(...)
