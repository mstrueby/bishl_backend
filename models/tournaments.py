from datetime import datetime
from enum import Enum

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator
from pydantic_core import core_schema

from utils import empty_str_to_none, prevent_empty_str, validate_dict_of_strings


class PyObjectId(ObjectId):

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):

        def validate_object_id(value: str) -> ObjectId:
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


# sub documents


class Teams(BaseModel):
    fullName: str = Field(...)
    shortName: str = Field(...)
    tinyName: str = Field(...)
    logo: HttpUrl | None = None

    @field_validator("logo", mode="before")
    @classmethod
    def validate_logo(cls, v, info):
        return empty_str_to_none(v, info.field_name)


class Standings(BaseModel):
    fullName: str = Field(...)
    shortName: str = Field(...)
    tinyName: str = Field(...)
    logo: HttpUrl | None = None
    gamesPlayed: int = Field(...)
    goalsFor: int = Field(...)
    goalsAgainst: int = Field(...)
    points: int = Field(...)
    wins: int = Field(...)
    losses: int = Field(...)
    draws: int = Field(...)
    otWins: int = Field(...)
    otLosses: int = Field(...)
    soWins: int = Field(...)
    soLosses: int = Field(...)
    streak: list[str] | None = Field(default_factory=list)


# settings at tournament level
class StandingsSettings(BaseModel):
    pointsWinReg: int | None = Field(default=0)
    pointsLossReg: int | None = Field(default=0)
    pointsDrawReg: int | None = Field(default=0)
    pointsWinOvertime: int | None = Field(default=0)
    pointsLossOvertime: int | None = Field(default=0)
    pointsWinShootout: int | None = Field(default=0)
    pointsLossShootout: int | None = Field(default=0)


# settings on round and matchday level
class MatchSettings(BaseModel):
    numOfPeriods: int | None = Field(default=0)
    periodLengthMin: int | None = Field(default=0)
    overtime: bool | None = Field(default=False)
    numOfPeriodsOvertime: int | None = Field(default=0)
    periodLengthMinOvertime: int | None = Field(default=0)
    shootout: bool | None = Field(default=False)
    refereePoints: int | None = Field(default=0)


# ------------
class MatchdayType(Enum):
    # PLAYOFFS = {"key": "PLAYOFFS", "value": "Playoffs", "sortOrder": 1}
    # REGULAR = {"key": "REGULAR", "value": "Regulär", "sortOrder": 2}
    PLAYOFFS = {"key": "PLAYOFFS", "value": "Playoffs"}
    REGULAR = {"key": "REGULAR", "value": "Regulär"}


class MatchdayOwner(BaseModel):
    clubId: str | None = None
    clubName: str | None = None
    clubAlias: str | None = None


class MatchdayBase(MongoBaseModel):
    name: str = Field(...)
    alias: str = Field(...)
    type: dict[str, str] = Field(...)
    startDate: datetime | None = None
    endDate: datetime | None = None
    createStandings: bool = False
    createStats: bool = False
    matchSettings: MatchSettings | None = Field(default_factory=dict)
    published: bool = False
    standings: dict[str, Standings] | None = Field(default_factory=dict)
    owner: MatchdayOwner | None = Field(default_factory=dict)

    @field_validator("startDate", "endDate", mode="before")
    @classmethod
    def validate_strings(cls, v, info):
        return empty_str_to_none(v, info.field_name)

    @field_validator("name", "alias", mode="before")
    @classmethod
    def validate_null_strings(cls, v, info):
        return prevent_empty_str(v, info.field_name)


class MatchdayDB(MatchdayBase):
    pass


class MatchdayUpdate(MongoBaseModel):
    name: str | None = "DEFAULT"
    alias: str | None = "DEFAULT"
    type: dict[str, str] | None = Field(default_factory=dict)
    startDate: datetime | None = None
    endDate: datetime | None = None
    createStandings: bool | None = False
    createStats: bool | None = False
    matchSettings: MatchSettings | None = Field(default_factory=dict)
    published: bool | None = False
    standings: dict[str, Standings] | None = Field(default_factory=dict)
    owner: MatchdayOwner | None = Field(default_factory=dict)

    @field_validator("startDate", "endDate", mode="before")
    @classmethod
    def validate_strings(cls, v, info):
        return empty_str_to_none(v, info.field_name)

    @field_validator("name", "alias", mode="before")
    @classmethod
    def validate_null_strings(cls, v, info):
        return prevent_empty_str(v, info.field_name)


