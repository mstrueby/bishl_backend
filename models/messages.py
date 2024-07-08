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

# Messages
class MessageBase(MongoBaseModel):
  sender_id: str = Field(...)
  receiver_id: str = Field(...)
  content: str = Field(...)
  timestamp: datetime = Field(default_factory=datetime.utcnow)
  read: bool = False

class MessageDB(MessageBase):
  pass

class MessageUpdate(MongoBaseModel):
  sender_id: Optional[str] = "DEFAULT"
  receiver_id: Optional[str] = "DEFAULT"
  content: Optional[str] = "DEFAULT"
  read: Optional[bool] = True

  @validator('sender_id', 'receiver_id', pre=True, always=True)
  def validate_null_strings(cls, v, field):
    return prevent_empty_str(v, field.name)
  
      