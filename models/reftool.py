from pydantic import BaseModel, ConfigDict, Field

from models.matches import MatchListBase
from models.assignments import AssignmentReferee


class RefToolReferee(AssignmentReferee):
    assignmentId: str | None = None
    status: str | None = None
    position: int | None = None


class RefereeOptions(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str = Field(..., alias="_id")
    assigned: list[RefToolReferee]
    requested: list[RefToolReferee]
    available: list[RefToolReferee]
    unavailable: list[RefToolReferee]


class RefSummary(BaseModel):
    assignedCount: int = 0
    requestedCount: int = 0
    availableCount: int = 0
    unavailableCount: int = 0
    requestsByLevel: dict[str, int] = Field(default_factory=dict)


class SummaryCounts(BaseModel):
    totalMatches: int = 0
    fullyAssigned: int = 0
    partiallyAssigned: int = 0
    unassigned: int = 0


class DayStripResponse(BaseModel):
    date: str
    counts: SummaryCounts


class TournamentSummary(BaseModel):
    tournamentAlias: str
    counts: SummaryCounts


class MatchWithRefSummary(MatchListBase):
    refSummary: RefSummary | None = None


class DayGroupResponse(BaseModel):
    date: str
    matches: list[MatchWithRefSummary]
    tournamentSummary: list[TournamentSummary]
