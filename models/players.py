from datetime import datetime
from enum import Enum

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from pydantic_core import core_schema

from models.matches import MatchMatchday, MatchRound, MatchSeason, MatchTournament


class PlayUpOccurrence(BaseModel):
    matchId: str = Field(..., description="ID of the match where play-up occurred")
    matchStartDate: datetime = Field(..., description="Start date of the match")
    counted: bool = Field(default=True, description="Whether this occurrence counts towards play-up limits")


class PlayUpTracking(BaseModel):
    tournamentAlias: str = Field(..., description="Tournament where play-up occurred")
    seasonAlias: str = Field(..., description="Season where play-up occurred")
    fromTeamId: str = Field(..., description="ID of the player's regular team")
    toTeamId: str = Field(..., description="ID of the team player played up to")
    occurrences: list[PlayUpOccurrence] = Field(default_factory=list, description="List of play-up occurrences")


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
    model_config = ConfigDict(
        populate_by_name=True, arbitrary_types_allowed=True, json_encoders={ObjectId: str}
    )

    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")


class PositionEnum(str, Enum):
    SKATER = "Skater"
    GOALIE = "Goalie"


class SourceEnum(str, Enum):
    ISHD = "ISHD"
    BISHL = "BISHL"
    CALLED = "CALLED"


class SexEnum(str, Enum):
    MALE = "männlich"
    FEMALE = "weiblich"


class SuspensionStatusEnum(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    SUSPENDED = "SUSPENDED"


class Suspension(BaseModel):
    startDate: datetime = Field(...)
    endDate: datetime = Field(...)
    reason: str = Field(...)
    teamIds: list[str] | None = Field(default_factory=list)


class LicenseTypeEnum(str, Enum):
    PRIMARY = "PRIMARY"      # Stammverein/-team
    SECONDARY = "SECONDARY"  # A-Pass, Zweitspielrecht im Sinne WKO
    LOAN = "LOAN"            # Leihgabe
    DEVELOPMENT = "DEVELOPMENT"  # Förderlizenz etc.


class AssignedTeams(BaseModel):
    teamId: str = Field(...)
    teamName: str = Field(...)
    teamAlias: str = Field(...)
    teamAgeGroup: str = Field(...)
    teamIshdId: str | None = None
    passNo: str = Field(...)
    source: SourceEnum = Field(default=SourceEnum.BISHL)
    licenseType: LicenseTypeEnum = Field(default=LicenseTypeEnum.PRIMARY)
    modifyDate: datetime | None = None
    active: bool = False
    jerseyNo: int | None = None


class AssignedClubs(BaseModel):
    clubId: str = Field(...)
    clubName: str = Field(...)
    clubAlias: str = Field(...)
    clubIshdId: int | None = None
    teams: list[AssignedTeams] = Field(...)


class TeamInput(BaseModel):
    teamId: str = Field(...)
    passNo: str = Field(...)
    jerseyNo: int | None = None
    active: bool | None = False
    source: SourceEnum | None = Field(default=SourceEnum.BISHL)
    modifyDate: datetime | None = None


class AssignedTeamsInput(BaseModel):
    clubId: str = Field(...)
    teams: list[TeamInput] = Field(...)


class PlayerStatsTeam(BaseModel):
    # team_id: str = Field(...)
    name: str = Field(...)
    fullName: str = Field(...)
    shortName: str = Field(...)
    tinyName: str = Field(...)


class PlayerStats(BaseModel):
    tournament: MatchTournament = Field(...)
    season: MatchSeason = Field(...)
    round: MatchRound = Field(...)
    matchday: MatchMatchday | None = None
    team: PlayerStatsTeam = Field(...)
    gamesPlayed: int = Field(0)
    goals: int = Field(0)
    assists: int = Field(0)
    points: int = Field(0)
    penaltyMinutes: int = Field(0)
    calledMatches: int = Field(0)


class PlayerBase(MongoBaseModel):
    firstName: str = Field(...)
    lastName: str = Field(...)
    birthdate: datetime = Field(..., description="format: yyyy-mm-dd hh:mi:ss")
    displayFirstName: str = Field(...)
    displayLastName: str = Field(...)
    nationality: str | None = None
    position: PositionEnum = Field(default=PositionEnum.SKATER)
    fullFaceReq: bool = False
    source: SourceEnum = Field(default=SourceEnum.BISHL)
    sex: SexEnum = Field(default=SexEnum.MALE)
    assignedTeams: list[AssignedClubs] | None = Field(default_factory=list)
    playUpTrackings: list[PlayUpTracking] | None = Field(default_factory=list, description="Track play-up occurrences separately from licenses")
    suspensions: list[Suspension] | None = Field(default_factory=list)
    stats: list[PlayerStats] | None = Field(default_factory=list)
    imageUrl: HttpUrl | None = None
    imageVisible: bool = False
    legacyId: int | None = None
    managedByISHD: bool = True
    """
  @validator('firstName', 'lastName', 'position', pre=True, always=True)
  def validate_null_strings(cls, v, field):
    return prevent_empty_str(v, field.name)

  @validator('image', pre=True, always=True)
  def validate_strings(cls, v, field):
    return empty_str_to_none(v, field.name)
"""


class PlayerDB(PlayerBase):
    """Player model for database operations"""

    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True, by_alias=True)

    @property
    def ageGroup(self) -> str:
        """Determine age group dynamically based on birth year"""
        if self.birthdate is None:
            return "UNKNOWN"

        current_year = datetime.now().year
        birth_year = self.birthdate.year

        # Determine age group classification using birth year and current year
        if birth_year >= current_year - 7:  # for year 2025: 2018 and above
            return "U8"
        elif birth_year >= current_year - 9:  # for year 2025: from 2016 to 2017
            return "U10"
        elif birth_year >= current_year - 12:  # for year 2025: from 2013 to 2015
            return "U13"
        elif birth_year >= current_year - 15:  # for year 2025: from 2010 to 2012
            return "U16"
        elif birth_year >= current_year - 18:  # for year 2025: from 2007 to 2009
            return "U19"
        else:
            return "HERREN" if self.sex == SexEnum.MALE else "DAMEN"

    @property
    def overAge(self) -> bool:
        """Evaluate compliance with Bambini over age rule"""
        if not self.birthdate:
            return False

        current_year = datetime.now().year

        if self.ageGroup == "U13":
            if self.sex == SexEnum.FEMALE and self.birthdate.year == current_year - 10:
                return True
            elif (
                self.sex == SexEnum.MALE
                and self.birthdate > datetime(current_year - 10, 8, 31)
                and self.birthdate < datetime(current_year - 9, 1, 1)
            ):
                return True
            else:
                return False
        elif self.ageGroup == "U16":
            if self.sex == SexEnum.FEMALE and self.birthdate.year == current_year - 13:
                return True
            else:
                return False
        elif self.ageGroup == "U19":
            if self.sex == SexEnum.FEMALE and self.birthdate.year == current_year - 16:
                return True
            else:
                return False
        elif self.ageGroup == "DAMEN":
            if self.sex == SexEnum.FEMALE and self.birthdate.year == current_year - 19:
                return True
            else:
                return False
        else:
            return False

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str},
        json_schema_extra={
            "properties": {"ageGroup": {"type": "string"}, "overAge": {"type": "boolean"}}
        },
    )

    def model_dump(self, *args, **kwargs):
        """Incorporate properties when converting to dictionary"""
        result = super().model_dump(*args, **kwargs)
        result["ageGroup"] = self.ageGroup
        result["overAge"] = self.overAge
        return result


