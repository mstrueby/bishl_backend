from bson import ObjectId
from pydantic import Field, BaseModel, validator
from typing import Optional
from utils import prevent_empty_str
from datetime import datetime


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
  userId: str = Field(...)
  firstName: str = Field(...)
  lastName: str = Field(...)

  @validator('userId', 'firstName', 'lastName', pre=True, always=True)
  def validate_null_strings(cls, v, field):
    return prevent_empty_str(v, field.name)


# Messages
class MessageBase(MongoBaseModel):
  receiverId: str = Field(...)
  content: str = Field(...)
  timestamp: datetime = Field(default_factory=lambda: datetime.now())
  read: bool = False


class MessageDB(MongoBaseModel):
  sender: User = Field(...)
  receiver: User = Field(...)
  content: str = Field(...)
  timestamp: datetime = Field(...)
  read: bool = False


class MessageUpdate(MongoBaseModel):
  #senderId: Optional[str] = "DEFAULT"
  #receiverId: Optional[str] = "DEFAULT"
  #content: Optional[str] = "DEFAULT"
  read: Optional[bool] = True