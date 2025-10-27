from datetime import datetime

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator
from pydantic_core import core_schema

from models.assignments import Referee
from utils import prevent_empty_str, validate_dict_of_strings, validate_match_time


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


# --- sub documents without _id


class KeyValue(BaseModel):
    key: str = Field(...)
    value: str = Field(...)


class MatchTournament(BaseModel):
    name: str = Field(...)
    alias: str = Field(...)


class MatchSeason(BaseModel):
    name: str = Field(...)
    alias: str = Field(...)


class MatchRound(BaseModel):
    name: str = Field(...)
    alias: str = Field(...)


class MatchMatchday(BaseModel):
    name: str = Field(...)
    alias: str = Field(...)


class EventPlayer(BaseModel):
    playerId: str = Field(...)
    firstName: str = Field(...)
    lastName: str = Field(...)
    jerseyNumber: int = 0
    displayFirstName: str | None = None
    displayLastName: str | None = None
    imageUrl: HttpUrl | None = None
    imageVisible: bool | None = False


class RosterPlayer(BaseModel):
    player: EventPlayer = Field(...)
    playerPosition: dict[str, str] = Field(...)
    passNumber: str = Field(...)
    goals: int = 0
    assists: int = 0
    points: int = 0
    penaltyMinutes: int = 0
    called: bool = False


class ScoresBase(MongoBaseModel):
    matchTime: str = Field(...)
    goalPlayer: EventPlayer = Field(...)
    assistPlayer: EventPlayer | None = None
    isPPG: bool = False
    isSHG: bool = False
    isGWG: bool = False

    @field_validator("matchTime", mode="before")
    @classmethod
    def validate_match_time_field(cls, v, info):
        return validate_match_time(v, info.field_name)


class ScoresDB(ScoresBase):
    pass


class ScoresUpdate(MongoBaseModel):
    matchTime: str | None = "00:00"
    goalPlayer: EventPlayer | None = None
    assistPlayer: EventPlayer | None = None
    isPPG: bool | None = False
    isSHG: bool | None = False
    isGWG: bool | None = False


class PenaltiesBase(MongoBaseModel):
    matchTimeStart: str = Field(...)
    matchTimeEnd: str | None = None
    penaltyPlayer: EventPlayer = Field(...)
    penaltyCode: dict[str, str] = Field(...)
    penaltyMinutes: int = Field(...)
    isGM: bool = False
    isMP: bool = False

    @field_validator("penaltyCode", mode="before")
    @classmethod
    def validate_type(cls, v, info):
        return validate_dict_of_strings(v, info.field_name)


class PenaltiesDB(PenaltiesBase):
    pass


class PenaltiesUpdate(MongoBaseModel):
    matchTimeStart: str | None = "00:00"
    matchTimeEnd: str | None = None
    penaltyPlayer: EventPlayer | None = None
    penaltyCode: dict[str, str] | None = None
    penaltyMinutes: int | None = 0
    isGM: bool | None = False
    isMP: bool | None = False

    @field_validator("penaltyCode", mode="before")
    @classmethod
    def validate_type(cls, v, info):
        if v is None:
            return v
        return validate_dict_of_strings(v, info.field_name)

    @field_validator("matchTimeStart", "matchTimeEnd", mode="before")
    @classmethod
    def validate_match_time_field(cls, v, info):
        if info.field_name == "matchTimeEnd" and v is None:
            return None
        return validate_match_time(v, info.field_name)


class MatchStats(BaseModel):
    gamePlayed: int = 0
    goalsFor: int = 0
    goalsAgainst: int = 0
    points: int = 0
    win: int = 0
    loss: int = 0
    draw: int = 0
    otWin: int = 0
    otLoss: int = 0
    soWin: int = 0
    soLoss: int = 0


class MatchStatsUpdate(BaseModel):
    gamePlayed: int | None = 0
    goalsFor: int | None = 0
    goalsAgainst: int | None = 0
    points: int | None = 0
    win: int | None = 0
    loss: int | None = 0
    draw: int | None = 0
    otWin: int | None = 0
    otLoss: int | None = 0
    soWin: int | None = 0
    soLoss: int | None = 0


class Coach(BaseModel):
    firstName: str | None = None
    lastName: str | None = None
    licence: str | None = None


class Staff(BaseModel):
    firstName: str = Field(...)
    lastName: str = Field(...)
    role: str | None = None


class MatchTeam(BaseModel):
    clubId: str | None = None
    clubName: str | None = None
    clubAlias: str | None = None
    teamId: str | None = None
    teamAlias: str = Field(...)
    name: str = Field(...)
    fullName: str = Field(...)
    shortName: str = Field(...)
    tinyName: str = Field(...)
    logo: HttpUrl | None = None
    roster: list[RosterPlayer] | None = Field(default_factory=list)
    rosterPublished: bool | None = False
    coach: Coach = Field(default_factory=Coach)
    staff: list[Staff] | None = Field(default_factory=list)
    scores: list[ScoresBase] | None = Field(default_factory=list)
    penalties: list[PenaltiesBase] | None = Field(default_factory=list)
    stats: MatchStats | None = Field(default_factory=MatchStats)

    @field_validator("teamAlias", "name", "fullName", "shortName", "tinyName", mode="before")
    @classmethod
    def validate_null_strings(cls, v, info):
        return prevent_empty_str(v, info.field_name)