class RoundBase(MongoBaseModel):
    name: str = Field(...)
    alias: str = Field(...)
    sortOrder: int = Field(0)
    createStandings: bool = False
    createStats: bool = False
    matchdaysType: dict[str, str] = Field(...)
    matchdaysSortedBy: dict[str, str] = Field(...)
    startDate: datetime | None = None
    endDate: datetime | None = None
    matchSettings: MatchSettings | None = Field(default_factory=dict)
    published: bool = False
    matchdays: list[MatchdayBase] | None = Field(default_factory=list)
    standings: dict[str, Standings] | None = Field(default_factory=dict)

    @field_validator("startDate", "endDate", mode="before")
    @classmethod
    def validate_strings(cls, v, info):
        return empty_str_to_none(v, info.field_name)

    @field_validator("name", "alias", mode="before")
    @classmethod
    def validate_null_strings(cls, v, info):
        return prevent_empty_str(v, info.field_name)

    @field_validator("matchdaysType", "matchdaysSortedBy", mode="before")
    @classmethod
    def validate_type(cls, v, info):
        return validate_dict_of_strings(v, info.field_name)


class RoundDB(RoundBase):
    pass


class RoundUpdate(MongoBaseModel):
    name: str | None = "DEFAULT"
    alias: str | None = "DEFAULT"
    sortOrder: int | None = None
    createStandings: bool | None = False
    createStats: bool | None = False
    matchdaysType: dict[str, str] | None = Field(default_factory=dict)
    matchdaysSortedBy: dict[str, str] | None = Field(default_factory=dict)
    startDate: datetime | None = None
    endDate: datetime | None = None
    matchSettings: MatchSettings | None = Field(default_factory=dict)
    published: bool | None = False
    matchdays: list[MatchdayBase] | None = Field(default_factory=list)
    standings: dict[str, Standings] | None = Field(default_factory=dict)

    @field_validator("startDate", "endDate", mode="before")
    @classmethod
    def validate_strings(cls, v, info):
        return empty_str_to_none(v, info.field_name)

    @field_validator("name", "alias", mode="before")
    @classmethod
    def validate_null_strings(cls, v, info):
        return prevent_empty_str(v, info.field_name)

    @field_validator("matchdaysSortedBy", "matchdaysType", mode="before")
    @classmethod
    def validate_type(cls, v, info):
        return validate_dict_of_strings(v, info.field_name)


class SeasonBase(MongoBaseModel):
    name: str = Field(...)
    alias: str = Field(...)
    standingsSettings: StandingsSettings | None = Field(default_factory=dict)
    published: bool = False
    rounds: list[RoundBase] | None = Field(default_factory=list)

    @field_validator("name", "alias", mode="before")
    @classmethod
    def validate_null_strings(cls, v, info):
        return prevent_empty_str(v, info.field_name)


class SeasonDB(SeasonBase):
    pass


class SeasonUpdate(MongoBaseModel):
    name: str | None = "DEFAULT"
    alias: str | None = "DEFAULT"
    standingsSettings: StandingsSettings | None = Field(default_factory=dict)
    published: bool | None = False
    rounds: list[RoundBase] | None = Field(default_factory=list)

    @field_validator("name", "alias", mode="before")
    @classmethod
    def validate_null_strings(cls, v, info):
        return prevent_empty_str(v, info.field_name)


# --------


class TournamentBase(MongoBaseModel):
    name: str = Field(...)
    alias: str = Field(...)
    tinyName: str = Field(...)
    ageGroup: dict[str, str] = Field(...)
    published: bool = False
    active: bool = False
    external: bool = False
    website: HttpUrl | None = None
    seasons: list[SeasonBase] | None = Field(default_factory=list)
    legacyId: int | None = None

    @field_validator("website", mode="before")
    @classmethod
    def validate_string(cls, v, info):
        return empty_str_to_none(v, info.field_name)

    @field_validator("name", "alias", "tinyName", mode="before")
    @classmethod
    def validate_null_strings(cls, v, info):
        return prevent_empty_str(v, info.field_name)

    @field_validator("ageGroup", mode="before")
    @classmethod
    def validate_type(cls, v, info):
        return validate_dict_of_strings(v, info.field_name)


class TournamentDB(TournamentBase):
    pass


class TournamentUpdate(MongoBaseModel):
    name: str | None = "DEFAULT"
    alias: str | None = "DEFAULT"
    tinyName: str | None = "DEFAULT"
    ageGroup: dict[str, str] | None = Field(default_factory=dict)
    published: bool | None = False
    active: bool | None = False
    external: bool | None = False
    website: HttpUrl | None = None
    seasons: list[SeasonBase] | None = Field(default_factory=list)

    @field_validator("website", mode="before")
    @classmethod
    def validate_string(cls, v, info):
        return empty_str_to_none(v, info.field_name)

    @field_validator("name", "alias", "tinyName", mode="before")
    @classmethod
    def validate_null_strings(cls, v, info):
        return prevent_empty_str(v, info.field_name)

    @field_validator("ageGroup", mode="before")
    @classmethod
    def validate_type(cls, v, info):
        return validate_dict_of_strings(v, info.field_name)
