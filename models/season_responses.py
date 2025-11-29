
"""
Season API Response Models
These models define the structure returned by season API endpoints.
They exclude nested rounds array to avoid confusion with HATEOAS links.
"""

from pydantic import BaseModel

from models.tournaments import MongoBaseModel, StandingsSettings


class SeasonLinks(BaseModel):
    """HATEOAS links for season navigation"""
    self: str
    rounds: str
    tournament: str


class SeasonResponse(MongoBaseModel):
    """Season response without nested rounds array"""
    name: str
    alias: str
    standingsSettings: StandingsSettings | None = None
    published: bool
    links: SeasonLinks | None = None

    class Config:
        json_schema_extra = {
            "example": {
                "_id": "507f1f77bcf86cd799439012",
                "name": "2024/25",
                "alias": "2024-25",
                "published": True,
                "standingsSettings": {
                    "pointsWinReg": 3,
                    "pointsLossReg": 0
                },
                "links": {
                    "self": "/tournaments/bishl-2024/seasons/2024-25",
                    "rounds": "/tournaments/bishl-2024/seasons/2024-25/rounds",
                    "tournament": "/tournaments/bishl-2024"
                }
            }
        }
