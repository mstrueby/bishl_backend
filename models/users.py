from enum import Enum

from bson import ObjectId
from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from pydantic_core import core_schema


class PyObjectId(ObjectId):

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):

        def validate_object_id(value, _info):
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
    model_config = ConfigDict(
        populate_by_name=True, arbitrary_types_allowed=True, json_encoders={ObjectId: str}
    )

    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")


class Role(str, Enum):
    admin = "ADMIN"
    ref_admin = "REF_ADMIN"
    author = "AUTHOR"
    publisher = "PUBLISHER"
    referee = "REFEREE"
    doc_admin = "DOC_ADMIN"
    club_admin = "CLUB_ADMIN"
    league_admin = "LEAGUE_ADMIN"
    player_admin = "PLAYER_ADMIN"


class RefereeLevel(str, Enum):
    NA = "n/a"
    SM = "SM"  # Schiri Mentor
    S3 = "S3"  # Schiedsrichter gut
    S2 = "S2"  # Schiedsrichter mittel
    S1 = "S1"  # Schiedsrichter unerfahren
    PM = "PM"  # Perspektiv Mentor (ehemaliger Schiedsrichter)
    P3 = "P3"  # Perspektiv-Schiedsrichter gut
    P2 = "P2"  # Perspektiv-Schiedsrichter mittel
    P1 = "P1"  # Perspektiv-Schiedsrichter unerfahren


class Club(BaseModel):
    clubId: str = Field(...)
    clubName: str = Field(...)
    logoUrl: str | None = None


class Referee(BaseModel):
    level: RefereeLevel = Field(default=RefereeLevel.NA)
    passNo: str | None = None
    ishdLevel: int | None = None
    active: bool = True
    club: Club | None = None
    points: int | None = 0


class UserBase(MongoBaseModel):
    email: EmailStr = Field(...)
    password: str = Field(...)
    firstName: str = Field(...)
    lastName: str = Field(...)
    club: Club | None = None
    roles: list[Role] | None = Field(default_factory=list)
    referee: Referee | None = None

    @field_validator("email")
    @classmethod
    def email_is_valid(cls, v):
        try:
            validate_email(v)
        except EmailNotValidError as e:
            raise ValueError(e) from e
        return v


class UserUpdate(MongoBaseModel):
    email: str | None = None
    password: str | None = None
    firstName: str | None = None
    lastName: str | None = None
    club: Club | None = None
    roles: list[Role] | None = Field(default_factory=list)
    referee: Referee | None = None
    """
  @validator('email')
  def email_is_valid(cls, v):
    try:
      validate_email(v)
    except EmailNotValidError as e:
      raise ValueError(e)
    return v

  """


class LoginBase(BaseModel):
    email: EmailStr = Field(...)
    password: str = Field(...)


class CurrentUser(MongoBaseModel):
    email: EmailStr = Field(...)
    firstName: str = Field(...)
    lastName: str = Field(...)
    club: Club | None = None
    roles: list[Role] | None = Field(default_factory=list)
    referee: Referee | None = None