class PlayerUpdate(MongoBaseModel):
    firstName: str | None = None
    lastName: str | None = None
    birthdate: datetime | None = None
    displayFirstName: str | None = None
    displayLastName: str | None = None
    nationality: str | None = None
    position: PositionEnum | None = None
    fullFaceReq: bool | None = None
    source: SourceEnum | None = None
    sex: SexEnum | None = None
    assignedTeams: list[AssignedClubs] | None = None
    playUpTrackings: list[PlayUpTracking] | None = None
    stats: list[PlayerStats] | None = None
    imageUrl: HttpUrl | None = None
    imageVisible: bool | None = None
    managedByISHD: bool | None = None
    """
  @validator('firstName', 'lastName', pre=True, always=True)
  def validate_null_strings(cls, v, field):
    return prevent_empty_str(v, field.name)

  @validator('image', pre=True, always=True)
  def validate_strings(cls, v, field):
    return empty_str_to_none(v, field.name)
"""


# ---- ISHD Log Model


class IshdActionEnum(str, Enum):
    ADD_PLAYER = "Add new Player"
    ADD_CLUB = "Add club/team assignment"
    ADD_TEAM = "Add team assigment"
    DEL_TEAM = "Remove team assigment"
    DEL_CLUB = "Remove club assignment"


class IshdLogPlayer(BaseModel):
    action: IshdActionEnum | None = None
    firstName: str = Field(...)
    lastName: str = Field(...)
    birthdate: datetime = Field(...)


class IshdLogTeam(BaseModel):
    teamIshdId: str = Field(...)
    url: str = Field(...)
    players: list[IshdLogPlayer] = Field(default_factory=list)


class IshdLogClub(BaseModel):
    clubName: str = Field(...)
    ishdId: int = Field(...)
    teams: list[IshdLogTeam] = Field(default_factory=list)


class IshdLogBase(MongoBaseModel):
    processDate: datetime = Field(...)
    clubs: list[IshdLogClub] = Field(default_factory=list)
