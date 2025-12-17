
"""
Player Assignment Service - Initial license type classification

Classifies player licenses based on passNo suffixes and simple heuristics.
This runs BEFORE LicenseValidationService and sets initial licenseType and status.
"""

from datetime import datetime

from fastapi.encoders import jsonable_encoder

from config import settings
from logging_config import logger
from models.players import (
    LicenseStatusEnum,
    LicenseTypeEnum,
    SourceEnum,
)


class PlayerAssignmentService:
    """Service for initial classification of player license types"""

    def __init__(self, db):
        self.db = db

    async def classify_player_licenses(self, player: dict) -> dict:
        """
        Apply passNo suffix heuristics and PRIMARY heuristic to set licenseType
        and initial status on all AssignedTeams.

        Args:
            player: Raw player dict from MongoDB (including assignedTeams)

        Returns:
            Modified player dict (does NOT persist to database)
        """
        if not player.get("assignedTeams"):
            return player

        # Collect all licenses across all clubs
        all_licenses = []
        for club in player["assignedTeams"]:
            for team in club.get("teams", []):
                all_licenses.append((club, team))

        # Step 1: Apply suffix-based classification
        for club, team in all_licenses:
            # Only classify if not already set
            if team.get("licenseType") == LicenseTypeEnum.UNKNOWN or not team.get("licenseType"):
                license_type = self._classify_by_pass_suffix(team.get("passNo", ""))
                team["licenseType"] = license_type

        # Step 2: Apply PRIMARY heuristic
        # Count licenses that are still UNKNOWN after suffix rules
        unknown_licenses = [
            (club, team) for club, team in all_licenses
            if team.get("licenseType") == LicenseTypeEnum.UNKNOWN
        ]

        # If player has exactly one license total and it's still UNKNOWN, make it PRIMARY
        if len(all_licenses) == 1 and len(unknown_licenses) == 1:
            club, team = unknown_licenses[0]
            team["licenseType"] = LicenseTypeEnum.PRIMARY
            if settings.DEBUG_LEVEL > 0:
                logger.debug(
                    f"Set single license to PRIMARY for player {player.get('firstName')} {player.get('lastName')}"
                )

        # Step 3: Set initial status based on licenseType
        for club, team in all_licenses:
            license_type = team.get("licenseType")
            if license_type and license_type != LicenseTypeEnum.UNKNOWN:
                # Set initial status to VALID for classified licenses
                team["status"] = LicenseStatusEnum.VALID
                # Clear any existing invalidReasonCodes (will be set by validation service)
                team["invalidReasonCodes"] = []
            else:
                # Keep UNKNOWN status for unclassified licenses
                team["status"] = LicenseStatusEnum.UNKNOWN
                team["invalidReasonCodes"] = []

        return player

    def _classify_by_pass_suffix(self, pass_no: str) -> str:
        """
        Classify license type based on passNo suffix.

        Args:
            pass_no: The license/pass number

        Returns:
            LicenseTypeEnum value
        """
        if not pass_no:
            return LicenseTypeEnum.UNKNOWN

        # Normalize: strip whitespace and convert to uppercase
        pass_no_normalized = pass_no.strip().upper()

        # Check suffix
        if pass_no_normalized.endswith("F"):
            return LicenseTypeEnum.DEVELOPMENT
        elif pass_no_normalized.endswith("A"):
            return LicenseTypeEnum.SECONDARY
        elif pass_no_normalized.endswith("L"):
            return LicenseTypeEnum.LOAN
        else:
            # No recognized suffix - leave as UNKNOWN for now
            # PRIMARY heuristic will handle single-license case
            return LicenseTypeEnum.UNKNOWN

    async def update_player_licenses_in_db(self, player_id: str) -> bool:
        """
        Load a player by _id, run classification, and update in MongoDB.

        Args:
            player_id: The player's _id

        Returns:
            True if player was modified, False otherwise
        """
        player = await self.db["players"].find_one({"_id": player_id})
        if not player:
            logger.warning(f"Player not found: {player_id}")
            return False

        # Capture original state
        original_assigned_teams = jsonable_encoder(player.get("assignedTeams", []))

        # Apply classification
        player = await self.classify_player_licenses(player)

        # Check if anything changed
        new_assigned_teams = jsonable_encoder(player.get("assignedTeams", []))
        if original_assigned_teams == new_assigned_teams:
            return False

        # Persist changes
        await self.db["players"].update_one(
            {"_id": player_id},
            {"$set": {"assignedTeams": new_assigned_teams}}
        )

        logger.info(
            f"Updated license classifications for player {player_id}: "
            f"{player.get('firstName')} {player.get('lastName')}"
        )
        return True

    async def bootstrap_all_players(self, batch_size: int = 1000) -> list[str]:
        """
        One-time migration: iterate over all players and apply classification.

        Args:
            batch_size: Number of players to process in each batch

        Returns:
            List of player IDs that were modified
        """
        modified_ids = []
        total_processed = 0
        total_modified = 0

        logger.info("Starting bootstrap classification of all player licenses...")

        # Process in batches to avoid memory issues
        cursor = self.db["players"].find({})
        batch = []

        async for player in cursor:
            batch.append(player)

            if len(batch) >= batch_size:
                # Process batch
                for p in batch:
                    total_processed += 1
                    was_modified = await self.update_player_licenses_in_db(p["_id"])
                    if was_modified:
                        modified_ids.append(p["_id"])
                        total_modified += 1

                logger.info(
                    f"Processed {total_processed} players, modified {total_modified} so far..."
                )
                batch = []

        # Process remaining players in final batch
        for p in batch:
            total_processed += 1
            was_modified = await self.update_player_licenses_in_db(p["_id"])
            if was_modified:
                modified_ids.append(p["_id"])
                total_modified += 1

        logger.info(
            f"Bootstrap complete: processed {total_processed} players, "
            f"modified {total_modified} players"
        )

        return modified_ids

    async def apply_heuristics_for_imported_player(self, player_doc: dict) -> dict:
        """
        Hook for process_ishd_data: apply classification to a player doc
        right after ISHD import, before persisting to MongoDB.

        Args:
            player_doc: In-memory player document from ISHD import

        Returns:
            Modified player document
        """
        return await self.classify_player_licenses(player_doc)

    async def get_classification_stats(self) -> dict:
        """
        Get statistics about license classifications across all players.

        Returns:
            Dictionary with classification statistics
        """
        stats = {
            "total_licenses": 0,
            "by_type": {
                LicenseTypeEnum.PRIMARY: 0,
                LicenseTypeEnum.SECONDARY: 0,
                LicenseTypeEnum.OVERAGE: 0,
                LicenseTypeEnum.LOAN: 0,
                LicenseTypeEnum.DEVELOPMENT: 0,
                LicenseTypeEnum.SPECIAL: 0,
                LicenseTypeEnum.UNKNOWN: 0,
            },
            "by_status": {
                LicenseStatusEnum.VALID: 0,
                LicenseStatusEnum.INVALID: 0,
                LicenseStatusEnum.UNKNOWN: 0,
            },
        }

        async for player in self.db["players"].find({}):
            for club in player.get("assignedTeams", []):
                for team in club.get("teams", []):
                    stats["total_licenses"] += 1

                    license_type = team.get("licenseType", LicenseTypeEnum.UNKNOWN)
                    stats["by_type"][license_type] = stats["by_type"].get(license_type, 0) + 1

                    status = team.get("status", LicenseStatusEnum.UNKNOWN)
                    stats["by_status"][status] = stats["by_status"].get(status, 0) + 1

        return stats
