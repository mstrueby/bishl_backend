
from bson import ObjectId
from pydantic import Field, BaseModel, field_validator, ConfigDict
from pydantic_core import core_schema
from typing import Optional
from utils import prevent_empty_str
from datetime import datetime


class PyObjectId(ObjectId):

  @classmethod
  def __get_pydantic_core_schema__(cls, source_type, handler):
    return core_schema.no_info_plain_validator_function(
      cls.validate,
      serialization=core_schema.plain_serializer_function_ser_schema(
        lambda x: str(x)
      )
    )

  @classmethod
  def validate(cls, v):
    if isinstance(v, ObjectId):
      return v
    if not ObjectId.is_valid(v):
      raise ValueError("Invalid objectid")
    return ObjectId(v)


class MongoBaseModel(BaseModel):
  model_config = ConfigDict(
    populate_by_name=True,
    arbitrary_types_allowed=True,
    json_encoders={ObjectId: str}
  )
  
  id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")


class User(BaseModel):
  userId: str = Field(...)
  firstName: str = Field(...)
  lastName: str = Field(...)

  @field_validator('userId', 'firstName', 'lastName', mode='before')
  @classmethod
  def validate_null_strings(cls, v, info):
    return prevent_empty_str(v, info.field_name)


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
