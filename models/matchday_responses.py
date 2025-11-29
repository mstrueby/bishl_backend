
"""
Matchday API Response Models
These models define the structure returned by matchday API endpoints.
"""

from datetime import datetime

from pydantic import BaseModel

from models.tournaments import MongoBaseModel, MatchSettings, MatchdayOwner, Standings


class MatchdayLinks(BaseModel):
    """HATEOAS links for matchday navigation"""
    self: str
    matches: str
    round: str


class MatchdayResponse(MongoBaseModel):
    """Matchday response with links to matches"""
    name: str
    alias: str
    type: dict[str, str]
    startDate: datetime | None = None
    endDate: datetime | None = None
    createStandings: bool
    createStats: bool
    matchSettings: MatchSettings | None = None
    published: bool
    standings: dict[str, Standings] | None = None
    owner: MatchdayOwner | None = None
    links: MatchdayLinks | None = None

    class Config:
        json_schema_extra = {
            "example": {
                "_id": "507f1f77bcf86cd799439014",
                "name": "Matchday 1",
                "alias": "matchday-1",
                "type": {"key": "REGULAR", "value": "Regular"},
                "published": True,
                "createStandings": True,
                "createStats": False,
                "links": {
                    "self": "/tournaments/bishl-2024/seasons/2024-25/rounds/regular/matchdays/matchday-1",
                    "matches": "/matches?tournament=bishl-2024&season=2024-25&round=regular&matchday=matchday-1",
                    "round": "/tournaments/bishl-2024/seasons/2024-25/rounds/regular"
                }
            }
        }
