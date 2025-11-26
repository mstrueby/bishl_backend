from bson import ObjectId
from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, field_validator
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


# Clubs
# ------------


class TeamPartnerships(BaseModel):
    clubId: str = Field(...)
    clubAlias: str = Field(...)
    clubName: str = Field(...)
    teamId: str = Field(...)
    teamAlias: str = Field(...)
    teamName: str = Field(...)


# sub documents
class TeamBase(MongoBaseModel):
    name: str = Field(...)
    alias: str = Field(...)
    fullName: str = Field(...)
    shortName: str = Field(...)
    tinyName: str = Field(...)
    ageGroup: str = Field(...)
    teamNumber: int = Field(...)
    teamPartnership: list[TeamPartnerships] = Field(default_factory=list)
    active: bool | None = False
    external: bool | None = False
    logoUrl: HttpUrl | None = None
    ishdId: str | None = None
    legacyId: int | None = None

    @field_validator("ishdId", mode="before")
    def empty_str_to_none(cls, v):
        return None if v == "" else v


"""
  @validator('name',
             'alias',
             'fullName',
             'shortName',
             'tinyName',
             'ageGroup',
             pre=True,
             always=True)
  def prevent_null_value(cls, v):
    if v is None or v == "":
      raise ValueError("Field cannot be null or empty string")
    return v
"""


@field_validator("teamNumber", mode="before")
def int_must_be_positive(cls, v):
    if v < 1 or v is None:
        raise ValueError("Field must be positive")
    return v


class TeamDB(TeamBase):
    pass


class TeamUpdate(MongoBaseModel):
    name: str | None = None
    alias: str | None = None
    fullName: str | None = None
    shortName: str | None = None
    tinyName: str | None = None
    ageGroup: str | None = None
    teamNumber: int | None = None
    teamPartnership: list[TeamPartnerships] | None = None
    active: bool | None = False
    external: bool | None = False
    logoUrl: HttpUrl | None = None
    ishdId: str | None = None
    legacyId: int | None = None

    @field_validator("ishdId", mode="before")
    def empty_str_to_none(cls, v):
        return None if v == "" else v

    """

  @validator('name',
             'alias',
             'fullName',
             'shortName',
             'tinyName',
             'ageGroup',
             pre=True,
             always=True)
  def prevent_null_value(cls, v):
    if v is None or v == "":
      raise ValueError("Field cannot be null or empty string")
    return v

  @validator('teamNumber', pre=True, always=True)
  def int_must_be_positive(cls, v):
    if v < 1 or v is None:
      raise ValueError("Field must be positive")

  """


class ClubBase(MongoBaseModel):
    name: str = Field(...)
    alias: str = Field(...)
    addressName: str | None = None
    street: str | None = None
    zipCode: str | None = None
    city: str | None = None
    country: str = Field(...)
    email: EmailStr | None = None
    yearOfFoundation: int | None = None
    description: str | None = None
    website: HttpUrl | None = None
    ishdId: int | None = None
    active: bool | None = False
    teams: list[TeamBase] | None = Field(default_factory=list)
    legacyId: int | None = None
    logoUrl: HttpUrl | None = None

    @field_validator(
        "addressName",
        "street",
        "zipCode",
        "city",
        "description",
        "email",
        "website",
        "yearOfFoundation",
        "ishdId",
        "logoUrl",
        "legacyId",
        mode="before",
    )
    @classmethod
    def empty_str_to_none(cls, v):
        return None if v == "" else v

    """
  @validator('name', 'alias', 'country', pre=True, always=True)
  def prevent_null_value(cls, v):
    if v is None or v == "":
      raise ValueError("Field cannot be null or empty string")
    return v
  """


class ClubDB(ClubBase):
    pass


class ClubUpdate(MongoBaseModel):
    name: str | None = None
    alias: str | None = None
    addressName: str | None = None
    street: str | None = None
    zipCode: str | None = None
    city: str | None = None
    country: str | None = None
    email: EmailStr | None = None
    yearOfFoundation: int | None = None
    description: str | None = None
    website: HttpUrl | None = None
    ishdId: int | None = None
    active: bool | None = None
    legacyId: int | None = None
    logoUrl: str | None = None

    @field_validator(
        "addressName",
        "street",
        "zipCode",
        "city",
        "description",
        "email",
        "website",
        "logoUrl",
        "yearOfFoundation",
        "ishdId",
        "legacyId",
        mode="before",
    )
    @classmethod
    def empty_str_to_none(cls, v):
        return None if v == "" else v

    """
  @validator('name', 'alias', 'country', pre=True, always=True)
  def prevent_null_value(cls, v):
    if v is None or v == "":
      raise ValueError("Field cannot be null or empty string")
    return v
"""
