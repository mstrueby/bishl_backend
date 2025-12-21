from bson import ObjectId
from pydantic import BaseModel, Field, ConfigDict, field_validator
from pydantic_core import core_schema
from typing import Optional, List, Any
from enum import Enum
from datetime import datetime
from utils import prevent_empty_str
from models.users import RefereeLevel


class PyObjectId(ObjectId):

  @classmethod
  def __get_pydantic_core_schema__(cls, source_type: Any, handler: Any) -> core_schema.CoreSchema:
    return core_schema.no_info_plain_validator_function(
      cls.validate,
      serialization=core_schema.plain_serializer_function_ser_schema(
        lambda x: str(x), return_schema=core_schema.str_schema()
      ),
    )

  @classmethod
  def validate(cls, v: Any) -> ObjectId:
    if isinstance(v, ObjectId):
      return v
    if not ObjectId.is_valid(v):
      raise ValueError("Invalid ObjectId")
    return ObjectId(v)

  @classmethod
  def __get_pydantic_json_schema__(cls, schema: Any, handler: Any) -> dict:
    return {"type": "string", "format": "objectid"}


class MongoBaseModel(BaseModel):
  model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)
  
  id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")


class Status(str, Enum):
  requested = "REQUESTED"
  unavailable = "UNAVAILABLE"
  assigned = "ASSIGNED"
  accepted = "ACCEPTED"


class StatusHistory(BaseModel):
  status: Status = Field(...)
  updateDate: datetime = Field(...)
  updatedBy: Optional[str] = None
  updatedByName: Optional[str] = None


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
  statusHistory: Optional[List[StatusHistory]] = Field(default_factory=list)


class AssignmentUpdate(MongoBaseModel):
  status: Optional[Status] = None
  refAdmin: Optional[bool] = False
  position: Optional[int] = Field(None,
                                  description='Possible values are 1 and 2',
                                  ge=1,
                                  le=2)

  @field_validator('status', mode='before')
  @classmethod
  def validate_null_strings(cls, v, info):
    return prevent_empty_str(v, info.field_name)