class MatchTeamUpdate(BaseModel):
    clubId: str | None = None
    clubName: str | None = None
    clubAlias: str | None = None
    teamId: str | None = None
    teamAlias: str | None = "DEFAULT"
    name: str | None = "DEFAULT"
    fullName: str | None = "DEFAULT"
    shortName: str | None = "DEFAULT"
    tinyName: str | None = "DEFAULT"
    logo: HttpUrl | None = None
    roster: list[RosterPlayer] | None = Field(default_factory=list)
    rosterPublished: bool | None = None
    coach: Coach | None = Field(default_factory=Coach)
    staff: list[Staff] | None = Field(default_factory=list)
    scores: list[ScoresBase] | None = Field(default_factory=list)
    penalties: list[PenaltiesBase] | None = Field(default_factory=list)
    stats: MatchStats | None = None

    @field_validator("teamAlias", "name", "fullName", "shortName", "tinyName", mode="before")
    @classmethod
    def validate_null_strings(cls, v, info):
        return prevent_empty_str(v, info.field_name)


class MatchVenue(BaseModel):
    venueId: str | None = None
    name: str = Field(...)
    alias: str = Field(...)


class RefereePaymentDetails(BaseModel):
    travelExpenses: float | None = 0.0
    expenseAllowance: float | None = 0.0
    gameFees: float | None = 0.0


class RefereePayment(BaseModel):
    referee1: RefereePaymentDetails | None = Field(default_factory=RefereePaymentDetails)
    referee2: RefereePaymentDetails | None = Field(default_factory=RefereePaymentDetails)


class Official(BaseModel):
    firstName: str | None = None
    lastName: str | None = None
    licence: str | None = None


class SupplementarySheet(BaseModel):
    refereeAttendance: str | None = None  # yes, only 1, no referee, substitute referee
    referee1Present: bool | None = False
    referee2Present: bool | None = False
    referee1PassAvailable: bool | None = False
    referee2PassAvailable: bool | None = False
    referee1PassNo: str | None = None
    referee2PassNo: str | None = None
    referee1DelayMin: int | None = 0
    referee2DelayMin: int | None = 0
    timekeeper1: Official | None = None
    timekeeper2: Official | None = None
    technicalDirector: Official | None = None
    usageApproval: bool | None = False
    ruleBook: bool | None = False
    goalDisplay: bool | None = False
    soundSource: bool | None = False
    matchClock: bool | None = False
    matchBalls: bool | None = False
    firstAidKit: bool | None = False
    fieldLines: bool | None = False
    nets: bool | None = False
    homeRoster: bool | None = False
    homePlayerPasses: bool | None = False
    homeUniformPlayerClothing: bool | None = False
    awayRoster: bool | None = False
    awayPlayerPasses: bool | None = False
    awayUniformPlayerClothing: bool | None = False
    awaySecondJerseySet: bool | None = False
    refereePayment: RefereePayment | None = Field(default_factory=RefereePayment)
    specialEvents: bool | None = False
    refereeComments: str | None = None
    crowd: int | None = 0
    isSaved: bool | None = False


# --- main document


class MatchBase(MongoBaseModel):
    matchId: int = 0
    tournament: MatchTournament | None = None
    season: MatchSeason = Field(...)
    round: MatchRound | None = None
    matchday: MatchMatchday | None = None
    home: MatchTeam | None = None
    away: MatchTeam | None = None
    referee1: Referee | None = None
    referee2: Referee | None = None
    matchStatus: KeyValue = Field(
        default_factory=lambda: KeyValue(key="SCHEDULED", value="angesetzt")
    )
    finishType: KeyValue = Field(default_factory=lambda: KeyValue(key="REGULAR", value="Regulär"))
    venue: MatchVenue | None = None
    startDate: datetime | None = None
    published: bool = False
    matchSheetComplete: bool = False
    supplementarySheet: SupplementarySheet | None = Field(default_factory=SupplementarySheet)


class MatchDB(MatchBase):
    pass


class MatchListTeam(BaseModel):
    clubId: str | None = None
    clubName: str | None = None
    clubAlias: str | None = None
    teamId: str | None = None
    teamAlias: str = Field(...)
    name: str = Field(...)
    fullName: str = Field(...)
    shortName: str = Field(...)
    tinyName: str = Field(...)
    logo: HttpUrl | None = None
    rosterPublished: bool | None = False
    stats: MatchStats | None = Field(default_factory=MatchStats)

    @field_validator("teamAlias", "name", "fullName", "shortName", "tinyName", mode="before")
    @classmethod
    def validate_null_strings(cls, v, info):
        return prevent_empty_str(v, info.field_name)


class MatchListBase(MongoBaseModel):
    matchId: int = 0
    tournament: MatchTournament | None = None
    season: MatchSeason | None = None
    round: MatchRound | None = None
    matchday: MatchMatchday | None = None
    home: MatchListTeam | None = None
    away: MatchListTeam | None = None
    referee1: Referee | None = None
    referee2: Referee | None = None
    matchStatus: KeyValue = Field(
        default_factory=lambda: KeyValue(key="SCHEDULED", value="angesetzt")
    )
    finishType: KeyValue = Field(default_factory=lambda: KeyValue(key="REGULAR", value="Regulär"))
    venue: MatchVenue | None = None
    startDate: datetime | None = None
    published: bool = False
    matchSheetComplete: bool = False


class MatchUpdate(MongoBaseModel):
    matchId: int | None = None
    tournament: MatchTournament | None = None
    season: MatchSeason | None = None
    round: MatchRound | None = None
    matchday: MatchMatchday | None = None
    home: MatchTeamUpdate | None = None
    away: MatchTeamUpdate | None = None
    referee1: Referee | None = None
    referee2: Referee | None = None
    matchStatus: KeyValue | None = None
    finishType: KeyValue | None = None
    venue: MatchVenue | None = None
    startDate: datetime | None = None
    published: bool | None = False
    matchSheetComplete: bool | None = False
    supplementarySheet: SupplementarySheet | None = Field(default_factory=SupplementarySheet)
