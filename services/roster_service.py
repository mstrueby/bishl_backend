"""
Roster Service - Business logic for roster management

Handles roster validation, updates, and jersey number synchronization across
scores and penalties. Manages the consolidated Roster object atomically.
"""

from datetime import datetime

from fastapi.encoders import jsonable_encoder

from exceptions import (
    AuthorizationException,
    DatabaseOperationException,
    ResourceNotFoundException,
    ValidationException,
)
from logging_config import logger
from models.matches import Roster, RosterPlayer, RosterStatusEnum, RosterUpdate
from utils import populate_event_player_fields


class RosterService:
    """Service for managing team rosters in matches"""

    def __init__(self, db):
        self.db = db

    def _validate_team_flag(self, team_flag: str) -> str:
        """Validate and normalize team flag."""
        team_flag = team_flag.lower()
        if team_flag not in ["home", "away"]:
            raise ValidationException(
                field="team_flag", message=f"Must be 'home' or 'away', got '{team_flag}'"
            )
        return team_flag

    async def _get_match(self, match_id: str, team_flag: str) -> dict:
        """Fetch match document or raise not found."""
        match = await self.db["matches"].find_one({"_id": match_id})
        if match is None:
            raise ResourceNotFoundException(
                resource_type="Match", resource_id=match_id, details={"team_flag": team_flag}
            )
        return match

    def _check_authorization(self, user_roles: list[str]) -> None:
        """Check if user has required roles for roster management."""
        required_roles = ["ADMIN", "LEAGUE_ADMIN", "CLUB_ADMIN"]
        if not any(role in user_roles for role in required_roles):
            raise AuthorizationException(
                message="Admin, League Admin, or Club Admin role required",
                details={
                    "user_roles": user_roles,
                    "required_roles": required_roles,
                },
            )

    async def get_roster(self, match_id: str, team_flag: str) -> Roster:
        """
        Fetch the complete roster object for a team.

        Args:
            match_id: The match ID
            team_flag: Either 'home' or 'away'

        Returns:
            Roster object with populated player display fields
        """
        team_flag = self._validate_team_flag(team_flag)
        match = await self._get_match(match_id, team_flag)

        roster_data = match.get(team_flag, {}).get("roster") or {}

        # Handle legacy flat structure (list of players)
        if isinstance(roster_data, list):
            roster_data = {
                "players": roster_data,
                "status": match.get(team_flag, {}).get("rosterStatus", "DRAFT"),
                "published": match.get(team_flag, {}).get("rosterPublished", False),
                "eligibilityTimestamp": match.get(team_flag, {}).get("eligibilityTimestamp"),
                "eligibilityValidator": match.get(team_flag, {}).get("eligibilityValidator"),
                "coach": match.get(team_flag, {}).get("coach", {}),
                "staff": match.get(team_flag, {}).get("staff", []),
            }

        if not isinstance(roster_data, dict):
            raise DatabaseOperationException(
                operation="get_roster",
                collection="matches",
                details={"match_id": match_id, "reason": "Unexpected roster data structure"},
            )

        # Populate display fields from player data
        players = roster_data.get("players") or []
        for roster_entry in players:
            if roster_entry.get("player"):
                await populate_event_player_fields(self.db, roster_entry["player"])

        return Roster(**roster_data)

    async def validate_roster_players(
        self, match: dict, team_flag: str, new_players: list[RosterPlayer]
    ) -> None:
        """
        Validate that roster player changes don't conflict with existing scores/penalties.

        Args:
            match: The match document
            team_flag: Either 'home' or 'away'
            new_players: The proposed new player list

        Raises:
            ValidationException: If players in scores/penalties are not in new roster
            ValidationException: If roster contains duplicate players
        """
        if not new_players:
            return

        # Check for duplicate players
        player_ids = [player.player.playerId for player in new_players]
        if len(player_ids) != len(set(player_ids)):
            seen = set()
            duplicates = set()
            for player_id in player_ids:
                if player_id in seen:
                    duplicates.add(player_id)
                seen.add(player_id)

            raise ValidationException(
                field="roster.players",
                message="Roster contains duplicate players",
                details={
                    "match_id": match["_id"],
                    "team_flag": team_flag,
                    "duplicate_player_ids": list(duplicates),
                },
            )

        scores = match.get(team_flag, {}).get("scores") or []
        penalties = match.get(team_flag, {}).get("penalties") or []
        new_player_ids = {player.player.playerId for player in new_players}

        # Check scores
        for score in scores:
            if score["goalPlayer"]["playerId"] not in new_player_ids:
                raise ValidationException(
                    field="roster.players",
                    message="All players in scores must be in roster",
                    details={
                        "match_id": match["_id"],
                        "team_flag": team_flag,
                        "missing_player": score["goalPlayer"]["playerId"],
                    },
                )
            if (
                score.get("assistPlayer")
                and score["assistPlayer"]["playerId"] not in new_player_ids
            ):
                raise ValidationException(
                    field="roster.players",
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
                    field="roster.players",
                    message="All players in penalties must be in roster",
                    details={
                        "match_id": match["_id"],
                        "team_flag": team_flag,
                        "missing_player": penalty["penaltyPlayer"]["playerId"],
                    },
                )

    def validate_status_transition(
        self, current_status: RosterStatusEnum, new_status: RosterStatusEnum, match_id: str, team_flag: str
    ) -> None:
        """
        Validate that the status transition is allowed.

        Args:
            current_status: Current roster status
            new_status: Requested new status
            match_id: Match ID for error context
            team_flag: Team flag for error context

        Raises:
            ValidationException: If the status transition is not allowed
        """
        valid_transitions = {
            RosterStatusEnum.DRAFT: {RosterStatusEnum.SUBMITTED, RosterStatusEnum.INVALID},
            RosterStatusEnum.SUBMITTED: {RosterStatusEnum.APPROVED, RosterStatusEnum.INVALID, RosterStatusEnum.DRAFT},
            RosterStatusEnum.APPROVED: {RosterStatusEnum.INVALID, RosterStatusEnum.DRAFT},
            RosterStatusEnum.INVALID: {RosterStatusEnum.DRAFT},
        }

        allowed = valid_transitions.get(current_status, set())
        if new_status not in allowed:
            raise ValidationException(
                field="roster.status",
                message=f"Cannot transition from {current_status.value} to {new_status.value}",
                details={
                    "match_id": match_id,
                    "team_flag": team_flag,
                    "current_status": current_status.value,
                    "new_status": new_status.value,
                    "allowed_transitions": [s.value for s in allowed],
                },
            )

    async def update_jersey_numbers(
        self, match_id: str, team_flag: str, jersey_updates: dict[str, int]
    ) -> None:
        """
        Update jersey numbers across scores and penalties.

        Args:
            match_id: The match ID
            team_flag: Either 'home' or 'away'
            jersey_updates: Dict mapping player_id to new jersey number
        """
        if not jersey_updates:
            return

        for player_id, jersey_number in jersey_updates.items():
            await self.db["matches"].update_one(
                {"_id": match_id},
                {"$set": {f"{team_flag}.scores.$[score].goalPlayer.jerseyNumber": jersey_number}},
                array_filters=[{"score.goalPlayer.playerId": player_id}],
            )

            await self.db["matches"].update_one(
                {"_id": match_id},
                {"$set": {f"{team_flag}.scores.$[score].assistPlayer.jerseyNumber": jersey_number}},
                array_filters=[{"score.assistPlayer.playerId": player_id}],
            )

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
        roster_update: RosterUpdate,
        user_roles: list[str],
        user_id: str | None = None,
        skip_status_validation: bool = False,
    ) -> tuple[Roster, bool]:
        """
        Atomically update the entire roster object.

        This is the main entry point for roster updates. It handles:
        - Authorization checks
        - Status transition validation
        - Player list validation (duplicates, scores/penalties consistency)
        - Jersey number sync across scores/penalties
        - Eligibility metadata update

        Args:
            match_id: The match ID
            team_flag: Either 'home' or 'away'
            roster_update: The RosterUpdate with fields to update
            user_roles: User's roles for authorization
            user_id: Optional user ID for tracking who made the change
            skip_status_validation: If True, skip status transition validation (for validate endpoint)

        Returns:
            Tuple of (updated Roster, was_modified flag)
        """
        self._check_authorization(user_roles)
        team_flag = self._validate_team_flag(team_flag)
        match = await self._get_match(match_id, team_flag)

        # Get current roster state
        current_roster = await self.get_roster(match_id, team_flag)

        # Build update dict with only provided fields
        update_dict = {}

        # Handle players update
        if roster_update.players is not None:
            await self.validate_roster_players(match, team_flag, roster_update.players)
            
            # Populate display fields before saving
            players_json = jsonable_encoder(roster_update.players)
            for roster_entry in players_json:
                if roster_entry.get("player"):
                    await populate_event_player_fields(self.db, roster_entry["player"])
            
            update_dict["players"] = players_json

            # Track jersey number updates for syncing
            jersey_updates = {
                entry["player"]["playerId"]: entry["player"]["jerseyNumber"]
                for entry in players_json
                if entry.get("player", {}).get("playerId")
                and entry.get("player", {}).get("jerseyNumber") is not None
            }
        else:
            jersey_updates = {}

        # Handle status transition
        if roster_update.status is not None and roster_update.status != current_roster.status:
            if not skip_status_validation:
                self.validate_status_transition(
                    current_roster.status, roster_update.status, match_id, team_flag
                )
            update_dict["status"] = roster_update.status.value

        # Handle simple field updates
        if roster_update.published is not None:
            update_dict["published"] = roster_update.published

        if roster_update.coach is not None:
            update_dict["coach"] = jsonable_encoder(roster_update.coach)

        if roster_update.staff is not None:
            update_dict["staff"] = jsonable_encoder(roster_update.staff)

        # Handle eligibility metadata
        if roster_update.eligibilityTimestamp is not None:
            update_dict["eligibilityTimestamp"] = roster_update.eligibilityTimestamp
        if roster_update.eligibilityValidator is not None:
            update_dict["eligibilityValidator"] = roster_update.eligibilityValidator

        # Auto-update eligibility timestamp/validator on status change to APPROVED
        if roster_update.status == RosterStatusEnum.APPROVED:
            if "eligibilityTimestamp" not in update_dict:
                update_dict["eligibilityTimestamp"] = datetime.utcnow()
            if "eligibilityValidator" not in update_dict and user_id:
                update_dict["eligibilityValidator"] = user_id

        if not update_dict:
            logger.info("No roster changes to apply", extra={"match_id": match_id, "team": team_flag})
            return current_roster, False

        # Apply update atomically
        mongo_update = {f"{team_flag}.roster.{k}": v for k, v in update_dict.items()}
        result = await self.db["matches"].update_one(
            {"_id": match_id},
            {"$set": mongo_update}
        )

        was_modified = result.modified_count > 0

        if was_modified:
            logger.info(
                "Roster updated atomically",
                extra={
                    "match_id": match_id,
                    "team": team_flag,
                    "updated_fields": list(update_dict.keys()),
                }
            )
            # Sync jersey numbers to scores/penalties
            if jersey_updates:
                await self.update_jersey_numbers(match_id, team_flag, jersey_updates)
        else:
            logger.warning("No changes detected in roster update", extra={"match_id": match_id})

        # Return updated roster
        updated_roster = await self.get_roster(match_id, team_flag)
        return updated_roster, was_modified

    async def get_roster_players(self, match_id: str, team_flag: str) -> list[RosterPlayer]:
        """
        Convenience method to get just the player list from a roster.
        Maintains backward compatibility with old API.

        Args:
            match_id: The match ID
            team_flag: Either 'home' or 'away'

        Returns:
            List of RosterPlayer objects
        """
        roster = await self.get_roster(match_id, team_flag)
        return roster.players
