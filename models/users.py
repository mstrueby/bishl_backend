from enum import Enum
from typing import Optional, List, Any
from pydantic import EmailStr, Field, BaseModel, ConfigDict, field_validator
from pydantic_core import core_schema
from email_validator import validate_email, EmailNotValidError
from bson import ObjectId


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
  logoUrl: Optional[str] = None


class Referee(BaseModel):
  level: RefereeLevel = Field(default=RefereeLevel.NA)
  passNo: Optional[str] = None
  ishdLevel: Optional[int] = None
  active: bool = True
  club: Optional[Club] = None
  points: Optional[int] = 0


class UserBase(MongoBaseModel):
  email: EmailStr
  password: str = Field(...)
  firstName: str = Field(...)
  lastName: str = Field(...)
  club: Optional[Club] = None
  roles: Optional[List[Role]] = Field(default_factory=list)
  referee: Optional[Referee] = None

  @field_validator('email')
  @classmethod
  def email_is_valid(cls, v):
    try:
      validate_email(v)
    except EmailNotValidError as e:
      raise ValueError(e)
    return v


class UserUpdate(MongoBaseModel):
  email: Optional[str] = None
  password: Optional[str] = None
  firstName: Optional[str] = None
  lastName: Optional[str] = None
  club: Optional[Club] = None
  roles: Optional[List[Role]] = Field(default_factory=list)
  referee: Optional[Referee] = None
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
  email: EmailStr
  password: str = Field(...)


class CurrentUser(MongoBaseModel):
  email: EmailStr
  firstName: str = Field(...)
  lastName: str = Field(...)
  club: Optional[Club] = None
  roles: Optional[List[Role]] = Field(default_factory=list)
  referee: Optional[Referee] = None