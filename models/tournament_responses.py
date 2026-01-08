"""
Tournament API Response Models
These models define the structure returned by tournament API endpoints.
They exclude nested arrays to avoid confusion with HATEOAS links.
"""

from pydantic import BaseModel, HttpUrl

from models.tournaments import AssignmentTimeWindow, MongoBaseModel


class TournamentLinks(BaseModel):
    """HATEOAS links for tournament navigation"""

    self: str
    seasons: str


class TournamentResponse(MongoBaseModel):
    """Tournament response without nested seasons array"""

    name: str
    alias: str
    tinyName: str
    ageGroup: dict[str, str]
    published: bool = False
    active: bool = False
    external: bool = False
    website: HttpUrl | None = None
    assignmentTimeWindow: AssignmentTimeWindow = AssignmentTimeWindow()
    legacyId: int | None = None
    links: TournamentLinks | None = None

    class Config:
        json_schema_extra = {
            "example": {
                "_id": "507f1f77bcf86cd799439011",
                "name": "BISHL 2024/25",
                "alias": "bishl-2024",
                "tinyName": "BISHL",
                "ageGroup": {"key": "ADULTS", "value": "Adults"},
                "published": True,
                "active": True,
                "external": False,
                "website": "https://bishl.de",
                "links": {
                    "self": "/tournaments/bishl-2024",
                    "seasons": "/tournaments/bishl-2024/seasons",
                },
            }
        }
