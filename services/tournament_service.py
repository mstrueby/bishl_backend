"""
Tournament Service - Direct database operations for tournament data
Replaces HTTP calls to internal tournament API endpoints
"""

from typing import Any

from exceptions import DatabaseOperationException, ResourceNotFoundException
from logging_config import logger
from services.performance_monitor import monitor_query


class TournamentService:
    """Service for tournament-related operations without HTTP overhead"""

    def __init__(self, mongodb):
        self.db = mongodb

    @monitor_query("get_standings_settings")
    async def get_standings_settings(
        self, tournament_alias: str, season_alias: str
    ) -> dict[str, Any]:
        """
        Get standings settings for a tournament/season directly from database.
        Replaces: GET /tournaments/{t_alias}/seasons/{s_alias}

        Args:
            tournament_alias: Tournament identifier
            season_alias: Season identifier

        Returns:
            Dictionary containing standings settings

        Raises:
            ResourceNotFoundException: If tournament/season not found
        """
        logger.debug(
            "Fetching standings settings",
            extra={"tournament": tournament_alias, "season": season_alias},
        )

        tournament = await self.db["tournaments"].find_one({"alias": tournament_alias})

        if not tournament:
            raise ResourceNotFoundException(
                resource_type="Tournament", resource_id=tournament_alias
            )

        season = next(
            (s for s in tournament.get("seasons", []) if s.get("alias") == season_alias), None
        )

        if not season:
            raise ResourceNotFoundException(
                resource_type="Season", resource_id=f"{tournament_alias}/{season_alias}"
            )

        settings = season.get("standingsSettings")
        if not settings:
            raise ResourceNotFoundException(
                resource_type="StandingsSettings",
                resource_id=f"{tournament_alias}/{season_alias}",
                details={"message": "No standings settings found"},
            )

        return settings

    @monitor_query("get_matchday_info")
    async def get_matchday_info(
        self, t_alias: str, s_alias: str, r_alias: str, md_alias: str
    ) -> dict[str, Any]:
        """
        Get matchday information including referee points.
        Replaces: GET /tournaments/{t_alias}/seasons/{s_alias}/rounds/{r_alias}/matchdays/{md_alias}

        Args:
            t_alias: Tournament alias
            s_alias: Season alias
            r_alias: Round alias
            md_alias: Matchday alias

        Returns:
            Dictionary containing matchday data

        Raises:
            ResourceNotFoundException: If matchday not found
        """
        logger.debug(
            "Fetching matchday info",
            extra={
                "tournament": t_alias,
                "season": s_alias,
                "round": r_alias,
                "matchday": md_alias,
            },
        )

        tournament = await self.db["tournaments"].find_one({"alias": t_alias})

        if not tournament:
            raise ResourceNotFoundException(resource_type="Tournament", resource_id=t_alias)

        season = next((s for s in tournament.get("seasons", []) if s.get("alias") == s_alias), None)

        if not season:
            raise ResourceNotFoundException(
                resource_type="Season", resource_id=f"{t_alias}/{s_alias}"
            )

        round_data = next((r for r in season.get("rounds", []) if r.get("alias") == r_alias), None)

        if not round_data:
            raise ResourceNotFoundException(
                resource_type="Round", resource_id=f"{t_alias}/{s_alias}/{r_alias}"
            )

        matchday = next(
            (md for md in round_data.get("matchdays", []) if md.get("alias") == md_alias), None
        )

        if not matchday:
            raise ResourceNotFoundException(
                resource_type="Matchday", resource_id=f"{t_alias}/{s_alias}/{r_alias}/{md_alias}"
            )

        return matchday

    @monitor_query("get_round_info")
    async def get_round_info(self, t_alias: str, s_alias: str, r_alias: str) -> dict[str, Any]:
        """
        Get round information.
        Replaces: GET /tournaments/{t_alias}/seasons/{s_alias}/rounds/{r_alias}

        Args:
            t_alias: Tournament alias
            s_alias: Season alias
            r_alias: Round alias

        Returns:
            Dictionary containing round data

        Raises:
            ResourceNotFoundException: If round not found
        """
        logger.debug(
            "Fetching round info",
            extra={"tournament": t_alias, "season": s_alias, "round": r_alias},
        )

        tournament = await self.db["tournaments"].find_one({"alias": t_alias})

        if not tournament:
            raise ResourceNotFoundException(resource_type="Tournament", resource_id=t_alias)

        season = next((s for s in tournament.get("seasons", []) if s.get("alias") == s_alias), None)

        if not season:
            raise ResourceNotFoundException(
                resource_type="Season", resource_id=f"{t_alias}/{s_alias}"
            )

        round_data = next((r for r in season.get("rounds", []) if r.get("alias") == r_alias), None)

        if not round_data:
            raise ResourceNotFoundException(
                resource_type="Round", resource_id=f"{t_alias}/{s_alias}/{r_alias}"
            )

        return round_data

    @monitor_query("update_round_dates")
    async def update_round_dates(
        self, round_id: str, t_alias: str, s_alias: str, r_alias: str
    ) -> None:
        """
        Update round start/end dates based on matches.
        Replaces: PATCH /tournaments/{t_alias}/seasons/{s_alias}/rounds/{round_id}

        Args:
            round_id: Round document ID
            t_alias: Tournament alias
            s_alias: Season alias
            r_alias: Round alias
        """
        logger.debug(
            "Updating round dates",
            extra={"round_id": round_id, "tournament": t_alias, "season": s_alias},
        )

        # Get all matches in this round
        matches = (
            await self.db["matches"]
            .find({"tournament.alias": t_alias, "season.alias": s_alias, "round.alias": r_alias})
            .sort("startDate", 1)
            .to_list(length=None)
        )

        if not matches:
            logger.warning("No matches found for round date update")
            return

        start_date = matches[0]["startDate"]
        end_date = matches[-1]["startDate"]

        # Update round dates
        try:
            await self.db["tournaments"].update_one(
                {"alias": t_alias, "seasons.alias": s_alias, "seasons.rounds._id": round_id},
                {
                    "$set": {
                        "seasons.$[season].rounds.$[round].startDate": start_date,
                        "seasons.$[season].rounds.$[round].endDate": end_date,
                    }
                },
                array_filters=[{"season.alias": s_alias}, {"round._id": round_id}],
            )
        except Exception as e:
            raise DatabaseOperationException(
                operation="update_round_dates",
                collection="tournaments",
                details={"error": str(e), "round_id": round_id},
            ) from e

    @monitor_query("update_matchday_dates")
    async def update_matchday_dates(
        self, matchday_id: str, t_alias: str, s_alias: str, r_alias: str, md_alias: str
    ) -> None:
        """
        Update matchday start/end dates based on matches.
        Replaces: PATCH /tournaments/{t_alias}/seasons/{s_alias}/rounds/{r_alias}/matchdays/{md_id}

        Args:
            matchday_id: Matchday document ID
            t_alias: Tournament alias
            s_alias: Season alias
            r_alias: Round alias
            md_alias: Matchday alias
        """
        logger.debug(
            "Updating matchday dates",
            extra={
                "matchday_id": matchday_id,
                "tournament": t_alias,
                "season": s_alias,
                "round": r_alias,
            },
        )

        # Get all matches in this matchday
        matches = (
            await self.db["matches"]
            .find(
                {
                    "tournament.alias": t_alias,
                    "season.alias": s_alias,
                    "round.alias": r_alias,
                    "matchday.alias": md_alias,
                }
            )
            .sort("startDate", 1)
            .to_list(length=None)
        )

        if not matches:
            logger.warning("No matches found for matchday date update")
            return

        start_date = matches[0]["startDate"]
        end_date = matches[-1]["startDate"]

        # Update matchday dates
        try:
            await self.db["tournaments"].update_one(
                {
                    "alias": t_alias,
                    "seasons.alias": s_alias,
                    "seasons.rounds.alias": r_alias,
                    "seasons.rounds.matchdays._id": matchday_id,
                },
                {
                    "$set": {
                        "seasons.$[season].rounds.$[round].matchdays.$[matchday].startDate": start_date,
                        "seasons.$[season].rounds.$[round].matchdays.$[matchday].endDate": end_date,
                    }
                },
                array_filters=[
                    {"season.alias": s_alias},
                    {"round.alias": r_alias},
                    {"matchday._id": matchday_id},
                ],
            )
        except Exception as e:
            raise DatabaseOperationException(
                operation="update_matchday_dates",
                collection="tournaments",
                details={"error": str(e), "matchday_id": matchday_id},
            ) from e
