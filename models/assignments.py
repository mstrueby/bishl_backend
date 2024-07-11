from bson import ObjectId
from pydantic import BaseModel, Field, validator
from typing import Optional
from enum import Enum
from utils import prevent_empty_str


class PyObjectId(ObjectId):

  @classmethod
  def __get_validators__(cls):
    yield cls.validate

  @classmethod
  def validate(cls, v):
    if not ObjectId.is_valid(v):
      raise ValueError("Invalid ObjectId")
    return ObjectId(v)

  @classmethod
  def __modify_schema__(cls, field_schema):
    field_schema.update(type="string")


class MongoBaseModel(BaseModel):
  id: PyObjectId = Field(default_factory=ObjectId, alias="_id")

  class Config:
    json_encoders = {ObjectId: str}


class Status(str, Enum):
  requested = "REQUESTED"
  unavailable = "UNAVAILABLE"
  assigned = "ASSIGNED"
  accepted = "ACCEPTED"


class Referee(BaseModel):
  user_id: str = Field(...)
  firstname: str = Field(...)
  lastname: str = Field(...)
  club_id: str = None
  club_name: str = None


class AssignmentBase(MongoBaseModel):
  status: Status = Field(...)
  user_id: str = None
  ref_admin: bool = False
  position: Optional[int] = Field(None,
                                  description='Possible values are 1 and 2',
                                  ge=1,
                                  le=2)


class AssignmentDB(MongoBaseModel):
  match_id: str = Field(...)
  status: Status = Field(...)
  referee: Referee = Field(...)
  position: Optional[int] = Field(None,
                                  description='Possible values are 1 and 2',
                                  ge=1,
                                  le=2)


class AssignmentUpdate(MongoBaseModel):
  status: Optional[Status] = "DEFAULT"
  ref_admin: Optional[bool] = False
  position: Optional[int] = Field(None,
                                  description='Possible values are 1 and 2',
                                  ge=1,
                                  le=2)

  @validator('status', pre=True, always=True)
  def validate_null_strings(cls, v, field):
    return prevent_empty_str(v, field.name)
