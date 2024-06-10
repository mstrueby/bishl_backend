from bson import ObjectId
from datetime import datetime, date
from pydantic import Field, BaseModel, HttpUrl, validator
from typing import Optional, List


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


class ConfigDocBase(MongoBaseModel):
  key: str = Field(..., description="The key of the age group")
  value: str = Field(..., description="The value of the age group")
  sortOrder: int = Field(..., description="The sort order of the age group")


# -------------------


class ConfigBase(MongoBaseModel):
  name: str = Field(..., description="The name of the config")
  value: ConfigDocBase = {}


class ConfigDB(ConfigBase):
  pass


class ConfigUpdate(MongoBaseModel):
  name: Optional[str] = "DEFAULT"
  value: Optional[ConfigDocBase] = {}
