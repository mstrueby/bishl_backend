
"""
Match Service - Direct database operations for matches
Replaces HTTP calls to internal match API endpoints
"""
from datetime import datetime
from typing import Any

from logging_config import logger
from services.performance_monitor import monitor_query


class MatchService:
    """Service for match-related operations without HTTP overhead"""

    def __init__(self, mongodb):
        self.db = mongodb

    @monitor_query("get_matches_for_referee")
    async def get_matches_for_referee(
        self, referee_id: str, date_from: datetime | None = None
    ) -> list[dict[str, Any]]:
        """
        Get matches assigned to a referee.
        Replaces: GET /matches/?referee={referee_id}&date_from={date}

        Args:
            referee_id: User ID of referee
            date_from: Optional start date filter

        Returns:
            List of match documents
        """
        logger.debug(
            "Fetching matches for referee",
            extra={"referee_id": referee_id, "date_from": date_from}
        )

        query: dict[str, Any] = {
            "$or": [
                {"referee1.userId": referee_id},
                {"referee2.userId": referee_id}
            ]
        }

        if date_from:
            query["startDate"] = {"$gte": date_from}

        matches = await self.db["matches"].find(query).sort("startDate", 1).to_list(length=None)

        return matches

    @monitor_query("get_referee_assignments")
    async def get_referee_assignments(self, referee_id: str) -> list[dict[str, Any]]:
        """
        Get assignment records for a referee.
        Replaces: GET /assignments/?referee={referee_id}

        Args:
            referee_id: User ID of referee

        Returns:
            List of assignment documents
        """
        logger.debug(
            "Fetching assignments for referee",
            extra={"referee_id": referee_id}
        )

        assignments = await self.db["assignments"].find(
            {"referee.userId": referee_id}
        ).to_list(length=None)

        return assignments
