from datetime import datetime
from enum import Enum

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import core_schema

from models.users import RefereeLevel
from utils import prevent_empty_str


class PyObjectId(ObjectId):

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):

        def validate_object_id(value: str, _info) -> ObjectId:
            if isinstance(value, ObjectId):
                return value
            if not ObjectId.is_valid(value):
                raise ValueError("Invalid ObjectId")
            return ObjectId(value)

        return core_schema.with_info_plain_validator_function(
            validate_object_id,
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda x: str(x), return_schema=core_schema.str_schema()
            ),
        )

    @classmethod
    def __get_pydantic_json_schema__(cls, schema, handler):
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
    updatedBy: str | None = None
    updatedByName: str | None = None


class Referee(BaseModel):
    userId: str = Field(...)
    firstName: str = Field(...)
    lastName: str = Field(...)
    clubId: str | None = None
    clubName: str | None = None
    logoUrl: str | None = None
    points: int = 0
    level: RefereeLevel | None = RefereeLevel.NA


class AssignmentBase(MongoBaseModel):
    matchId: str = Field(...)
    status: Status = Field(...)
    userId: str | None = None
    refAdmin: bool = False


class AssignmentCreate(BaseModel):
    """Model for creating a new assignment"""
    matchId: str = Field(...)
    refereeId: str | None = Field(None, description="Referee user ID (required for ref admin)")
    status: Status = Field(...)
    position: int | None = Field(None, description="Possible values are 1 and 2", ge=1, le=2)
    refAdmin: bool = Field(default=False, description="Whether this is being created by a ref admin")


class AssignmentDB(MongoBaseModel):
    matchId: str = Field(...)
    status: Status = Field(...)
    referee: Referee = Field(...)
    position: int | None = Field(None, description="Possible values are 1 and 2", ge=1, le=2)
    statusHistory: list[StatusHistory] | None = Field(default_factory=list)


class AssignmentRead(AssignmentDB):
    """Model for reading assignment data (API responses)"""
    pass


class AssignmentStatusUpdate(BaseModel):
    """Model for updating assignment status"""
    status: Status = Field(..., description="New status for the assignment")

    position: int | None = Field(None, description="Possible values are 1 and 2", ge=1, le=2)


class AssignmentUpdate(MongoBaseModel):
    status: Status | None = None
    refAdmin: bool | None = False
    position: int | None = Field(None, description="Possible values are 1 and 2", ge=1, le=2)

    @field_validator("status", mode="before")
    @classmethod
    def validate_null_strings(cls, v, info):
        return prevent_empty_str(v, info.field_name)
