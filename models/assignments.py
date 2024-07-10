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
  position: Optional[int] = Field(None,
                                  description='Possible values are 1 and 2',
                                  ge=1,
                                  le=2)
  user_id: str = Field(...)
  firstname: str = Field(...)
  lastname: str = Field(...)
  club_id: str = None
  club_name: str = None


class AssignmentBase(MongoBaseModel):
  status: Status = Field(...)
  user_id: str = Field(...)
  position: Optional[int] = Field(None,
                                  description='Possible values are 1 and 2',
                                  ge=1,
                                  le=2)
  ref_admin: bool = False


class AssignmentDB(MongoBaseModel):
  match_id: str = Field(...)
  status: Status = Field(...)
  referee: Referee = Field(...)


class AssignmentUpdate(MongoBaseModel):
  #match_id: Optional[str] = "DEFAULT"
  #user_id: Optional[str] = "DEFAULT"
  #referee: Optional[Referee] = {}
  status: Optional[Status] = "DEFAULT"
  position: Optional[int] = Field(None,
                                  description='Possible values are 1 and 2',
                                  ge=1,
                                  le=2)
  ref_admin: Optional[bool] = False

  @validator('status', pre=True, always=True)
  def validate_null_strings(cls, v, field):
    return prevent_empty_str(v, field.name)
