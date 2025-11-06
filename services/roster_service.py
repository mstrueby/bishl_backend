
"""
Roster Service - Business logic for roster management

Handles roster validation, updates, and jersey number synchronization across
scores and penalties.
"""

from typing import Any

from bson import ObjectId
from fastapi.encoders import jsonable_encoder

from exceptions import (
    AuthorizationException,
    DatabaseOperationException,
    ResourceNotFoundException,
    ValidationException,
)
from logging_config import logger
from models.matches import RosterPlayer
from services.stats_service import StatsService
from utils import populate_event_player_fields


class RosterService:
    """Service for managing team rosters in matches"""

    def __init__(self, db):
        self.db = db

    async def get_roster(self, match_id: str, team_flag: str) -> list[RosterPlayer]:
        """
        Fetch and populate roster data for a team

        Args:
            match_id: The match ID
            team_flag: Either 'home' or 'away'

        Returns:
            List of RosterPlayer objects with populated display fields
        """
        team_flag = team_flag.lower()
        if team_flag not in ["home", "away"]:
            raise ValidationException(
                field="team_flag", message=f"Must be 'home' or 'away', got '{team_flag}'"
            )

        match = await self.db["matches"].find_one({"_id": match_id})
        if match is None:
            raise ResourceNotFoundException(
                resource_type="Match", resource_id=match_id, details={"team_flag": team_flag}
            )

        roster = match.get(team_flag, {}).get("roster") or []

        if not isinstance(roster, list):
            raise DatabaseOperationException(
                operation="get_roster",
                collection="matches",
                details={"match_id": match_id, "reason": "Unexpected roster data structure"},
            )

        # Populate display fields from player data
        for roster_entry in roster:
            if roster_entry.get("player"):
                await populate_event_player_fields(self.db, roster_entry["player"])

        return [RosterPlayer(**player) for player in roster]

    async def validate_roster_changes(
        self, match: dict, team_flag: str, new_roster: list[RosterPlayer]
    ) -> None:
        """
        Validate that roster changes don't conflict with existing scores/penalties

        Args:
            match: The match document
            team_flag: Either 'home' or 'away'
            new_roster: The proposed new roster

        Raises:
            ValidationException: If players in scores/penalties are not in new roster
        """
        scores = match.get(team_flag, {}).get("scores") or []
        penalties = match.get(team_flag, {}).get("penalties") or []
        new_player_ids = {player.player.playerId for player in new_roster}

        # Check scores
        for score in scores:
            if score["goalPlayer"]["playerId"] not in new_player_ids:
                raise ValidationException(
                    field="roster",
                    message="All players in scores must be in roster",
                    details={
                        "match_id": match["_id"],
                        "team_flag": team_flag,
                        "missing_player": score["goalPlayer"]["playerId"],
                    },
                )
            if score.get("assistPlayer") and score["assistPlayer"]["playerId"] not in new_player_ids:
                raise ValidationException(
                    field="roster",
                    message="All players in scores must be in roster",
                    details={
                        "match_id": match["_id"],
                        "team_flag": team_flag,
                        "missing_player": score["assistPlayer"]["playerId"],
                    },
                )

        # Check penalties
        for penalty in penalties:
            if penalty["penaltyPlayer"]["playerId"] not in new_player_ids:
                raise ValidationException(
                    field="roster",
                    message="All players in penalties must be in roster",
                    details={
                        "match_id": match["_id"],
                        "team_flag": team_flag,
                        "missing_player": penalty["penaltyPlayer"]["playerId"],
                    },
                )

    async def update_jersey_numbers(
        self, match_id: str, team_flag: str, jersey_updates: dict[str, int]
    ) -> None:
        """
        Update jersey numbers across scores and penalties

        Args:
            match_id: The match ID
            team_flag: Either 'home' or 'away'
            jersey_updates: Dict mapping player_id to new jersey number
        """
        if not jersey_updates:
            return

        # Update scores - goal players
        for player_id, jersey_number in jersey_updates.items():
            await self.db["matches"].update_one(
                {"_id": match_id},
                {"$set": {f"{team_flag}.scores.$[score].goalPlayer.jerseyNumber": jersey_number}},
                array_filters=[{"score.goalPlayer.playerId": player_id}],
            )

            # Update scores - assist players
            await self.db["matches"].update_one(
                {"_id": match_id},
                {"$set": {f"{team_flag}.scores.$[score].assistPlayer.jerseyNumber": jersey_number}},
                array_filters=[{"score.assistPlayer.playerId": player_id}],
            )

            # Update penalties
            await self.db["matches"].update_one(
                {"_id": match_id},
                {
                    "$set": {
                        f"{team_flag}.penalties.$[penalty].penaltyPlayer.jerseyNumber": jersey_number
                    }
                },
                array_filters=[{"penalty.penaltyPlayer.playerId": player_id}],
            )

        logger.info(
            "Updated jersey numbers in scores/penalties",
            extra={"match_id": match_id, "team_flag": team_flag, "count": len(jersey_updates)},
        )

    async def update_roster(
        self,
        match_id: str,
        team_flag: str,
        roster_data: list[RosterPlayer],
        user_roles: list[str],
    ) -> list[RosterPlayer]:
        """
        Validate and update roster with authorization checks

        Args:
            match_id: The match ID
            team_flag: Either 'home' or 'away'
            roster_data: The new roster data
            user_roles: User's roles for authorization

        Returns:
            Updated roster with populated fields
        """
        # Authorization check
        if not any(role in user_roles for role in ["ADMIN", "LEAGUE_ADMIN", "CLUB_ADMIN"]):
            raise AuthorizationException(
                message="Admin, League Admin, or Club Admin role required",
                details={
                    "user_roles": user_roles,
                    "required_roles": ["ADMIN", "LEAGUE_ADMIN", "CLUB_ADMIN"],
                },
            )

        team_flag = team_flag.lower()
        if team_flag not in ["home", "away"]:
            raise ValidationException(
                field="team_flag", message=f"Must be 'home' or 'away', got '{team_flag}'"
            )

        match = await self.db["matches"].find_one({"_id": match_id})
        if match is None:
            raise ResourceNotFoundException(
                resource_type="Match", resource_id=match_id, details={"team_flag": team_flag}
            )

        # Validate roster changes
        await self.validate_roster_changes(match, team_flag, roster_data)

        # Populate display fields before saving
        roster_json = jsonable_encoder(roster_data)
        for roster_entry in roster_json:
            if roster_entry.get("player"):
                await populate_event_player_fields(self.db, roster_entry["player"])

        # Create jersey number update mapping
        jersey_updates = {
            roster_entry["player"]["playerId"]: roster_entry["player"]["jerseyNumber"]
            for roster_entry in roster_json
            if roster_entry.get("player", {}).get("playerId")
            and roster_entry.get("player", {}).get("jerseyNumber") is not None
        }

        # Update roster
        update_result = await self.db["matches"].update_one(
            {"_id": match_id}, {"$set": {f"{team_flag}.roster": roster_json}}
        )

        if not update_result.acknowledged:
            raise DatabaseOperationException(
                operation="update_one",
                collection="matches",
                details={
                    "match_id": match_id,
                    "team_flag": team_flag,
                    "reason": "Update operation not acknowledged",
                },
            )

        logger.info(
            "Roster updated",
            extra={
                "match_id": match_id,
                "team_flag": team_flag,
                "roster_size": len(roster_json),
                "modified": update_result.modified_count > 0,
            },
        )

        # Update jersey numbers in scores/penalties
        await self.update_jersey_numbers(match_id, team_flag, jersey_updates)

        # Return updated roster
        return await self.get_roster(match_id, team_flag)
