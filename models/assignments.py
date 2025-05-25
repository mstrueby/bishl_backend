from bson import ObjectId
from pydantic import BaseModel, Field, validator
from typing import Optional
from enum import Enum
from utils import prevent_empty_str
from models.users import RefereeLevel

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


class Status(str, Enum):
  requested = "REQUESTED"
  unavailable = "UNAVAILABLE"
  assigned = "ASSIGNED"
  accepted = "ACCEPTED"


class Referee(BaseModel):
  userId: str = Field(...)
  firstName: str = Field(...)
  lastName: str = Field(...)
  clubId: Optional[str] = None
  clubName: Optional[str] = None
  logoUrl: Optional[str] = None
  points: int = 0
  level: Optional[RefereeLevel] = RefereeLevel.NA


class AssignmentBase(MongoBaseModel):
  matchId: str = Field(...)
  status: Status = Field(...)
  userId: Optional[str] = None
  refAdmin: bool = False
  position: Optional[int] = Field(None,
                                  description='Possible values are 1 and 2',
                                  ge=1,
                                  le=2)


class AssignmentDB(MongoBaseModel):
  matchId: str = Field(...)
  status: Status = Field(...)
  referee: Referee = Field(...)
  position: Optional[int] = Field(None,
                                  description='Possible values are 1 and 2',
                                  ge=1,
                                  le=2)


class AssignmentUpdate(MongoBaseModel):
  status: Optional[Status] = None
  refAdmin: Optional[bool] = False
  position: Optional[int] = Field(None,
                                  description='Possible values are 1 and 2',
                                  ge=1,
                                  le=2)

  @validator('status', pre=True, always=True)
  def validate_null_strings(cls, v, field):
    return prevent_empty_str(v, field.name)
