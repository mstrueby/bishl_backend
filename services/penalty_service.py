"""
Penalty Service - Business logic for penalty management

Handles penalty creation, updates, deletion with incremental penalty minute
updates and validation.
"""

from typing import Any

from bson import ObjectId
from fastapi.encoders import jsonable_encoder

from exceptions import (
    DatabaseOperationException,
    ResourceNotFoundException,
    ValidationException,
)
from logging_config import logger
from models.matches import PenaltiesBase, PenaltiesDB, PenaltiesUpdate
from services.stats_service import StatsService
from utils import parse_time_from_seconds, parse_time_to_seconds, populate_event_player_fields


class PenaltyService:
    """Service for managing penalties in matches"""

    def __init__(self, db):
        self.db = db
        self.stats_service = StatsService(db)

    async def _get_match(self, match_id: str) -> dict:
        """Get match document or raise exception"""
        match = await self.db["matches"].find_one({"_id": match_id})
        if match is None:
            raise ResourceNotFoundException(resource_type="Match", resource_id=match_id)
        return match

    async def _validate_match_status(self, match: dict) -> None:
        """Validate match status allows modifications"""
        match_status = match.get("matchStatus", {}).get("key")
        if match_status != "INPROGRESS":
            raise ValidationException(
                field="matchStatus",
                message="Penalties can only be modified when match status is INPROGRESS",
                details={"current_status": match_status},
            )

    async def _validate_player_in_roster(
        self, match: dict, team_flag: str, penalty_data: dict
    ) -> None:
        """Validate that penalty player is in the roster"""
        roster = match.get(team_flag, {}).get("roster") or []
        roster_player_ids = {player["player"]["playerId"] for player in roster}

        penalty_player = penalty_data.get("penaltyPlayer")
        if penalty_player and penalty_player.get("playerId"):
            if penalty_player["playerId"] not in roster_player_ids:
                raise ValidationException(
                    field="penaltyPlayer",
                    message=f"Player with id {penalty_player['playerId']} not in roster",
                    details={"match_id": match["_id"], "team_flag": team_flag},
                )

    async def get_penalties(self, match_id: str, team_flag: str) -> list[PenaltiesDB]:
        """
        Fetch and populate penalty sheet for a team

        Args:
            match_id: The match ID
            team_flag: Either 'home' or 'away'

        Returns:
            List of PenaltiesDB objects with populated player fields
        """
        team_flag = team_flag.lower()
        if team_flag not in ["home", "away"]:
            raise ValidationException(
                field="team_flag", message=f"Must be 'home' or 'away', got '{team_flag}'"
            )

        match = await self._get_match(match_id)
        penalties = match.get(team_flag, {}).get("penalties") or []

        # Parse time and populate player fields
        for penalty in penalties:
            if "matchSecondsStart" in penalty:
                penalty["matchTimeStart"] = parse_time_from_seconds(penalty["matchSecondsStart"])
            if "matchSecondsEnd" in penalty and penalty["matchSecondsEnd"] is not None:
                penalty["matchTimeEnd"] = parse_time_from_seconds(penalty["matchSecondsEnd"])
            if penalty.get("penaltyPlayer"):
                await populate_event_player_fields(self.db, penalty["penaltyPlayer"])

        return [PenaltiesDB(**penalty) for penalty in penalties]

    async def get_penalty_by_id(
        self, match_id: str, team_flag: str, penalty_id: str
    ) -> PenaltiesDB:
        """
        Fetch a single penalty by ID

        Args:
            match_id: The match ID
            team_flag: Either 'home' or 'away'
            penalty_id: The penalty ID

        Returns:
            PenaltiesDB object with populated fields
        """
        team_flag = team_flag.lower()
        if team_flag not in ["home", "away"]:
            raise ValidationException(
                field="team_flag", message=f"Must be 'home' or 'away', got '{team_flag}'"
            )

        penalty = await self.db["matches"].find_one(
            {"_id": match_id, f"{team_flag}.penalties._id": penalty_id},
            {"_id": 0, f"{team_flag}.penalties.$": 1},
        )

        if not penalty or not penalty.get(team_flag) or "penalties" not in penalty.get(team_flag):
            raise ResourceNotFoundException(
                resource_type="Penalty",
                resource_id=penalty_id,
                details={"match_id": match_id, "team_flag": team_flag},
            )

        penalty_data = penalty[team_flag]["penalties"][0]

        # Parse time and populate player fields
        if "matchSecondsStart" in penalty_data:
            penalty_data["matchTimeStart"] = parse_time_from_seconds(
                penalty_data["matchSecondsStart"]
            )
        if "matchSecondsEnd" in penalty_data and penalty_data["matchSecondsEnd"] is not None:
            penalty_data["matchTimeEnd"] = parse_time_from_seconds(penalty_data["matchSecondsEnd"])
        if penalty_data.get("penaltyPlayer"):
            await populate_event_player_fields(self.db, penalty_data["penaltyPlayer"])

        return PenaltiesDB(**penalty_data)

    async def create_penalty(
        self, match_id: str, team_flag: str, penalty: PenaltiesBase
    ) -> PenaltiesDB:
        """
        Create a new penalty with incremental penalty minute updates

        Args:
            match_id: The match ID
            team_flag: Either 'home' or 'away'
            penalty: The penalty data

        Returns:
            Created PenaltiesDB object
        """
        team_flag = team_flag.lower()
        if team_flag not in ["home", "away"]:
            raise ValidationException(
                field="team_flag", message=f"Must be 'home' or 'away', got '{team_flag}'"
            )

        match = await self._get_match(match_id)
        await self._validate_match_status(match)

        # Convert to dict for validation
        penalty_dict = penalty.model_dump()
        await self._validate_player_in_roster(match, team_flag, penalty_dict)

        penalty_player_id = penalty.penaltyPlayer.playerId

        # Prepare penalty data
        new_penalty_id = str(ObjectId())
        penalty_dict.pop("id", None)

        # Extract time strings and convert to seconds
        match_time_start = penalty_dict.pop("matchTimeStart")
        match_time_end = penalty_dict.pop("matchTimeEnd", None)

        penalty_data = {
            "_id": new_penalty_id,
            **penalty_dict,
            "matchSecondsStart": parse_time_to_seconds(match_time_start),
        }
        if match_time_end is not None:
            penalty_data["matchSecondsEnd"] = parse_time_to_seconds(match_time_end)

        penalty_data = jsonable_encoder(penalty_data)

        # Build incremental update operations
        update_operations = {
            "$push": {f"{team_flag}.penalties": penalty_data},
            "$inc": {f"{team_flag}.roster.$[penaltyPlayer].penaltyMinutes": penalty.penaltyMinutes},
        }

        array_filters = [{"penaltyPlayer.player.playerId": penalty_player_id}]

        # Execute update
        update_result = await self.db["matches"].update_one(
            {"_id": match_id}, update_operations, array_filters=array_filters
        )

        if update_result.modified_count == 0:
            raise DatabaseOperationException(
                operation="create_penalty",
                collection="matches",
                details={"match_id": match_id, "penalty_data": penalty_data},
            )

        logger.info(
            "Penalty created with incremental updates",
            extra={
                "match_id": match_id,
                "penalty_id": new_penalty_id,
                "player_id": penalty_player_id,
                "minutes": penalty.penaltyMinutes,
            },
        )

        return await self.get_penalty_by_id(match_id, team_flag, new_penalty_id)

    async def update_penalty(
        self, match_id: str, team_flag: str, penalty_id: str, penalty: PenaltiesUpdate
    ) -> PenaltiesDB:
        """
        Update an existing penalty

        Args:
            match_id: The match ID
            team_flag: Either 'home' or 'away'
            penalty_id: The penalty ID
            penalty: The updated penalty data

        Returns:
            Updated PenaltiesDB object
        """
        team_flag = team_flag.lower()
        if team_flag not in ["home", "away"]:
            raise ValidationException(
                field="team_flag", message=f"Must be 'home' or 'away', got '{team_flag}'"
            )

        match = await self._get_match(match_id)
        await self._validate_match_status(match)

        # Convert to dict for validation
        penalty_dict = penalty.model_dump(exclude_unset=True)
        if penalty_dict:
            await self._validate_player_in_roster(match, team_flag, penalty_dict)

        # Prepare update data
        if "matchTimeStart" in penalty_dict:
            penalty_dict["matchSecondsStart"] = parse_time_to_seconds(
                penalty_dict["matchTimeStart"]
            )
        if "matchTimeEnd" in penalty_dict:
            penalty_dict["matchSecondsEnd"] = parse_time_to_seconds(penalty_dict["matchTimeEnd"])
        penalty_dict = jsonable_encoder(penalty_dict)

        update_data: dict[str, dict[str, Any]] = {"$set": {}}
        for key, value in penalty_dict.items():
            update_data["$set"][f"{team_flag}.penalties.$.{key}"] = value

        if not update_data.get("$set"):
            # No changes
            return await self.get_penalty_by_id(match_id, team_flag, penalty_id)

        # Execute update
        result = await self.db["matches"].update_one(
            {"_id": match_id, f"{team_flag}.penalties._id": penalty_id}, update_data
        )

        if result.modified_count == 0:
            raise ResourceNotFoundException(
                resource_type="Penalty",
                resource_id=penalty_id,
                details={"match_id": match_id, "team_flag": team_flag},
            )

        # Recalculate roster stats
        await self.stats_service.calculate_roster_stats(match_id, team_flag)

        logger.info(
            "Penalty updated",
            extra={"match_id": match_id, "penalty_id": penalty_id, "team_flag": team_flag},
        )

        return await self.get_penalty_by_id(match_id, team_flag, penalty_id)

    async def delete_penalty(self, match_id: str, team_flag: str, penalty_id: str) -> None:
        """
        Delete a penalty with decremental penalty minute updates

        Args:
            match_id: The match ID
            team_flag: Either 'home' or 'away'
            penalty_id: The penalty ID
        """
        team_flag = team_flag.lower()
        if team_flag not in ["home", "away"]:
            raise ValidationException(
                field="team_flag", message=f"Must be 'home' or 'away', got '{team_flag}'"
            )

        match = await self._get_match(match_id)
        await self._validate_match_status(match)

        # Find the penalty to delete
        current_penalty = None
        for penalty_entry in match.get(team_flag, {}).get("penalties", []):
            if penalty_entry["_id"] == penalty_id:
                current_penalty = penalty_entry
                break

        if current_penalty is None:
            raise ResourceNotFoundException(
                resource_type="Penalty",
                resource_id=penalty_id,
                details={"match_id": match_id, "team_flag": team_flag},
            )

        penalty_player_id = current_penalty.get("penaltyPlayer", {}).get("playerId")
        penalty_minutes = current_penalty.get("penaltyMinutes", 0)

        # Build decremental update operations
        update_operations = {
            "$pull": {f"{team_flag}.penalties": {"_id": penalty_id}},
            "$inc": {f"{team_flag}.roster.$[penaltyPlayer].penaltyMinutes": -penalty_minutes},
        }

        array_filters = [{"penaltyPlayer.player.playerId": penalty_player_id}]

        # Execute update
        result = await self.db["matches"].update_one(
            {"_id": match_id, f"{team_flag}.penalties._id": penalty_id},
            update_operations,
            array_filters=array_filters,
        )

        if result.modified_count == 0:
            raise ResourceNotFoundException(
                resource_type="Penalty",
                resource_id=penalty_id,
                details={"match_id": match_id, "team_flag": team_flag},
            )

        logger.info(
            "Penalty deleted with decremental updates",
            extra={
                "match_id": match_id,
                "penalty_id": penalty_id,
                "player_id": penalty_player_id,
                "minutes": penalty_minutes,
            },
        )
