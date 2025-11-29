
"""
Round API Response Models
These models define the structure returned by round API endpoints.
They exclude nested matchdays array to avoid confusion with HATEOAS links.
"""

from datetime import datetime

from pydantic import BaseModel

from models.tournaments import MongoBaseModel, MatchSettings, Standings


class RoundLinks(BaseModel):
    """HATEOAS links for round navigation"""
    self: str
    matchdays: str
    season: str


class RoundResponse(MongoBaseModel):
    """Round response without nested matchdays array"""
    name: str
    alias: str
    sortOrder: int
    createStandings: bool
    createStats: bool
    matchdaysType: dict[str, str]
    matchdaysSortedBy: dict[str, str]
    startDate: datetime | None = None
    endDate: datetime | None = None
    matchSettings: MatchSettings | None = None
    published: bool
    standings: dict[str, Standings] | None = None
    links: RoundLinks | None = None

    class Config:
        json_schema_extra = {
            "example": {
                "_id": "507f1f77bcf86cd799439013",
                "name": "Regular Season",
                "alias": "regular",
                "sortOrder": 1,
                "published": True,
                "createStandings": True,
                "createStats": True,
                "matchdaysType": {"key": "REGULAR", "value": "Regular"},
                "matchdaysSortedBy": {"key": "DATE", "value": "Date"},
                "links": {
                    "self": "/tournaments/bishl-2024/seasons/2024-25/rounds/regular",
                    "matchdays": "/tournaments/bishl-2024/seasons/2024-25/rounds/regular/matchdays",
                    "season": "/tournaments/bishl-2024/seasons/2024-25"
                }
            }
        }
