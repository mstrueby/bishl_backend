"""
Player Assignment Service - Unified license classification and validation

Responsibilities:
1. Classification: Set licenseType based on passNo suffixes and heuristics
2. Validation: Set status and invalidReasonCodes based on WKO/BISHL rules
3. ISHD Sync: Fetch and synchronize player data from ISHD API

This service is the single entry point for all license-related operations.
"""

import base64
import json
import os
import ssl
import urllib.parse
from datetime import datetime
from typing import Any

import aiohttp
from fastapi.encoders import jsonable_encoder

from config import settings
from exceptions import DatabaseOperationException, ExternalServiceException
from logging_config import logger
from models.clubs import TeamType
from models.players import (
    AssignedClubs,
    AssignedTeams,
    ClubType,
    IshdAction,
    IshdLogBase,
    IshdLogClub,
    IshdLogPlayer,
    IshdLogTeam,
    LicenseInvalidReasonCode,
    LicenseStatus,
    LicenseType,
    OverAgeRule,
    PlayerBase,
    PlayerDB,
    SecondaryRule,
    Sex,
    Source,
    WkoRule,
)


class PlayerAssignmentService:
    """Service for player license classification and validation"""

    # WKO Rule Configuration
    WKO_RULES: list[WkoRule] = [
        WkoRule(
            ageGroup="HERREN",
            label="Herren",
            sortOrder=1,
            altKey="Herren",
            sex=[Sex.MALE, Sex.FEMALE],
            maxTotalAgeClasses={Sex.MALE: 2, Sex.FEMALE: 2},
        ),
        WkoRule(
            ageGroup="DAMEN",
            label="Damen",
            sortOrder=2,
            altKey="Damen",
            sex=[Sex.FEMALE],
            secondaryRules=[
                SecondaryRule(
                    targetAgeGroup="HERREN",
                    sex=[Sex.FEMALE],
                    maxLicenses=1,
                    requiresAdmin=False,
                )
            ],
            maxTotalAgeClasses={Sex.MALE: 2, Sex.FEMALE: 2},
        ),
        WkoRule(
            ageGroup="U19",
            label="U19",
            sortOrder=3,
            altKey="Junioren",
            sex=[Sex.MALE, Sex.FEMALE],
            secondaryRules=[
                SecondaryRule(
                    targetAgeGroup="HERREN", sex=[Sex.MALE], maxLicenses=99, requiresAdmin=False
                ),
                SecondaryRule(
                    targetAgeGroup="DAMEN",
                    sex=[Sex.FEMALE],
                    maxLicenses=99,
                    requiresAdmin=False,
                ),
            ],
            overAgeRules=[
                OverAgeRule(
                    targetAgeGroup="U16",
                    sex=[Sex.MALE, Sex.FEMALE],
                    maxLicenses=1,
                    maxOverAgePlayersPerTeam=3,
                )
            ],
            maxTotalAgeClasses={Sex.MALE: 2, Sex.FEMALE: 3},
        ),
        WkoRule(
            ageGroup="U16",
            label="U16",
            sortOrder=4,
            altKey="Jugend",
            sex=[Sex.MALE, Sex.FEMALE],
            secondaryRules=[
                SecondaryRule(
                    targetAgeGroup="U19",
                    sex=[Sex.MALE, Sex.FEMALE],
                    maxLicenses=1,
                    requiresAdmin=False,
                ),
                SecondaryRule(
                    targetAgeGroup="HERREN", sex=[Sex.MALE], maxLicenses=1, requiresAdmin=False
                ),
                SecondaryRule(
                    targetAgeGroup="DAMEN", sex=[Sex.FEMALE], maxLicenses=1, requiresAdmin=True
                ),
            ],
            overAgeRules=[
                OverAgeRule(
                    targetAgeGroup="U13",
                    sex=[Sex.MALE, Sex.FEMALE],
                    maxLicenses=1,
                    maxOverAgePlayersPerTeam=3,
                )
            ],
            maxTotalAgeClasses={Sex.MALE: 2, Sex.FEMALE: 3},
        ),
        WkoRule(
            ageGroup="U13",
            label="U13",
            sortOrder=5,
            altKey="Schüler",
            sex=[Sex.MALE, Sex.FEMALE],
            secondaryRules=[
                SecondaryRule(
                    targetAgeGroup="U16",
                    sex=[Sex.MALE, Sex.FEMALE],
                    maxLicenses=1,
                    requiresAdmin=False,
                ),
                SecondaryRule(
                    targetAgeGroup="DAMEN", sex=[Sex.FEMALE], maxLicenses=1, requiresAdmin=True
                ),
            ],
            overAgeRules=[
                OverAgeRule(
                    targetAgeGroup="U10",
                    sex=[Sex.MALE, Sex.FEMALE],
                    maxLicenses=1,
                    maxOverAgePlayersPerTeam=3,
                )
            ],
            maxTotalAgeClasses={Sex.MALE: 2, Sex.FEMALE: 3},
        ),
        WkoRule(
            ageGroup="U10",
            label="U10",
            sortOrder=6,
            altKey="Bambini",
            sex=[Sex.MALE, Sex.FEMALE],
            secondaryRules=[
                SecondaryRule(
                    targetAgeGroup="U13",
                    sex=[Sex.MALE, Sex.FEMALE],
                    maxLicenses=1,
                    requiresAdmin=False,
                ),
                SecondaryRule(
                    targetAgeGroup="DAMEN", sex=[Sex.FEMALE], maxLicenses=1, requiresAdmin=True
                ),
            ],
            overAgeRules=[
                OverAgeRule(
                    targetAgeGroup="U8",
                    sex=[Sex.MALE, Sex.FEMALE],
                    maxLicenses=1,
                    maxOverAgePlayersPerTeam=2,
                ),
            ],
            maxTotalAgeClasses={Sex.MALE: 2, Sex.FEMALE: 3},
        ),
        WkoRule(
            ageGroup="U8",
            label="U8",
            sortOrder=7,
            altKey="Mini",
            sex=[Sex.MALE, Sex.FEMALE],
            secondaryRules=[
                SecondaryRule(
                    targetAgeGroup="U10",
                    sex=[Sex.MALE, Sex.FEMALE],
                    maxLicenses=1,
                    requiresAdmin=False,
                ),
                SecondaryRule(
                    targetAgeGroup="DAMEN", sex=[Sex.FEMALE], maxLicenses=1, requiresAdmin=True
                ),
            ],
            maxTotalAgeClasses={Sex.MALE: 2, Sex.FEMALE: 3},
        ),
    ]

    # DEFAULT Maximum number of active age class participations allowed by WKO
    MAX_AGE_CLASS_PARTICIPATIONS = 2

    def _is_primary_like(self, license_type: LicenseType) -> bool:
        """PRIMARY acts as primary-like for anchor/quotas/consistency."""
        return license_type == LicenseType.PRIMARY

    def __init__(self, db):
        self.db = db
        # Build age group map from WKO_RULES, keeping as Pydantic model objects
        self._wko_rules = {rule.ageGroup: rule for rule in self.WKO_RULES}
        # License types that count as "primary-like" for WKO participation limits
        self.PRIMARY_LIKE_TYPES = {LicenseType.PRIMARY}

    def _prepare_player_for_validation(self, player: dict) -> dict:
        """
        Prepare a player dict for Pydantic validation by ensuring required fields
        have fallback values. This handles legacy data that may be missing fields.
        """
        player_copy = player.copy()
        if "displayFirstName" not in player_copy:
            player_copy["displayFirstName"] = player_copy.get("firstName", "")
        if "displayLastName" not in player_copy:
            player_copy["displayLastName"] = player_copy.get("lastName", "")
        return player_copy

    def _is_team_allowed(
        self, player_age: str, team_age: str, sex: Sex, over_age_flag: bool = False
    ):
        """
        Checks if a player of a given age and sex is allowed to play in a team of a given age
        based on WKO secondary and overage rules.

        Returns: (is_allowed, max_licenses, requires_admin)
        """
        if player_age not in self._wko_rules:
            return False, None, False

        rule = self._wko_rules[player_age]

        # Check secondaryRules (playing in older age groups)
        for sec in rule.secondaryRules:
            if sec.targetAgeGroup == team_age and (not sec.sex or sex in sec.sex):
                return True, sec.maxLicenses, sec.requiresAdmin

        # Check overAgeRules (playing in younger age groups)
        for over in rule.overAgeRules:
            if over.targetAgeGroup == team_age and (not over.sex or sex in over.sex):
                # Only allowed if player has the overAge flag set to true
                if not over_age_flag:
                    return False, over.maxLicenses, getattr(over, "requiresAdmin", False)

                # Overage rules in WKO might not have requiresAdmin field,
                # but we return a consistent signature. Default to False if missing.
                requires_admin = getattr(over, "requiresAdmin", False)
                return True, over.maxLicenses, requires_admin

        # Default: not allowed
        return False, None, False

    # ========================================================================
    # CLASSIFICATION METHODS (only touch licenseType)
    # ========================================================================

    async def classify_license_types_for_player(self, player: dict) -> dict:
        """
        Classification step: sets only assignedTeams[*].licenseType
        based on heuristics (passNo suffix) and simple structural rules.

        Does NOT set status or invalidReasonCodes.
        Returns the modified player dict; does not persist to database.

        Args:
          player: Raw player dict from MongoDB (including assignedTeams)

        Returns:
          Modified player dict
        """
        if not player.get("assignedTeams"):
            return player

        # Collect all licenses across all clubs
        all_licenses = []
        for club in player["assignedTeams"]:
            for team in club.get("teams", []):
                all_licenses.append((club, team))

        # Step 1: Handle single license case
        # Classify based on age group comparison rather than defaulting to PRIMARY
        if len(all_licenses) == 1:
            club, team = all_licenses[0]

            # PROTECT LOAN and SPECIAL licenses from being changed
            if team.get("licenseType") in [LicenseType.LOAN, LicenseType.SPECIAL]:
                return player

            team_age_group = team.get("teamAgeGroup")

            # Get player's age group for comparison
            player_obj = PlayerDB(**self._prepare_player_for_validation(player))
            player_age_group = player_obj.ageGroup

            # Determine license type based on age group relationship
            license_type = self._classify_single_license_by_age_group(
                player_age_group, team_age_group, player_obj.overAge
            )
            team["licenseType"] = license_type

            if settings.DEBUG_LEVEL > 0:
                logger.debug(
                    f"Set single license to {license_type.value} for player "
                    f"{player.get('firstName')} {player.get('lastName')} "
                    f"(player age: {player_age_group}, team age: {team_age_group})"
                )
            return player

        # Step 2: Apply suffix-based classification
        for club, team in all_licenses:
            # PROTECT LOAN and SPECIAL licenses from being changed
            if team.get("licenseType") in [LicenseType.LOAN, LicenseType.SPECIAL]:
                continue

            # Only classify if licenseType is UNKNOWN or not set
            if team.get("licenseType") == LicenseType.UNKNOWN or not team.get("licenseType"):
                license_type = self._classify_by_pass_suffix(team.get("passNo", ""))
                team["licenseType"] = license_type

                # New rule: if "F" suffix was used, it returned PRIMARY, but mark club as DEVELOPMENT
                pass_no = team.get("passNo") or ""
                if pass_no.strip().upper().endswith("F"):
                    club["clubType"] = ClubType.DEVELOPMENT

        # Step 2b: Detect DEVELOPMENT clubs - check ALL teams (not just newly classified)
        # A club is DEVELOPMENT if passNo ends with 'F'
        for club, team in all_licenses:
            pass_no = team.get("passNo") or ""
            if pass_no.strip().upper().endswith("F"):
                club["clubType"] = ClubType.DEVELOPMENT

        # Step 2c: Detect LOAN clubs - check ALL teams (not just newly classified)
        # A club is LOAN if passNo ends with 'L' OR licenseType is LOAN
        for club, team in all_licenses:
            pass_no = team.get("passNo") or ""
            if pass_no.strip().upper().endswith("L") or team.get("licenseType") == LicenseType.LOAN:
                club["clubType"] = ClubType.LOAN

        # Step 3: Apply PRIMARY heuristic for UNKNOWN licenses based on age group match
        # We need to determine player's age group first
        player_obj = PlayerDB(**self._prepare_player_for_validation(player))
        player_age_group = player_obj.ageGroup

        for club in player.get("assignedTeams", []):
            for team in club.get("teams", []):
                # PROTECT LOAN and SPECIAL licenses from being changed
                if team.get("licenseType") in [LicenseType.LOAN, LicenseType.SPECIAL]:
                    continue

                if team.get("licenseType") == LicenseType.UNKNOWN:
                    team_age_group = team.get("teamAgeGroup")
                    # If team age group matches player age group, set as PRIMARY
                    if team_age_group and team_age_group == player_age_group:
                        team["licenseType"] = LicenseType.PRIMARY
                        if settings.DEBUG_LEVEL > 0:
                            logger.debug(
                                f"Set license to PRIMARY based on age group match ({player_age_group}) "
                                f"for player {player.get('firstName')} {player.get('lastName')}"
                            )

        # Step 4: Detect and set OVERAGE licenses
        # OVERAGE licenses are when a license is exactly one age group below the player's age group
        if player_age_group in self._wko_rules:
            player_rule = self._wko_rules[player_age_group]
            player_sort_order = player_rule.sortOrder

            for club in player.get("assignedTeams", []):
                for team in club.get("teams", []):
                    # PROTECT LOAN and SPECIAL licenses from being changed
                    if team.get("licenseType") in [LicenseType.LOAN, LicenseType.SPECIAL]:
                        continue

                    # Only check UNKNOWN licenses
                    if team.get("licenseType") == LicenseType.UNKNOWN:
                        team_age_group = team.get("teamAgeGroup")
                        if not team_age_group or team_age_group not in self._wko_rules:
                            continue

                        team_rule = self._wko_rules[team_age_group]
                        team_sort_order = team_rule.sortOrder

                        # OVERAGE: team is exactly one age group below player
                        # (higher sortOrder means younger age group)
                        if team_sort_order == player_sort_order + 1:
                            team["licenseType"] = LicenseType.OVERAGE
                            if settings.DEBUG_LEVEL > 0:
                                logger.debug(
                                    f"Set license to OVERAGE for team {team.get('teamName')} "
                                    f"(player age group: {player_age_group}, team age group: {team_age_group}) "
                                    f"for player {player.get('firstName')} {player.get('lastName')}"
                                )

        # Step 5: Set ISHD UNKNOWN licenses to PRIMARY in clubs without PRIMARY
        # First, identify clubs with PRIMARY licenses
        clubs_with_primary = set()
        for club in player.get("assignedTeams", []):
            for team in club.get("teams", []):
                if team.get("licenseType") == LicenseType.PRIMARY:
                    clubs_with_primary.add(club.get("clubId"))
                    break

        # Step 6:
        # For each club without PRIMARY, set first ISHD UNKNOWN license to PRIMARY
        for club in player.get("assignedTeams", []):
            club_id = club.get("clubId")
            if club_id not in clubs_with_primary:
                # Find ISHD UNKNOWN licenses in this club
                # (LOAN and SPECIAL are already protected by being skipped in previous steps,
                # but we check licenseType == UNKNOWN here anyway)
                ishd_unknown_licenses = [
                    team
                    for team in club.get("teams", [])
                    if team.get("licenseType") == LicenseType.UNKNOWN
                    and team.get("source") == Source.ISHD
                ]

                # Set first ISHD UNKNOWN to PRIMARY
                if ishd_unknown_licenses:
                    ishd_unknown_licenses[0]["licenseType"] = LicenseType.PRIMARY
                    clubs_with_primary.add(club_id)
                    if settings.DEBUG_LEVEL > 0:
                        logger.debug(
                            f"Set ISHD UNKNOWN license to PRIMARY in club without PRIMARY for player "
                            f"{player.get('firstName')} {player.get('lastName')}"
                        )

        # Step 7: Convert UNKNOWN to SECONDARY in clubs with PRIMARY license
        # Then, convert UNKNOWN licenses in those clubs to SECONDARY
        for club in player.get("assignedTeams", []):
            if club.get("clubId") in clubs_with_primary:
                for team in club.get("teams", []):
                    if team.get("licenseType") == LicenseType.UNKNOWN:
                        team["licenseType"] = LicenseType.SECONDARY
                        if settings.DEBUG_LEVEL > 0:
                            logger.debug(
                                f"Set UNKNOWN license to SECONDARY in club with PRIMARY for player "
                                f"{player.get('firstName')} {player.get('lastName')}"
                            )

        # Step 8: Apply PRIMARY heuristic for remaining UNKNOWN licenses
        # Collect remaining UNKNOWN licenses
        unknown_licenses = []
        for club in player.get("assignedTeams", []):
            for team in club.get("teams", []):
                # PROTECT LOAN and SPECIAL licenses from being changed
                if team.get("licenseType") in [LicenseType.LOAN, LicenseType.SPECIAL]:
                    continue

                if team.get("licenseType") == LicenseType.UNKNOWN:
                    unknown_licenses.append((club, team))

        # If exactly one UNKNOWN license remains, make it PRIMARY
        if len(unknown_licenses) == 1:
            club, team = unknown_licenses[0]
            team["licenseType"] = LicenseType.PRIMARY
            if settings.DEBUG_LEVEL > 0:
                logger.debug(
                    f"Set single UNKNOWN license to PRIMARY for player {player.get('firstName')} {player.get('lastName')}"
                )

        return player

    def _classify_single_license_by_age_group(
        self, player_age_group: str, team_age_group: str, player_is_overage: bool
    ) -> LicenseType:
        """
        Classify a single license based on age group comparison.

        For players with only one license:
        - If team matches player age group -> PRIMARY
        - If team is younger (allowed by overAgeRules) -> OVERAGE
        - If team is older (allowed by secondaryRules) -> SECONDARY
        - Otherwise -> PRIMARY (fallback, will be validated later)

        Args:
          player_age_group: Player's age group (e.g., "U16")
          team_age_group: Team's age group (e.g., "U14", "U19")
          player_is_overage: Whether player has overAge flag

        Returns:
          LicenseType (PRIMARY, OVERAGE, or SECONDARY)
        """
        if not player_age_group or not team_age_group:
            return LicenseType.PRIMARY

        # Same age group -> PRIMARY
        if player_age_group == team_age_group:
            return LicenseType.PRIMARY

        # Check WKO rules for age group relationship
        if player_age_group not in self._wko_rules:
            return LicenseType.PRIMARY

        player_rule = self._wko_rules[player_age_group]

        # Check if this is an OVERAGE scenario (playing in younger age group)
        for overage_rule in player_rule.overAgeRules:
            if overage_rule.targetAgeGroup == team_age_group:
                return LicenseType.OVERAGE

        # Check if this is a SECONDARY scenario (playing in older age group)
        for secondary_rule in player_rule.secondaryRules:
            if secondary_rule.targetAgeGroup == team_age_group:
                return LicenseType.SECONDARY

        # Fallback to PRIMARY if no rule matches
        # Validation step will catch any age group violations
        return LicenseType.PRIMARY

    def _get_recommended_license_type(
        self,
        player_age_group: str,
        team_age_group: str,
        player_sex: Sex,
        player_is_overage: bool,
    ) -> LicenseType:
        """
        Determine the recommended license type for a team based on WKO rules.

        Used by get_possible_teams endpoint to suggest license types upfront.
        This is NOT the classification logic used during PATCH - that remains unchanged.

        Rules:
        - Same age group → PRIMARY
        - In secondaryRules → SECONDARY (if sex matches)
        - In overAgeRules → OVERAGE (only if player has overAge=true AND sex matches)
        - Otherwise → PRIMARY (fallback, likely INVALID)

        Args:
            player_age_group: Player's age group (e.g., "U16")
            team_age_group: Team's age group
            player_sex: Player's sex for rule matching
            player_is_overage: Whether player has overAge flag

        Returns:
            LicenseType recommendation
        """
        if not player_age_group or not team_age_group:
            return LicenseType.PRIMARY

        # Same age group → PRIMARY
        if player_age_group == team_age_group:
            return LicenseType.PRIMARY

        # Check WKO rules
        if player_age_group not in self._wko_rules:
            return LicenseType.PRIMARY

        player_rule = self._wko_rules[player_age_group]

        # Check SECONDARY rules (playing in older age groups)
        for sec_rule in player_rule.secondaryRules:
            if sec_rule.targetAgeGroup == team_age_group:
                # Check sex restriction if defined
                if not sec_rule.sex or player_sex in sec_rule.sex:
                    return LicenseType.SECONDARY

        # Check OVERAGE rules (playing in younger age groups)
        for over_rule in player_rule.overAgeRules:
            if over_rule.targetAgeGroup == team_age_group:
                # Check sex restriction if defined
                if not over_rule.sex or player_sex in over_rule.sex:
                    return LicenseType.OVERAGE

        # Fallback to PRIMARY (will likely be INVALID status)
        return LicenseType.PRIMARY

    def _classify_by_pass_suffix(self, pass_no: str) -> str:
        """
        Classify license type based on passNo suffix.

        Args:
          pass_no: The license/pass number

        Returns:
          LicenseType value
        """
        if not pass_no:
            return LicenseType.UNKNOWN

        # Normalize: strip whitespace and convert to uppercase
        pass_no_normalized = pass_no.strip().upper()

        # Check suffix
        if pass_no_normalized.endswith("F"):
            if settings.DEBUG_LEVEL > 0:
                logger.debug(f"Classified license {pass_no} as PRIMARY (F-suffix)")
            # Concept change: "F" is now PRIMARY, but the club will be marked DEVELOPMENT later
            return LicenseType.PRIMARY
        elif pass_no_normalized.endswith("A"):
            if settings.DEBUG_LEVEL > 0:
                logger.debug(f"Classified license {pass_no} as SECONDARY")
            return LicenseType.SECONDARY
        elif pass_no_normalized.endswith("L"):
            if settings.DEBUG_LEVEL > 0:
                logger.debug(f"Classified license {pass_no} as LOAN")
            return LicenseType.LOAN
        else:
            # No recognized suffix - leave as UNKNOWN
            # PRIMARY heuristic will handle single-license case
            return LicenseType.UNKNOWN

    async def bootstrap_classification_for_all_players(
        self, reset: bool = False, batch_size: int = 1000
    ) -> list[str]:
        """
        Runs the classification step for all players.

        Args:
          reset: If True, sets licenseType=UNKNOWN for all AssignedTeams before classification
          batch_size: Number of players to process in each batch

        Returns:
          List of player IDs that were modified
        """
        modified_ids = []
        total_processed = 0
        total_modified = 0

        logger.info(f"Starting bootstrap classification of all player licenses (reset={reset})...")

        # Process in batches to avoid memory issues
        cursor = self.db["players"].find({})
        batch = []

        async for player in cursor:
            batch.append(player)

            if len(batch) >= batch_size:
                # Process batch
                for p in batch:
                    total_processed += 1
                    was_modified = await self._update_player_classification_in_db(
                        p["_id"], reset=reset
                    )
                    if was_modified:
                        modified_ids.append(str(p["_id"]))
                        total_modified += 1

                logger.info(
                    f"Processed {total_processed} players, modified {total_modified} so far..."
                )
                batch = []

        # Process remaining players in final batch
        for p in batch:
            total_processed += 1
            was_modified = await self._update_player_classification_in_db(p["_id"], reset=reset)
            if was_modified:
                modified_ids.append(str(p["_id"]))
                total_modified += 1

        logger.info(
            f"Classification bootstrap complete: processed {total_processed} players, "
            f"modified {total_modified} players"
        )

        return modified_ids

    async def _update_player_classification_in_db(
        self, player_id: str, reset: bool = False
    ) -> bool:
        """
        Load a player by _id, run classification, and update in MongoDB.

        Args:
          player_id: The player's _id
          reset: If True, reset licenseType before classification

        Returns:
          True if player was modified, False otherwise
        """
        player = await self.db["players"].find_one({"_id": player_id})
        if not player:
            logger.warning(f"Player not found: {player_id}")
            return False

        # Capture original state
        original_assigned_teams = jsonable_encoder(player.get("assignedTeams", []))

        # Reset if requested
        if reset:
            for club in player.get("assignedTeams", []):
                for team in club.get("teams", []):
                    team["licenseType"] = LicenseType.UNKNOWN
                    team["status"] = LicenseStatus.UNKNOWN
                    team["invalidReasonCodes"] = []

        # Apply classification
        player = await self.classify_license_types_for_player(player)

        # Check if anything changed
        new_assigned_teams = jsonable_encoder(player.get("assignedTeams", []))
        if original_assigned_teams == new_assigned_teams:
            return False

        # Persist changes
        await self.db["players"].update_one(
            {"_id": player_id}, {"$set": {"assignedTeams": new_assigned_teams}}
        )

        logger.info(
            f"Updated license classifications for player {player_id}: "
            f"{player.get('firstName')} {player.get('lastName')}"
        )
        return True

    # ========================================================================
    # VALIDATION METHODS (only touch status and invalidReasonCodes)
    # ========================================================================

    async def validate_licenses_for_player(self, player: dict) -> dict:
        """
        Validation step: sets only assignedTeams[*].status and invalidReasonCodes
        based on WKO/BISHL rules and existing licenseType values.

        Does NOT change licenseType.
        Licenses with adminOverride=True are skipped entirely (not modified).
        Returns the modified player dict; does not persist to database.

        Args:
          player: Raw player dict from MongoDB (including assignedTeams)

        Returns:
          Modified player dict
        """
        if not player.get("assignedTeams"):
            return player

        # Step 1: Reset all license states to VALID with empty codes
        # (except those with adminOverride=True)
        self._reset_license_validation_states(player)

        # Step 2: Validate UNKNOWN license types
        self._validate_unknown_license_types(player)

        # Step 3: Validate ISHD vs BISHL conflicts (Fix 3: Order change)
        # This may invalidate ISHD licenses before primary consistency check
        self._validate_import_conflicts(player)

        # Step 4: Validate PRIMARY-like consistency
        self._validate_primary_consistency(player)

        # Step 5: Validate LOAN consistency
        self._validate_loan_consistency(player)

        # Step 6: Determine primary clubs (MAIN and DEVELOPMENT)
        # Fix 2 & 3: ensure we get all primary club IDs regardless of status
        primary_club_ids = self._get_primary_club_ids(player)

        # Step 7: Validate club consistency for SECONDARY/OVERAGE
        if primary_club_ids:
            self._validate_club_consistency(player, primary_club_ids)

        # Step 8: Validate age group violations and OVERAGE rules
        # We need to create a PlayerDB instance for age group properties
        player_obj = PlayerDB(**self._prepare_player_for_validation(player))
        self._validate_age_group_compliance(player, player_obj)

        # Step 9: Validate WKO license quotas (maxLicenses per target age group)
        self._validate_wko_license_quota(player, player_obj)

        # Step 10: Validate WKO limits (max participations)
        self._validate_wko_limits(player)

        # Step 10.5: Validate distinct age groups (max unique groups)
        self._validate_distinct_age_groups(player)

        # Step 11: Validate date sanity
        self._validate_date_sanity(player)

        # Step 12: Validate HOBBY exclusivity
        self._validate_hobby_exclusivity(player)

        # Step 13: Validate suspensions (check active suspensions per team)
        self._validate_suspensions(player)

        # Step 14: Ensure no UNKNOWN status remains
        self._enforce_no_unknown_status(player)

        return player

    def _reset_license_validation_states(self, player: dict) -> None:
        """Reset all licenses to VALID with empty invalidReasonCodes (skip adminOverride=True)"""
        if not player.get("assignedTeams"):
            return

        for club in player["assignedTeams"]:
            for team in club.get("teams", []):
                # Skip licenses with adminOverride=True
                if team.get("adminOverride"):
                    continue
                team["status"] = LicenseStatus.VALID
                team["invalidReasonCodes"] = []

    def _validate_unknown_license_types(self, player: dict) -> None:
        """Mark licenses with UNKNOWN license type as INVALID (skip adminOverride=True)"""
        if not player.get("assignedTeams"):
            return

        for club in player["assignedTeams"]:
            for team in club.get("teams", []):
                if team.get("adminOverride"):
                    continue
                if team.get("licenseType") == LicenseType.UNKNOWN:
                    team["status"] = LicenseStatus.INVALID
                    if LicenseInvalidReasonCode.UNKNOWN_LICENCE_TYPE not in team.get(
                        "invalidReasonCodes", []
                    ):
                        team.setdefault("invalidReasonCodes", []).append(
                            LicenseInvalidReasonCode.UNKNOWN_LICENCE_TYPE
                        )

    def _validate_primary_consistency(self, player: dict) -> None:
        """
        Validate PRIMARY licenses: at most one per clubType (MAIN/DEVELOPMENT).

        Sorting rule for deterministic tie-breaking:
        1. BISHL source over ISHD
        2. Earliest modifyDate
        3. Alphabetical teamAlias (fallback)
        """
        if not player.get("assignedTeams"):
            return

        # Group PRIMARY licenses by clubType
        primary_by_type: dict[ClubType, list[dict]] = {
            ClubType.MAIN: [],
            ClubType.DEVELOPMENT: [],
        }

        for club in player["assignedTeams"]:
            club_type = club.get("clubType", ClubType.MAIN)
            # Handle missing/invalid clubType
            if club_type not in [ClubType.MAIN, ClubType.DEVELOPMENT]:
                club_type = ClubType.MAIN

            for team in club.get("teams", []):
                if team.get("adminOverride"):
                    continue
                if team.get("licenseType") == LicenseType.PRIMARY:
                    # Keep track of parent club for validation
                    primary_by_type[club_type].append({"club": club, "team": team})

        for club_type, licenses in primary_by_type.items():
            if len(licenses) > 1:
                # Sort licenses to pick the "best" one to keep valid
                def sort_key(item):
                    team = item["team"]
                    source_pref = 0 if team.get("source") == Source.BISHL else 1
                    modify_date = team.get("modifyDate") or datetime.max
                    # Handle case where modifyDate might be a string (from jsonable_encoder)
                    if isinstance(modify_date, str):
                        try:
                            modify_date = datetime.fromisoformat(modify_date.replace("Z", "+00:00"))
                        except (ValueError, TypeError):
                            modify_date = datetime.max
                    return (source_pref, modify_date, team.get("teamAlias", ""))

                licenses.sort(key=sort_key)

                # Mark all but the first one as INVALID
                for item in licenses[1:]:
                    team = item["team"]
                    team["status"] = LicenseStatus.INVALID
                    if LicenseInvalidReasonCode.MULTIPLE_PRIMARY not in team.get(
                        "invalidReasonCodes", []
                    ):
                        team.setdefault("invalidReasonCodes", []).append(
                            LicenseInvalidReasonCode.MULTIPLE_PRIMARY
                        )
                    logger.debug(
                        f"Invalidated excess PRIMARY in {club_type} club: "
                        f"{item['club'].get('clubName')} / {team.get('teamName')}"
                    )

    def _validate_loan_consistency(self, player: dict) -> None:
        """
        Validate LOAN license consistency (skip adminOverride=True):
        1. Player has at most one LOAN license
        2. LOAN must be the only license within its club
        3. No other license in same age group as LOAN in other clubs
        """
        if not player.get("assignedTeams"):
            return

        loan_licenses = []
        for club in player["assignedTeams"]:
            for team in club.get("teams", []):
                if team.get("adminOverride"):
                    continue
                if team.get("licenseType") == LicenseType.LOAN:
                    loan_licenses.append(
                        {
                            "club": club,
                            "team": team,
                            "clubId": club.get("clubId"),
                            "ageGroup": team.get("teamAgeGroup"),
                        }
                    )

        if not loan_licenses:
            return

        # Rule 1: At most one LOAN license
        if len(loan_licenses) > 1:
            for loan_info in loan_licenses:
                team = loan_info["team"]
                team["status"] = LicenseStatus.INVALID
                if LicenseInvalidReasonCode.TOO_MANY_LOAN not in team.get("invalidReasonCodes", []):
                    team.setdefault("invalidReasonCodes", []).append(
                        LicenseInvalidReasonCode.TOO_MANY_LOAN
                    )
            return

        # We have exactly one LOAN license
        loan_info = loan_licenses[0]
        loan_club_id = loan_info["clubId"]
        loan_age_group = loan_info["ageGroup"]

        # Rule 2: LOAN must be the only license within its club
        for club in player["assignedTeams"]:
            if club.get("clubId") != loan_club_id:
                continue
            for team in club.get("teams", []):
                if team.get("licenseType") == LicenseType.LOAN:
                    continue
                # Any other license in the same club as LOAN is invalid
                team["status"] = LicenseStatus.INVALID
                if LicenseInvalidReasonCode.LOAN_CLUB_CONFLICT not in team.get(
                    "invalidReasonCodes", []
                ):
                    team.setdefault("invalidReasonCodes", []).append(
                        LicenseInvalidReasonCode.LOAN_CLUB_CONFLICT
                    )

        # Rule 3: LOAN cannot be in the same age group as any license in other clubs
        # When conflict exists, invalidate the LOAN (not the other license - PRIMARY takes priority)
        loan_team = loan_info["team"]
        for club in player["assignedTeams"]:
            if club.get("clubId") == loan_club_id:
                continue
            for team in club.get("teams", []):
                if team.get("adminOverride"):
                    continue
                if team.get("teamAgeGroup") == loan_age_group:
                    # Conflict found - invalidate the LOAN license, not this one
                    loan_team["status"] = LicenseStatus.INVALID
                    if LicenseInvalidReasonCode.LOAN_AGE_GROUP_CONFLICT not in loan_team.get(
                        "invalidReasonCodes", []
                    ):
                        loan_team.setdefault("invalidReasonCodes", []).append(
                            LicenseInvalidReasonCode.LOAN_AGE_GROUP_CONFLICT
                        )
                    return  # LOAN is already invalid, no need to check further

    def _validate_import_conflicts(self, player: dict) -> None:
        """
        Validate ISHD vs BISHL conflicts - ISHD never overrides BISHL (skip adminOverride=True).

        Respects clubType separation: MAIN and DEVELOPMENT are separate pools.
        BISHL PRIMARY in MAIN should NOT conflict with ISHD PRIMARY in DEVELOPMENT.
        """
        if not player.get("assignedTeams"):
            return

        # Collect BISHL licenses by (clubType, licenseType) tuple
        # This ensures MAIN and DEVELOPMENT pools are separate
        bishl_licenses_by_pool: dict[tuple[ClubType, LicenseType], set] = {}

        for club in player["assignedTeams"]:
            club_type = club.get("clubType", ClubType.MAIN)
            if club_type not in [ClubType.MAIN, ClubType.DEVELOPMENT]:
                club_type = ClubType.MAIN

            for team in club.get("teams", []):
                if team.get("adminOverride"):
                    continue
                if team.get("source") == Source.BISHL and team.get("status") == LicenseStatus.VALID:
                    license_type = team.get("licenseType")
                    pool_key = (club_type, license_type)
                    if pool_key not in bishl_licenses_by_pool:
                        bishl_licenses_by_pool[pool_key] = set()
                    bishl_licenses_by_pool[pool_key].add(team.get("teamId"))

        # Check ISHD licenses for conflicts within the SAME clubType pool
        for club in player["assignedTeams"]:
            club_type = club.get("clubType", ClubType.MAIN)
            if club_type not in [ClubType.MAIN, ClubType.DEVELOPMENT]:
                club_type = ClubType.MAIN

            for team in club.get("teams", []):
                if team.get("source") == Source.ISHD and team.get("status") == LicenseStatus.VALID:
                    license_type = team.get("licenseType")
                    pool_key = (club_type, license_type)

                    # Only conflict if BISHL license exists in the SAME clubType pool
                    if pool_key in bishl_licenses_by_pool:
                        if license_type == LicenseType.PRIMARY:
                            team["status"] = LicenseStatus.INVALID
                            if LicenseInvalidReasonCode.IMPORT_CONFLICT not in team.get(
                                "invalidReasonCodes", []
                            ):
                                team.setdefault("invalidReasonCodes", []).append(
                                    LicenseInvalidReasonCode.IMPORT_CONFLICT
                                )

    def _get_anchor_license(self, player: dict) -> tuple[dict | None, dict | None]:
        """
        Determine the anchor license (PRIMARY or fallback) for a player.
        Priority 1: Valid PRIMARY.
        Priority 2: Single valid license (existing).
        """
        if not player.get("assignedTeams"):
            return None, None

        # Priority 1: Valid PRIMARY
        for club in player["assignedTeams"]:
            for team in club.get("teams", []):
                if (
                    team.get("status") == LicenseStatus.VALID
                    and team.get("licenseType") == LicenseType.PRIMARY
                ):
                    return club, team

        # Priority 2: Single valid license
        valid_licenses = []
        for club in player["assignedTeams"]:
            for team in club.get("teams", []):
                if team.get("status") == LicenseStatus.VALID:
                    valid_licenses.append((club, team))

        if len(valid_licenses) == 1:
            return valid_licenses[0]

        return None, None

    def _get_primary_club_ids(self, player: dict) -> list[str]:
        """
        Returns a list of clubIds with any PRIMARY licenses (regardless of status).
        If no PRIMARY exists, returns a list with the 'anchor' clubId if applicable.
        """
        primary_club_ids = set()

        # Pass 1: Collect clubs with ANY PRIMARY (regardless of status)
        for club in player.get("assignedTeams", []):
            for team in club.get("teams", []):
                if team.get("adminOverride"):
                    continue
                if team.get("licenseType") == LicenseType.PRIMARY:
                    club_id = club.get("clubId")
                    if club_id:
                        primary_club_ids.add(club_id)
                    break

        if primary_club_ids:
            return sorted(primary_club_ids)

        # Pass 2: Anchor logic if no PRIMARY exists
        anchor_club, anchor_team = self._get_anchor_license(player)
        if anchor_club:
            club_id = anchor_club.get("clubId")
            return [club_id] if club_id else []

        return []

    def _validate_club_consistency(self, player: dict, primary_club_ids: list[str]) -> None:
        """
        SECONDARY and OVERAGE licenses are valid only if they belong to a club
        that also has a valid PRIMARY license (or acts as anchor).
        """
        if not player.get("assignedTeams"):
            return

        for club in player["assignedTeams"]:
            club_id = club.get("clubId")
            for team in club.get("teams", []):
                if team.get("adminOverride"):
                    continue
                if team.get("licenseType") in [LicenseType.SECONDARY, LicenseType.OVERAGE]:
                    if club_id not in primary_club_ids:
                        team["status"] = LicenseStatus.INVALID
                        if LicenseInvalidReasonCode.CONFLICTING_CLUB not in team.get(
                            "invalidReasonCodes", []
                        ):
                            team.setdefault("invalidReasonCodes", []).append(
                                LicenseInvalidReasonCode.CONFLICTING_CLUB
                            )
                        logger.debug(
                            f"Club consistency violation: {team.get('licenseType')} "
                            f"in club {club.get('clubName')} without valid PRIMARY"
                        )

    def _validate_age_group_compliance(self, player: dict, player_obj: PlayerDB) -> None:
        """
        Validate age group compliance and OVERAGE rules.

        Uses two-pass approach:
        1. First pass: Validate PRIMARY licenses only
        2. Second pass: Validate SECONDARY, OVERAGE, and LOAN licenses

        This ensures PRIMARY is validated first and other license types are
        invalidated before the PRIMARY when there are conflicts.

        Special handling for anchor-only scenarios:
        - When player has only one license (no PRIMARY), the single OVERAGE/SECONDARY
          license acts as anchor and doesn't require the overAge flag.
        """
        if not player.get("assignedTeams"):
            return

        player_age_group = player_obj.ageGroup
        player_is_overage = player_obj.overAge

        # Detect anchor-only scenario (single license acting as anchor)
        anchor_club, anchor_team = self._get_anchor_license(player)
        primary_club_ids = self._get_primary_club_ids(player)
        is_anchor_only = (
            anchor_team is not None
            and anchor_team.get("clubId") in primary_club_ids
            and anchor_team.get("licenseType") != LicenseType.PRIMARY
        )

        # PASS 1: Validate PRIMARY licenses first
        for club in player["assignedTeams"]:
            for team in club.get("teams", []):
                if team.get("adminOverride"):
                    continue
                if team.get("status") != LicenseStatus.VALID:
                    continue

                license_type = team.get("licenseType")
                if license_type != LicenseType.PRIMARY:
                    continue

                team_age_group = team.get("teamAgeGroup")
                if not self._is_age_group_compatible(player_age_group, team_age_group):
                    team["status"] = LicenseStatus.INVALID
                    if LicenseInvalidReasonCode.AGE_GROUP_VIOLATION not in team.get(
                        "invalidReasonCodes", []
                    ):
                        team.setdefault("invalidReasonCodes", []).append(
                            LicenseInvalidReasonCode.AGE_GROUP_VIOLATION
                        )

        # PASS 2: Validate SECONDARY, OVERAGE, and LOAN licenses
        for club in player["assignedTeams"]:
            for team in club.get("teams", []):
                if team.get("adminOverride"):
                    continue
                if team.get("status") != LicenseStatus.VALID:
                    continue

                team_age_group = team.get("teamAgeGroup")
                license_type = team.get("licenseType")

                # Check if this team is the anchor license
                is_this_anchor = is_anchor_only and team is anchor_team

                # Handle OVERAGE licenses
                if license_type == LicenseType.OVERAGE:
                    if not self._is_overage_allowed(
                        player_age_group,
                        team_age_group,
                        player_is_overage,
                        is_anchor_license=is_this_anchor,
                    ):
                        team["status"] = LicenseStatus.INVALID
                        if LicenseInvalidReasonCode.OVERAGE_NOT_ALLOWED not in team.get(
                            "invalidReasonCodes", []
                        ):
                            team.setdefault("invalidReasonCodes", []).append(
                                LicenseInvalidReasonCode.OVERAGE_NOT_ALLOWED
                            )

                # Handle SECONDARY licenses
                elif license_type == LicenseType.SECONDARY:
                    if not self._is_secondary_allowed(player_age_group, team_age_group):
                        team["status"] = LicenseStatus.INVALID
                        if LicenseInvalidReasonCode.AGE_GROUP_VIOLATION not in team.get(
                            "invalidReasonCodes", []
                        ):
                            team.setdefault("invalidReasonCodes", []).append(
                                LicenseInvalidReasonCode.AGE_GROUP_VIOLATION
                            )

                # Handle LOAN licenses (similar to SECONDARY rules)
                elif license_type == LicenseType.LOAN:
                    if not self._is_secondary_allowed(player_age_group, team_age_group):
                        team["status"] = LicenseStatus.INVALID
                        if LicenseInvalidReasonCode.AGE_GROUP_VIOLATION not in team.get(
                            "invalidReasonCodes", []
                        ):
                            team.setdefault("invalidReasonCodes", []).append(
                                LicenseInvalidReasonCode.AGE_GROUP_VIOLATION
                            )

    def _is_overage_allowed(
        self,
        player_age_group: str,
        team_age_group: str,
        player_is_overage: bool,
        is_anchor_license: bool = False,
    ) -> bool:
        """
        Check if OVERAGE license is allowed based on WKO rules.

        Args:
          player_age_group: The player's age group
          team_age_group: The team's age group (target)
          player_is_overage: Whether player has overAge flag
          is_anchor_license: If True, this is a single-license anchor scenario
                             where overAge flag is not required
        """
        # For anchor scenarios (single license), we don't require the overAge flag
        # The player may be in a club without a team in their main age group
        if not is_anchor_license and not player_is_overage:
            return False

        if player_age_group not in self._wko_rules:
            return False

        player_rule = self._wko_rules[player_age_group]
        return any(
            over_age_rule.targetAgeGroup == team_age_group
            for over_age_rule in player_rule.overAgeRules
        )

    def _is_secondary_allowed(self, player_age_group: str, team_age_group: str) -> bool:
        """Check if SECONDARY license in this age group is allowed"""
        if player_age_group not in self._wko_rules:
            return False

        player_rule = self._wko_rules[player_age_group]

        # SECONDARY can be in same age group or allowed play-up groups
        if team_age_group == player_age_group:
            return True

        return any(
            secondary_rule.targetAgeGroup == team_age_group
            for secondary_rule in player_rule.secondaryRules
        )

    def _is_age_group_compatible(self, player_age_group: str, team_age_group: str) -> bool:
        """Check if player can play in the team's age group"""
        if player_age_group not in self._wko_rules or team_age_group not in self._wko_rules:
            return True  # Unknown age groups - allow for now

        player_rule = self._wko_rules[player_age_group]
        team_rule = self._wko_rules[team_age_group]

        # Same age group is always OK
        if player_age_group == team_age_group:
            return True

        # Playing up (younger player in older team) - check if team allows this age group
        if team_rule.sortOrder < player_rule.sortOrder:
            allowed = any(
                secondary_rule.targetAgeGroup == team_age_group
                for secondary_rule in player_rule.secondaryRules
            )
            logger.debug(
                f"{player_age_group} is {'allowed' if allowed else 'NOT allowed'} to play up in {team_age_group}"
            )
            return allowed

        # Playing down (older player in younger team) - not allowed without OVERAGE
        return False

    def _count_all_licenses_by_age_group(self, player: dict) -> dict[str, list[dict]]:
        """
        Count ALL valid licenses by target age group (regardless of license type).

        Args:
          player: Player dict with assignedTeams

        Returns:
          Dict mapping teamAgeGroup -> list of {club, team} entries with valid licenses
        """
        result: dict[str, list[dict]] = {}

        if not player.get("assignedTeams"):
            return result

        for club in player["assignedTeams"]:
            for team in club.get("teams", []):
                if team.get("status") == LicenseStatus.VALID:
                    target_age_group = team.get("teamAgeGroup")
                    if target_age_group not in result:
                        result[target_age_group] = []
                    result[target_age_group].append({"club": club, "team": team})

        return result

    def _get_max_licenses_for_age_group(
        self, player_age_group: str, target_age_group: str, player_sex: Sex
    ) -> int | None:
        """
        Get the maximum licenses allowed for a target age group by merging
        secondary and overage rules.

        Takes the minimum (most restrictive) limit when multiple rules apply.
        Returns None if no limit is defined (unlimited).

        Args:
          player_age_group: The player's own age group
          target_age_group: The age group to check limits for
          player_sex: The player's sex for filtering rules

        Returns:
          The max licenses allowed, or None if unlimited
        """
        if player_age_group not in self._wko_rules:
            return None

        player_rule = self._wko_rules[player_age_group]
        limits: list[int] = []

        # Check secondary rules
        for sec_rule in player_rule.secondaryRules:
            if sec_rule.targetAgeGroup == target_age_group:
                if player_sex in sec_rule.sex or not sec_rule.sex:
                    if sec_rule.maxLicenses is not None:
                        limits.append(sec_rule.maxLicenses)

        # Check overage rules
        for ovr_rule in player_rule.overAgeRules:
            if ovr_rule.targetAgeGroup == target_age_group:
                if player_sex in ovr_rule.sex or not ovr_rule.sex:
                    if ovr_rule.maxLicenses is not None:
                        limits.append(ovr_rule.maxLicenses)

        # Return the minimum (most restrictive) limit, or None if no limits
        return min(limits) if limits else None

    def _validate_wko_license_quota(self, player: dict, player_obj: PlayerDB) -> None:
        """
        Validate that player doesn't exceed maxLicenses for each target age group (skip adminOverride=True).

        maxLicenses from secondaryRules/overAgeRules defines the total number of
        licenses (of any type) allowed in that target age group. For example, if
        U16's secondaryRule for HERREN has maxLicenses=1, a U16 player can have
        at most 1 license total in HERREN teams.

        This runs after age group compliance to ensure only structurally valid
        licenses are subject to quota checks.
        """
        if not player.get("assignedTeams"):
            return

        player_age_group = player_obj.ageGroup
        player_sex = player_obj.sex

        if player_age_group not in self._wko_rules:
            return

        # Count all valid licenses by target age group
        licenses_by_age_group = self._count_all_licenses_by_age_group(player)

        for target_age_group, licenses in licenses_by_age_group.items():
            # Skip player's own age group (no quota applies to primary age group)
            if target_age_group == player_age_group:
                continue

            # Get the maximum allowed for this target age group
            max_licenses = self._get_max_licenses_for_age_group(
                player_age_group, target_age_group, player_sex
            )

            if max_licenses is not None and len(licenses) > max_licenses:
                # Mark excess licenses as invalid (keep first max_licenses)
                for entry in licenses[max_licenses:]:
                    team = entry["team"]
                    team["status"] = LicenseStatus.INVALID
                    if LicenseInvalidReasonCode.EXCEEDS_WKO_LIMIT not in team.get(
                        "invalidReasonCodes", []
                    ):
                        team.setdefault("invalidReasonCodes", []).append(
                            LicenseInvalidReasonCode.EXCEEDS_WKO_LIMIT
                        )
                    logger.debug(
                        f"Player {player_obj.firstName} {player_obj.lastName}: "
                        f"licenses in {target_age_group} exceeds quota "
                        f"({len(licenses)} > {max_licenses})"
                    )

    def _validate_wko_limits(self, player: dict) -> None:
        """
        Validate WKO limits on unique age group participations (maxTotalAgeClasses).

        This validation ensures a player does not participate in more unique age
        classes than allowed by WKO rules (e.g., max 2 unique age groups).
        """
        if not player.get("assignedTeams"):
            return

        # 1. Get player details
        player_obj = PlayerDB(**self._prepare_player_for_validation(player))
        player_age_group = player_obj.ageGroup
        player_sex = player_obj.sex

        if player_age_group not in self._wko_rules:
            return

        # 2. Get max unique age groups (maxTotalAgeClasses)
        player_rule = self._wko_rules[player_age_group]
        max_groups = 2  # Default
        max_participations_dict = player_rule.maxTotalAgeClasses or {}

        if player_sex in max_participations_dict:
            max_groups = max_participations_dict[player_sex]
            if max_groups is None:
                return  # No limit

        # 3. Collect all licenses that count towards age class limit
        # We count licenses that are VALID OR those that are INVALID only because of MULTIPLE_PRIMARY
        # (Fix: Don't let MULTIPLE_PRIMARY status mask the fact that an age group is being used)
        licenses_by_group: dict[str, list[dict]] = {}

        for club in player["assignedTeams"]:
            for team in club.get("teams", []):
                if team.get("adminOverride"):
                    continue

                reason_codes = team.get("invalidReasonCodes", [])
                is_structurally_valid = team.get("status") == LicenseStatus.VALID or (
                    team.get("status") == LicenseStatus.INVALID
                    and LicenseInvalidReasonCode.MULTIPLE_PRIMARY in reason_codes
                    and len(reason_codes) == 1
                )

                if is_structurally_valid:
                    age_group = team.get("teamAgeGroup")
                    if age_group:
                        if age_group not in licenses_by_group:
                            licenses_by_group[age_group] = []
                        licenses_by_group[age_group].append(team)

        # 4. Check unique age groups limit
        unique_age_groups = list(licenses_by_group.keys())
        if len(unique_age_groups) > max_groups:
            # Sort groups to prioritize: PRIMARY-first, then wko sortOrder (older first)
            def group_priority(group_name):
                teams = licenses_by_group[group_name]
                has_primary = any(t.get("licenseType") == LicenseType.PRIMARY for t in teams)
                # Use simple fallback if rule missing
                sort_order = (
                    self._wko_rules[group_name].sortOrder if group_name in self._wko_rules else 99
                )
                return (0 if has_primary else 1, sort_order)

            unique_age_groups.sort(key=group_priority)

            # Invalidate excess age groups
            excess_groups = unique_age_groups[max_groups:]
            for group_name in excess_groups:
                for team in licenses_by_group[group_name]:
                    # Don't overwrite existing MULTIPLE_PRIMARY if it's already there
                    if team.get("status") == LicenseStatus.VALID:
                        team["status"] = LicenseStatus.INVALID
                        if LicenseInvalidReasonCode.EXCEEDS_WKO_LIMIT not in team.get(
                            "invalidReasonCodes", []
                        ):
                            team.setdefault("invalidReasonCodes", []).append(
                                LicenseInvalidReasonCode.EXCEEDS_WKO_LIMIT
                            )

    def _validate_distinct_age_groups(self, player: dict) -> None:
        """Legacy method - functionality merged into _validate_wko_limits"""
        pass

    def _validate_date_sanity(self, player: dict) -> None:
        """Validate date sanity (validFrom <= validTo)"""
        if not player.get("assignedTeams"):
            return

        for club in player["assignedTeams"]:
            for team in club.get("teams", []):
                valid_from = team.get("validFrom")
                valid_to = team.get("validTo")
                if valid_from and valid_to:
                    if valid_from > valid_to:
                        team["status"] = LicenseStatus.INVALID
                        if LicenseInvalidReasonCode.IMPORT_CONFLICT not in team.get(
                            "invalidReasonCodes", []
                        ):
                            team.setdefault("invalidReasonCodes", []).append(
                                LicenseInvalidReasonCode.IMPORT_CONFLICT
                            )

    def _validate_hobby_exclusivity(self, player: dict) -> None:
        """
        Validate that if a HOBBY team exists, no COMPETITIVE teams can exist.

        HOBBY teams are mutually exclusive with COMPETITIVE teams across ALL club types.
        """
        if not player.get("assignedTeams"):
            return

        # First, check if player has any HOBBY teams
        has_hobby = False
        hobby_teams = []

        for club in player["assignedTeams"]:
            for team in club.get("teams", []):
                if team.get("adminOverride"):
                    continue
                if team.get("teamType") == "HOBBY":
                    has_hobby = True
                    hobby_teams.append((club, team))

        if not has_hobby:
            return

        # If HOBBY exists, check for conflicting COMPETITIVE teams
        # COMPETITIVE is any team that is NOT HOBBY
        for club in player["assignedTeams"]:
            for team in club.get("teams", []):
                if team.get("adminOverride"):
                    continue
                team_type = team.get("teamType")

                # If this is a COMPETITIVE team, mark both HOBBY and COMPETITIVE as invalid
                if team_type == "COMPETITIVE":
                    team["status"] = LicenseStatus.INVALID
                    if LicenseInvalidReasonCode.HOBBY_PLAYER_CONFLICT not in team.get(
                        "invalidReasonCodes", []
                    ):
                        team.setdefault("invalidReasonCodes", []).append(
                            LicenseInvalidReasonCode.HOBBY_PLAYER_CONFLICT
                        )

                    # Also mark all HOBBY teams as invalid
                    for _, hobby_team in hobby_teams:
                        hobby_team["status"] = LicenseStatus.INVALID
                        if LicenseInvalidReasonCode.HOBBY_PLAYER_CONFLICT not in hobby_team.get(
                            "invalidReasonCodes", []
                        ):
                            hobby_team.setdefault("invalidReasonCodes", []).append(
                                LicenseInvalidReasonCode.HOBBY_PLAYER_CONFLICT
                            )

    def _validate_suspensions(self, player: dict) -> None:
        """
        Validate that player is not actively suspended for any team.

        For each active suspension:
        - If globalLock=True: invalidate ALL teams
        - If globalLock=False: only invalidate teams whose teamId is in suspension.teamIds

        Suspensions with adminOverride on the team license are skipped.
        """
        if not player.get("assignedTeams"):
            return

        suspensions = player.get("suspensions") or []
        if not suspensions:
            return

        # Find active suspensions
        now = datetime.now()
        active_suspensions = []

        for susp in suspensions:
            # Check if suspension is active (same logic as Suspension.active property)
            start_date = susp.get("startDate")
            end_date = susp.get("endDate")

            # Convert string dates if needed
            if isinstance(start_date, str):
                try:
                    start_date = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    start_date = None
            if isinstance(end_date, str):
                try:
                    end_date = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    end_date = None

            # Check if active: now >= startDate AND (endDate is None OR now <= endDate)
            if start_date and now < start_date:
                continue  # Not yet started
            if end_date and now > end_date:
                continue  # Already ended

            active_suspensions.append(susp)

        if not active_suspensions:
            return

        # Apply suspensions to teams
        for club in player["assignedTeams"]:
            for team in club.get("teams", []):
                if team.get("adminOverride"):
                    continue

                team_id = team.get("teamId")

                for susp in active_suspensions:
                    global_lock = susp.get("globalLock")
                    suspension_team_ids = susp.get("teamIds") or []

                    is_suspended = False
                    if global_lock is True:
                        is_suspended = True
                    elif global_lock is False and suspension_team_ids:
                        is_suspended = team_id and team_id in suspension_team_ids
                    elif global_lock is None:
                        is_suspended = True

                    if is_suspended:
                        team["status"] = LicenseStatus.INVALID
                        if LicenseInvalidReasonCode.SUSPENDED not in team.get(
                            "invalidReasonCodes", []
                        ):
                            team.setdefault("invalidReasonCodes", []).append(
                                LicenseInvalidReasonCode.SUSPENDED
                            )
                        logger.debug(
                            f"Player {player.get('firstName')} {player.get('lastName')} "
                            f"suspended for team {team.get('teamName')}: {susp.get('reason')} "
                            f"(globalLock={global_lock}, teamIds={suspension_team_ids})"
                        )
                        break  # One suspension is enough to invalidate

    def _enforce_no_unknown_status(self, player: dict) -> None:
        """
        Ensure no license has status=UNKNOWN after validation.

        For any license still UNKNOWN:
        - If licenseType is UNKNOWN: mark as INVALID with UNKNOWN_LICENCE_TYPE
        - Otherwise: mark as VALID (nothing spoke against it structurally)
        """
        if not player.get("assignedTeams"):
            return

        for club in player["assignedTeams"]:
            for team in club.get("teams", []):
                if team.get("status") == LicenseStatus.UNKNOWN:
                    if team.get("licenseType") == LicenseType.UNKNOWN:
                        # Cannot classify license type, mark as invalid
                        team["status"] = LicenseStatus.INVALID
                        if LicenseInvalidReasonCode.UNKNOWN_LICENCE_TYPE not in team.get(
                            "invalidReasonCodes", []
                        ):
                            team.setdefault("invalidReasonCodes", []).append(
                                LicenseInvalidReasonCode.UNKNOWN_LICENCE_TYPE
                            )
                    else:
                        # License type is known and no structural issues found
                        team["status"] = LicenseStatus.VALID

    async def bootstrap_validation_for_all_players(
        self, reset: bool = False, batch_size: int = 1000
    ) -> list[str]:
        """
        Runs the validation step for all players.

        Args:
          reset: If True, sets status=UNKNOWN and invalidReasonCodes=[] before validation
          batch_size: Number of players to process in each batch

        Returns:
          List of player IDs that were modified
        """
        modified_ids = []
        total_processed = 0
        total_modified = 0

        logger.info(f"Starting bootstrap validation of all player licenses (reset={reset})...")

        # Process in batches to avoid memory issues
        cursor = self.db["players"].find({})
        batch = []

        async for player in cursor:
            batch.append(player)

            if len(batch) >= batch_size:
                # Process batch
                for p in batch:
                    total_processed += 1
                    was_modified = await self._update_player_validation_in_db(p["_id"], reset=reset)
                    if was_modified:
                        modified_ids.append(str(p["_id"]))
                        total_modified += 1

                logger.info(
                    f"Processed {total_processed} players, modified {total_modified} so far..."
                )
                batch = []

        # Process remaining players in final batch
        for p in batch:
            total_processed += 1
            was_modified = await self._update_player_validation_in_db(p["_id"], reset=reset)
            if was_modified:
                modified_ids.append(str(p["_id"]))
                total_modified += 1

        logger.info(
            f"Validation bootstrap complete: processed {total_processed} players, "
            f"modified {total_modified} players"
        )

        return modified_ids

    async def _update_player_validation_in_db(self, player_id: str, reset: bool = False) -> bool:
        """
        Load a player by _id, run validation, and update in MongoDB.

        Args:
          player_id: The player's _id
          reset: If True, reset status and invalidReasonCodes before validation

        Returns:
          True if player was modified, False otherwise
        """
        player = await self.db["players"].find_one({"_id": player_id})
        if not player:
            logger.warning(f"Player not found: {player_id}")
            return False

        # Capture original state
        original_assigned_teams = jsonable_encoder(player.get("assignedTeams", []))

        # Reset if requested
        if reset:
            for club in player.get("assignedTeams", []):
                for team in club.get("teams", []):
                    team["status"] = LicenseStatus.UNKNOWN
                    team["invalidReasonCodes"] = []

        # Apply validation
        player = await self.validate_licenses_for_player(player)

        # Check if anything changed
        new_assigned_teams = jsonable_encoder(player.get("assignedTeams", []))
        if original_assigned_teams == new_assigned_teams:
            return False

        # Persist changes
        await self.db["players"].update_one(
            {"_id": player_id}, {"$set": {"assignedTeams": new_assigned_teams}}
        )

        logger.info(
            f"Updated license validations for player {player_id}: "
            f"{player.get('firstName')} {player.get('lastName')}"
        )
        return True

    async def update_player_validation_in_db(
        self, player_id: str, reset: bool = False
    ) -> dict | None:
        """
        Public method to update player validation in database.

        Loads player, runs license validation (including suspension checks),
        persists changes, and returns the updated player document.

        Args:
            player_id: The player's _id
            reset: If True, reset status and invalidReasonCodes before validation

        Returns:
            Updated player dict if found, None if player not found
        """
        was_modified = await self._update_player_validation_in_db(player_id, reset=reset)

        # Return the updated player document
        player = await self.db["players"].find_one({"_id": player_id})
        if player:
            logger.info(f"Validated player {player_id}, modified={was_modified}")
        return player

    # ========================================================================
    # ORCHESTRATION METHODS
    # ========================================================================

    async def bootstrap_all_players(
        self,
        reset_classification: bool = False,
        reset_validation: bool = False,
        batch_size: int = 1000,
    ) -> dict:
        """
        Convenience orchestration: runs both classification and validation for all players.

        Args:
          reset_classification: If True, reset licenseType before classification
          reset_validation: If True, reset status/invalidReasonCodes before validation
          batch_size: Number of players to process in each batch

        Returns:
          Summary dict with counts of modified players
        """
        logger.info("Starting full bootstrap (classification + validation)...")

        # Step 1: Classification
        classification_modified = await self.bootstrap_classification_for_all_players(
            reset=reset_classification, batch_size=batch_size
        )

        # Step 2: Validation
        validation_modified = await self.bootstrap_validation_for_all_players(
            reset=reset_validation, batch_size=batch_size
        )

        # Get statistics
        stats = await self.get_classification_stats()

        logger.info("Full bootstrap complete")

        return {
            "classification_modified_count": len(classification_modified),
            "classification_modified_ids": classification_modified[:100],  # First 100 IDs
            "validation_modified_count": len(validation_modified),
            "validation_modified_ids": validation_modified[:100],  # First 100 IDs
            "stats": stats,
        }

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    async def apply_heuristics_for_imported_player(self, player_doc: dict) -> dict:
        """
        Hook for process_ishd_data: apply classification to a player doc
        right after ISHD import, before persisting to MongoDB.

        Args:
          player_doc: In-memory player document from ISHD import

        Returns:
          Modified player document
        """
        return await self.classify_license_types_for_player(player_doc)

    async def get_classification_stats(self) -> dict:
        """
        Get statistics about license classifications across all players.

        Returns:
          Dictionary with classification statistics
        """
        stats = {
            "total_licenses": 0,
            "by_type": {
                LicenseType.PRIMARY: 0,
                LicenseType.SECONDARY: 0,
                LicenseType.OVERAGE: 0,
                LicenseType.LOAN: 0,
                LicenseType.SPECIAL: 0,
                LicenseType.UNKNOWN: 0,
            },
            "by_status": {
                LicenseStatus.VALID: 0,
                LicenseStatus.INVALID: 0,
                LicenseStatus.UNKNOWN: 0,
            },
        }

        async for player in self.db["players"].find({}):
            for club in player.get("assignedTeams", []):
                for team in club.get("teams", []):
                    stats["total_licenses"] += 1

                    license_type = team.get("licenseType", LicenseType.UNKNOWN)
                    stats["by_type"][license_type] = stats["by_type"].get(license_type, 0) + 1

                    status = team.get("status", LicenseStatus.UNKNOWN)
                    stats["by_status"][status] = stats["by_status"].get(status, 0) + 1

        return stats

    async def get_validation_stats(self) -> dict:
        """
        Get statistics about license validation across all players.

        Returns:
          Dictionary with validation statistics including counts by status
          and by invalid reason codes
        """
        stats = {
            "total_licenses": 0,
            "by_status": {
                LicenseStatus.VALID: 0,
                LicenseStatus.INVALID: 0,
            },
            "by_invalidReasonCodes": {},
        }

        async for player in self.db["players"].find({}):
            for club in player.get("assignedTeams", []):
                for team in club.get("teams", []):
                    stats["total_licenses"] += 1

                    # Count by status
                    status = team.get("status", LicenseStatus.VALID)
                    if status in stats["by_status"]:
                        stats["by_status"][status] += 1
                    else:
                        stats["by_status"][status] = 1

                    # Count by invalid reason codes
                    if status == LicenseStatus.INVALID:
                        reason_codes = team.get("invalidReasonCodes", [])
                        for code in reason_codes:
                            stats["by_invalidReasonCodes"][code] = (
                                stats["by_invalidReasonCodes"].get(code, 0) + 1
                            )

        return stats

    async def get_possible_teams_for_player(
        self, player_id: str, club_id: str = None
    ) -> list[dict]:
        """
        Get a list of teams that a player could potentially join,
        with recommendations and WKO compliance status.
        """
        # 1. Fetch player
        player = await self.db["players"].find_one({"_id": player_id})
        if not player:
            return []

        # 2. Prepare player object for age group and sex properties
        player_obj = PlayerDB(**self._prepare_player_for_validation(player))
        player_age = player_obj.ageGroup
        player_sex = player_obj.sex

        # 3. Get target club teams
        # If club_id is provided, only look at that club. Otherwise all clubs.
        club_query = {"_id": club_id} if club_id else {}
        clubs_cursor = self.db["clubs"].find(club_query)
        clubs = await clubs_cursor.to_list(length=None)

        # 4. Identify assigned teams
        assigned_team_ids = set()
        for club_assignment in player.get("assignedTeams", []):
            for team_assignment in club_assignment.get("teams", []):
                assigned_team_ids.add(team_assignment["teamId"])

        results = []
        for club in clubs:
            for team in club.get("teams", []):
                team_id = team["_id"]
                team_age_group = team.get("ageGroup")

                # Recommendation logic based on WKO rules
                rec_type = self._get_recommended_license_type(
                    player_age, team_age_group, player_sex, player_obj.overAge
                )

                # WKO compliance check
                is_allowed, max_lic, requires_admin = self._is_team_allowed(
                    player_age, team_age_group, player_sex, player_obj.overAge
                )

                # Special case: PRIMARY (player's own age group) is always allowed
                if team_age_group == player_age:
                    is_allowed = True

                status = "VALID" if is_allowed else "INVALID"
                reason_detail = "allowed" if is_allowed else "not allowed"

                # 6. Build result
                results.append(
                    {
                        "teamId": team_id,
                        "teamAlias": team.get("alias"),
                        "teamName": team.get("name"),
                        "teamAgeGroup": team_age_group,
                        "recommendedType": rec_type.value,
                        "status": status,
                        "reason": f"{rec_type.value} ({reason_detail})",
                        "maxLicenses": max_lic,
                        "requiresAdmin": requires_admin,
                        "clubId": club["_id"],
                        "clubName": club["name"],
                        "assigned": team_id in assigned_team_ids,
                    }
                )

        return results

    # ========================================================================
    # ISHD SYNC METHODS
    # ========================================================================

    async def process_ishd_sync(self, mode: str = "live", run: int = 1) -> dict[str, Any]:
        """
        Process ISHD player data synchronization.

        Migrated from routers/players.py process_ishd_data endpoint.
        Fetches player data from ISHD API and synchronizes with local database.

        Args:
          mode: Sync mode - "live" (full sync), "test" (use JSON files), "dry" (simulate only)
          run: Run number for test mode (determines which JSON files to use)

        Returns:
          Dict containing logs, stats, and ishdLog data
        """
        log_lines: list[str] = []
        stats = {
            "added_players": 0,
            "updated_teams": 0,
            "updated_passno": 0,
            "deleted": 0,
            "invalid_new": 0,
        }

        # Get ISHD API credentials from environment
        ISHD_API_URL = settings.ISHD_API_URL
        ISHD_API_USER = settings.ISHD_API_USER
        ISHD_API_PASS = settings.ISHD_API_PASS

        # Helper class to store club/team info for processing
        class IshdTeams:
            def __init__(self, club_id, club_ishd_id, club_name, club_alias, teams):
                self.club_id = club_id
                self.club_ishd_id = club_ishd_id
                self.club_name = club_name
                self.club_alias = club_alias
                self.teams = teams

        ishd_teams = []
        create_date = datetime.now().replace(microsecond=0)

        # Get all active clubs with teams from database
        async for club in self.db["clubs"].aggregate(
            [
                {
                    "$match": {
                        "active": True,
                        "teams": {"$ne": []},
                    }
                },
                {"$project": {"ishdId": 1, "_id": 1, "name": 1, "alias": 1, "teams": 1}},
                {"$sort": {"name": 1}},
            ]
        ):
            ishd_teams.append(
                IshdTeams(
                    club["_id"], club.get("ishdId"), club["name"], club["alias"], club["teams"]
                )
            )

        # Get existing players from database for comparison
        existing_players = []
        async for player in self.db["players"].find(
            {},
            {
                "firstName": 1,
                "lastName": 1,
                "birthdate": 1,
                "assignedTeams": 1,
                "managedByISHD": 1,
            },
        ):
            existing_players.append(player)

        # Setup HTTP headers for ISHD API
        base_url_str = str(ISHD_API_URL)
        headers = {
            "Authorization": f"Basic {base64.b64encode(f'{ISHD_API_USER}:{ISHD_API_PASS}'.encode()).decode('utf-8')}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

        ishd_data = []
        timeout = aiohttp.ClientTimeout(total=60)

        # Create SSL context with certificate verification
        ssl_context = ssl.create_default_context()
        connector = aiohttp.TCPConnector(ssl=ssl_context, limit=10, limit_per_host=5)

        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            # Initialize ISHD log structure
            ishd_log_base = IshdLogBase(
                processDate=datetime.now().replace(microsecond=0),
                clubs=[],
            )

            # Process each club
            for club in ishd_teams:
                # Skip clubs without ISHD ID
                if club.club_ishd_id is None:
                    log_line = f"Skipping club {club.club_name} (no ISHD ID)"
                    logger.info(log_line)
                    log_lines.append(log_line)
                    continue

                log_line = f"Processing club {club.club_name} (IshdId: {club.club_ishd_id})"
                logger.info(log_line)
                log_lines.append(log_line)

                ishd_log_club = IshdLogClub(
                    clubName=club.club_name,
                    ishdId=club.club_ishd_id,
                    teams=[],
                )

                # Process each team in the club
                processed_team_ids = set()
                for team in club.teams:
                    if not team["ishdId"] or team["ishdId"] in processed_team_ids:
                        continue
                    processed_team_ids.add(team["ishdId"])

                    club_ishd_id_str = urllib.parse.quote(str(club.club_ishd_id))
                    team_id_str = urllib.parse.quote(str(team["ishdId"]))
                    api_url = f"{base_url_str}/clubs/{club_ishd_id_str}/teams/{team_id_str}.json"

                    ishd_log_team = IshdLogTeam(
                        teamIshdId=team["ishdId"],
                        url=api_url,
                        players=[],
                    )

                    # Fetch team data from ISHD API or test file
                    data = {}
                    if mode == "test":
                        test_file = f"ishd_test{run}_{club_ishd_id_str}_{team['alias']}.json"
                        if os.path.exists(test_file):
                            logger.debug(
                                f"Processing team {club.club_name} / {team['ishdId']} / {test_file}"
                            )
                            with open(test_file) as file:
                                data = json.load(file)
                        else:
                            logger.warning(f"File {test_file} does not exist. Skipping...")
                    else:
                        # Live or Dry mode - fetch from API
                        logger.info(
                            f"Fetching team data: {club.club_name} / {team['ishdId']} (URL: {api_url})"
                        )

                        async with session.get(api_url, headers=headers) as response:
                            if response.status == 200:
                                data = await response.json()
                                logger.debug(
                                    f"Successfully fetched {len(data.get('players', []))} players from {api_url}"
                                )
                            elif response.status == 404:
                                logger.error(f"API URL {api_url} returned a 404 status code.")
                            else:
                                try:
                                    error_detail = await response.json()
                                except json.JSONDecodeError:
                                    try:
                                        error_detail = await response.text()
                                    except Exception:
                                        error_detail = "Unable to parse error response"

                                if response.status in [525, 526, 530]:
                                    error_detail = f"SSL/TLS error - Status {response.status}. The server may have SSL certificate issues."

                                raise ExternalServiceException(
                                    service_name="ISHD_API",
                                    message=f"Failed to fetch team data (status {response.status})",
                                    details={
                                        "url": api_url,
                                        "status_code": response.status,
                                        "error_detail": error_detail,
                                    },
                                )

                    if data:
                        # Process each player in the team data
                        for player in data["players"]:
                            # Validate player birthdate
                            try:
                                birthdate = datetime.strptime(player["date_of_birth"], "%Y-%m-%d")
                            except ValueError:
                                log_line = (
                                    f"ERROR: Invalid date format for player "
                                    f"{player['first_name']} {player['last_name']} "
                                    f"from club {club.club_name} and team {team['name']}"
                                )
                                logger.info(log_line)
                                log_lines.append(log_line)
                                continue

                            # Check if player exists and has managedByISHD=false (skip if so)
                            existing_player_check = None
                            for existing_player in existing_players:
                                if (
                                    existing_player["firstName"] == player["first_name"]
                                    and existing_player["lastName"] == player["last_name"]
                                    and datetime.strftime(existing_player["birthdate"], "%Y-%m-%d")
                                    == player["date_of_birth"]
                                ):
                                    existing_player_check = existing_player
                                    break

                            if (
                                existing_player_check
                                and existing_player_check.get("managedByISHD", True) is False
                            ):
                                log_line = f"Skipping player (managedByISHD=false): {player['first_name']} {player['last_name']} {player['date_of_birth']}"
                                logger.info(log_line)
                                log_lines.append(log_line)
                                continue

                            ishd_log_player = IshdLogPlayer(
                                firstName=player["first_name"],
                                lastName=player["last_name"],
                                birthdate=datetime.strptime(player["date_of_birth"], "%Y-%m-%d"),
                            )

                            # NEW: Get teamType from database team document
                            team_doc = await self.db["teams"].find_one({"_id": team["_id"]})
                            team_type = (
                                team_doc.get("teamType", TeamType.COMPETITIVE)
                                if team_doc
                                else TeamType.COMPETITIVE
                            )

                            # Build assigned team object with source=ISHD
                            assigned_team = AssignedTeams(
                                teamId=team["_id"],
                                teamName=team["name"],
                                teamAlias=team["alias"],
                                teamType=team_type,
                                teamAgeGroup=team["ageGroup"],
                                teamIshdId=team["ishdId"],
                                passNo=player["license_number"],
                                source=Source.ISHD,
                                modifyDate=datetime.strptime(
                                    player["last_modification"], "%Y-%m-%d %H:%M:%S"
                                ),
                            )
                            assigned_club = AssignedClubs(
                                clubId=club.club_id,
                                clubName=club.club_name,
                                clubAlias=club.club_alias,
                                clubIshdId=club.club_ishd_id,
                                teams=[assigned_team],
                            )

                            # Check if player already exists in existing_players array
                            player_exists = False
                            existing_player = None
                            for existing_player_loop in existing_players:
                                if (
                                    existing_player_loop["firstName"] == player["first_name"]
                                    and existing_player_loop["lastName"] == player["last_name"]
                                    and datetime.strftime(
                                        existing_player_loop["birthdate"], "%Y-%m-%d"
                                    )
                                    == player["date_of_birth"]
                                ):
                                    player_exists = True
                                    existing_player = existing_player_loop
                                    break

                            if player_exists and existing_player is not None:
                                # EXISTING PLAYER - update team assignments
                                club_assignment_exists = False

                                # Correctly identify existing_player as a dict
                                assigned_teams_list = existing_player.get("assignedTeams", [])
                                if not isinstance(assigned_teams_list, list):
                                    assigned_teams_list = []

                                for club_assignment in assigned_teams_list:
                                    if club_assignment["clubName"] == club.club_name:
                                        club_assignment_exists = True

                                        # Check if team assignment exists
                                        team_assignment_exists = False
                                        for team_assignment in club_assignment.get("teams", []):
                                            if team_assignment["teamId"] == team["_id"]:
                                                team_assignment_exists = True
                                                ishd_pass_no = player["license_number"]
                                                current_pass_no = team_assignment.get("passNo")
                                                if (
                                                    existing_player.get("managedByISHD", True) is not False
                                                    and team_assignment.get("source") == Source.ISHD
                                                    and current_pass_no != ishd_pass_no
                                                ):
                                                    old_pass_no = current_pass_no
                                                    team_assignment["passNo"] = ishd_pass_no
                                                    team_assignment["modifyDate"] = datetime.strptime(
                                                        player["last_modification"], "%Y-%m-%d %H:%M:%S"
                                                    )

                                                    existing_player = (
                                                        await self.classify_license_types_for_player(
                                                            existing_player
                                                        )
                                                    )
                                                    existing_player = (
                                                        await self.validate_licenses_for_player(
                                                            existing_player
                                                        )
                                                    )

                                                    birthdate_val = existing_player.get("birthdate")
                                                    birthdate_str = (
                                                        birthdate_val.strftime("%Y-%m-%d")
                                                        if birthdate_val
                                                        else "Unknown"
                                                    )
                                                    if mode == "dry":
                                                        log_line = f"[DRY] Would update passNo for: {existing_player.get('firstName')} {existing_player.get('lastName')} {birthdate_str} -> {club.club_name} / {team['ishdId']} (passNo: {old_pass_no} -> {ishd_pass_no})"
                                                        logger.info(log_line)
                                                        log_lines.append(log_line)
                                                        ishd_log_player.action = IshdAction.UPDATE_TEAM
                                                        stats["updated_passno"] += 1
                                                    else:
                                                        result = await self.db["players"].update_one(
                                                            {"_id": existing_player["_id"]},
                                                            {
                                                                "$set": {
                                                                    "assignedTeams": jsonable_encoder(
                                                                        existing_player["assignedTeams"]
                                                                    )
                                                                }
                                                            },
                                                        )
                                                        if result.modified_count:
                                                            log_line = f"Updated passNo for: {existing_player.get('firstName')} {existing_player.get('lastName')} {birthdate_str} -> {club.club_name} / {team['ishdId']} (passNo: {old_pass_no} -> {ishd_pass_no})"
                                                            logger.info(log_line)
                                                            log_lines.append(log_line)
                                                            ishd_log_player.action = IshdAction.UPDATE_TEAM
                                                            stats["updated_passno"] += 1
                                                        else:
                                                            logger.debug(
                                                                f"passNo update had no effect for: {existing_player.get('firstName')} {existing_player.get('lastName')} {birthdate_str}"
                                                            )
                                                break

                                        if not team_assignment_exists:
                                            # Add team assignment to existing club
                                            club_assignment.get("teams").append(
                                                jsonable_encoder(assigned_team)
                                            )
                                            # Fix: Update the list in place if needed, or ensure it's correctly referenced
                                            # The current logic below [club_assignment] + ... might be creating duplicates if not careful
                                            # but the primary issue is the loop over assignedTeams might be hitting the same club multiple times
                                            # if the player data has duplicates or if the logic is called in a way that repeats.

                                            # Apply license classification and validation
                                            existing_player = (
                                                await self.classify_license_types_for_player(
                                                    existing_player
                                                )
                                            )
                                            existing_player = (
                                                await self.validate_licenses_for_player(
                                                    existing_player
                                                )
                                            )

                                            # Persist to database (skip in dry mode)
                                            if mode == "dry":
                                                birthdate_val = existing_player.get("birthdate")
                                                birthdate_str = (
                                                    birthdate_val.strftime("%Y-%m-%d")
                                                    if birthdate_val
                                                    else "Unknown"
                                                )
                                                log_line = f"[DRY] Would update team assignment for: {existing_player.get('firstName')} {existing_player.get('lastName')} {birthdate_str} -> {club.club_name} / {team['ishdId']}"
                                                logger.info(log_line)
                                                log_lines.append(log_line)
                                                ishd_log_player.action = IshdAction.ADD_TEAM
                                                stats["updated_teams"] += 1
                                            else:
                                                result = await self.db["players"].update_one(
                                                    {"_id": existing_player["_id"]},
                                                    {
                                                        "$set": {
                                                            "assignedTeams": jsonable_encoder(
                                                                existing_player["assignedTeams"]
                                                            )
                                                        }
                                                    },
                                                )
                                                if result.modified_count:
                                                    birthdate_val = existing_player.get("birthdate")
                                                    birthdate_str = (
                                                        birthdate_val.strftime("%Y-%m-%d")
                                                        if birthdate_val
                                                        else "Unknown"
                                                    )
                                                    log_line = f"Updated team assignment for: {existing_player.get('firstName')} {existing_player.get('lastName')} {birthdate_str} -> {club.club_name} / {team['ishdId']}"
                                                    logger.info(log_line)
                                                    log_lines.append(log_line)
                                                    ishd_log_player.action = IshdAction.ADD_TEAM
                                                    stats["updated_teams"] += 1
                                                else:
                                                    raise DatabaseOperationException(
                                                        operation="update_one",
                                                        collection="players",
                                                        details={
                                                            "player_id": existing_player["_id"],
                                                            "reason": "Failed to update team assignment",
                                                        },
                                                    )
                                        break

                                if not club_assignment_exists:
                                    # Club assignment does not exist - add new club with team
                                    existing_player["assignedTeams"].append(
                                        jsonable_encoder(assigned_club)
                                    )

                                    # Apply license classification and validation
                                    existing_player = await self.classify_license_types_for_player(
                                        existing_player
                                    )
                                    existing_player = await self.validate_licenses_for_player(
                                        existing_player
                                    )

                                    # Persist to database (skip in dry mode)
                                    if mode == "dry":
                                        birthdate_val = existing_player.get("birthdate")
                                        birthdate_str = (
                                            birthdate_val.strftime("%Y-%m-%d")
                                            if birthdate_val
                                            else "Unknown"
                                        )
                                        log_line = f"[DRY] Would add club assignment for: {existing_player.get('firstName')} {existing_player.get('lastName')} {birthdate_str} -> {club.club_name} / {team.get('ishdId')}"
                                        logger.info(log_line)
                                        log_lines.append(log_line)
                                        ishd_log_player.action = IshdAction.ADD_CLUB
                                        stats["updated_teams"] += 1
                                    else:
                                        result = await self.db["players"].update_one(
                                            {"_id": existing_player["_id"]},
                                            {
                                                "$set": {
                                                    "source": Source.ISHD,
                                                    "assignedTeams": jsonable_encoder(
                                                        existing_player["assignedTeams"]
                                                    ),
                                                }
                                            },
                                        )
                                        if result.modified_count:
                                            birthdate_val = existing_player.get("birthdate")
                                            birthdate_str = (
                                                birthdate_val.strftime("%Y-%m-%d")
                                                if birthdate_val
                                                else "Unknown"
                                            )
                                            log_line = f"New club assignment for: {existing_player.get('firstName')} {existing_player.get('lastName')} {birthdate_str} -> {club.club_name} / {team.get('ishdId')}"
                                            logger.info(log_line)
                                            log_lines.append(log_line)
                                            ishd_log_player.action = IshdAction.ADD_CLUB
                                            stats["updated_teams"] += 1
                                        else:
                                            raise DatabaseOperationException(
                                                operation="update_one",
                                                collection="players",
                                                details={
                                                    "player_id": existing_player["_id"],
                                                    "reason": "Failed to add club assignment",
                                                },
                                            )

                            else:
                                # NEW PLAYER - create and insert
                                new_player = PlayerBase(
                                    firstName=player["first_name"],
                                    lastName=player["last_name"],
                                    birthdate=datetime.strptime(
                                        player["date_of_birth"], "%Y-%m-%d"
                                    ),
                                    displayFirstName=player["first_name"],
                                    displayLastName=player["last_name"],
                                    nationality=(
                                        player["nationality"] if "nationality" in player else None
                                    ),
                                    assignedTeams=[assigned_club],
                                    fullFaceReq=(
                                        True if player.get("full_face_req") == "true" else False
                                    ),
                                    source=Source.ISHD,
                                )
                                new_player_dict = jsonable_encoder(new_player)
                                new_player_dict["birthdate"] = datetime.strptime(
                                    player["date_of_birth"], "%Y-%m-%d"
                                )
                                new_player_dict["createDate"] = create_date

                                # Apply license classification and validation
                                new_player_dict = await self.classify_license_types_for_player(
                                    new_player_dict
                                )
                                new_player_dict = await self.validate_licenses_for_player(
                                    new_player_dict
                                )

                                # Check if any license is INVALID (for stats)
                                for club_assign in new_player_dict.get("assignedTeams", []):
                                    for team_assign in club_assign.get("teams", []):
                                        if team_assign.get("status") == LicenseStatus.INVALID:
                                            stats["invalid_new"] += 1

                                # Add to existing players array
                                existing_players.append(new_player_dict)

                                # Persist to database (skip in dry mode)
                                if mode == "dry":
                                    birthdate = new_player_dict.get("birthdate")
                                    birthdate_str = (
                                        birthdate.strftime("%Y-%m-%d")
                                        if isinstance(birthdate, datetime)
                                        else "Unknown"
                                    )
                                    log_line = f"[DRY] Would insert player: {new_player_dict.get('firstName')} {new_player_dict.get('lastName')} {birthdate_str} -> {assigned_club.clubName} / {assigned_team.teamName}"
                                    logger.info(log_line)
                                    log_lines.append(log_line)
                                    ishd_log_player.action = IshdAction.ADD_PLAYER
                                    stats["added_players"] += 1
                                else:
                                    result = await self.db["players"].insert_one(new_player_dict)
                                    if result.inserted_id:
                                        birthdate = new_player_dict.get("birthdate")
                                        birthdate_str = (
                                            birthdate.strftime("%Y-%m-%d")
                                            if isinstance(birthdate, datetime)
                                            else "Unknown"
                                        )
                                        log_line = f"Inserted player: {new_player_dict.get('firstName')} {new_player_dict.get('lastName')} {birthdate_str} -> {assigned_club.clubName} / {assigned_team.teamName}"
                                        logger.info(log_line)
                                        log_lines.append(log_line)
                                        ishd_log_player.action = IshdAction.ADD_PLAYER
                                        stats["added_players"] += 1
                                    else:
                                        raise DatabaseOperationException(
                                            operation="insert_one",
                                            collection="players",
                                            details={
                                                "player_name": f"{new_player_dict.get('firstName')} {new_player_dict.get('lastName')}",
                                                "reason": "Insert operation did not return inserted_id",
                                            },
                                        )

                            if ishd_log_player.action is not None:
                                ishd_log_team.players.append(ishd_log_player)

                        ishd_data.append(data)

                        # Handle DEL: Remove players from team if missing in ISHD data
                        query = {
                            "assignedTeams": {
                                "$elemMatch": {
                                    "clubAlias": club.club_alias,
                                    "teams.teamAlias": team["alias"],
                                }
                            }
                        }
                        players = await self.db["players"].find(query).to_list(length=None)
                        if mode == "test":
                            print("removing / players:", players)

                        if players:
                            for player_to_check in players:
                                ishd_log_player_remove = IshdLogPlayer(
                                    firstName=player_to_check["firstName"],
                                    lastName=player_to_check["lastName"],
                                    birthdate=player_to_check["birthdate"],
                                )
                                if mode == "test":
                                    print("remove player ?", player_to_check)

                                # Only remove player from team if source is ISHD
                                team_source_is_ishd = False
                                for club_assignment in player_to_check.get("assignedTeams", []):
                                    if club_assignment.get("clubAlias") == club.club_alias:
                                        for team_assignment in club_assignment.get("teams", []):
                                            if (
                                                team_assignment.get("teamAlias") == team["alias"]
                                                and team_assignment.get("source") == "ISHD"
                                            ):
                                                team_source_is_ishd = True
                                                break

                                # Skip players with managedByISHD=false
                                if player_to_check.get("managedByISHD", True) is False:
                                    birthdate_val = player_to_check.get("birthdate")
                                    birthdate_str = (
                                        birthdate_val.strftime("%Y-%m-%d")
                                        if birthdate_val
                                        else "Unknown"
                                    )
                                    log_line = f"Skipping player (managedByISHD=false): {player_to_check.get('firstName')} {player_to_check.get('lastName')} {birthdate_str}"
                                    logger.info(log_line)
                                    log_lines.append(log_line)
                                    continue

                                # Check if player exists in ISHD data by comparing name and birthdate
                                player_birthdate = player_to_check.get("birthdate")
                                player_birthdate_str = (
                                    player_birthdate.strftime("%Y-%m-%d")
                                    if player_birthdate
                                    else ""
                                )

                                if team_source_is_ishd and not any(
                                    p["first_name"] == player_to_check["firstName"]
                                    and p["last_name"] == player_to_check["lastName"]
                                    and p["date_of_birth"] == player_birthdate_str
                                    for p in data["players"]
                                ):
                                    # Player missing in ISHD - remove from team (skip in dry mode)
                                    if mode == "dry":
                                        del_birthdate = player_to_check.get("birthdate")
                                        del_birthdate_str = (
                                            del_birthdate.strftime("%Y-%m-%d")
                                            if del_birthdate
                                            else "Unknown"
                                        )
                                        log_line = f"[DRY] Would remove player from team: {player_to_check.get('firstName')} {player_to_check.get('lastName')} {del_birthdate_str} -> {club.club_name} / {team.get('ishdId')}"
                                        logger.info(log_line)
                                        log_lines.append(log_line)
                                        ishd_log_player_remove.action = IshdAction.DEL_TEAM
                                        stats["deleted"] += 1
                                    else:
                                        query_update = {
                                            "$and": [
                                                {"_id": player_to_check["_id"]},
                                                {
                                                    "assignedTeams": {
                                                        "$elemMatch": {
                                                            "clubAlias": club.club_alias,
                                                            "teams": {
                                                                "$elemMatch": {
                                                                    "teamAlias": team["alias"]
                                                                }
                                                            },
                                                        }
                                                    }
                                                },
                                            ]
                                        }
                                        result = await self.db["players"].update_one(
                                            query_update,
                                            {
                                                "$pull": {
                                                    "assignedTeams.$.teams": {
                                                        "teamAlias": team["alias"]
                                                    }
                                                }
                                            },
                                        )
                                        if result.modified_count:
                                            # Update existing_players array
                                            for existing_player in existing_players:
                                                if existing_player["_id"] == player_to_check["_id"]:
                                                    for club_assignment in existing_player.get(
                                                        "assignedTeams", []
                                                    ):
                                                        if (
                                                            club_assignment["clubAlias"]
                                                            == club.club_alias
                                                        ):
                                                            club_assignment["teams"] = [
                                                                t
                                                                for t in club_assignment["teams"]
                                                                if t["teamAlias"] != team["alias"]
                                                            ]
                                                            break

                                            del_birthdate = player_to_check.get("birthdate")
                                            del_birthdate_str = (
                                                del_birthdate.strftime("%Y-%m-%d")
                                                if del_birthdate
                                                else "Unknown"
                                            )
                                            log_line = f"Removed player from team: {player_to_check.get('firstName')} {player_to_check.get('lastName')} {del_birthdate_str} -> {club.club_name} / {team.get('ishdId')}"
                                            logger.info(log_line)
                                            log_lines.append(log_line)
                                            ishd_log_player_remove.action = IshdAction.DEL_TEAM
                                            stats["deleted"] += 1

                                            # Remove club assignment if teams array is empty
                                            result = await self.db["players"].update_one(
                                                {
                                                    "_id": player_to_check["_id"],
                                                    "assignedTeams.clubIshdId": club.club_ishd_id,
                                                },
                                                {
                                                    "$pull": {
                                                        "assignedTeams": {"teams": {"$size": 0}}
                                                    }
                                                },
                                            )
                                            if result.modified_count:
                                                for existing_player in existing_players:
                                                    if (
                                                        existing_player["_id"]
                                                        == player_to_check["_id"]
                                                    ):
                                                        existing_player["assignedTeams"] = [
                                                            a
                                                            for a in existing_player.get(
                                                                "assignedTeams", []
                                                            )
                                                            if a["clubIshdId"] != club.club_ishd_id
                                                        ]
                                                        break

                                                birthdate_val = player_to_check.get("birthdate")
                                                birthdate_str = (
                                                    birthdate_val.strftime("%Y-%m-%d")
                                                    if birthdate_val
                                                    else "Unknown"
                                                )
                                                log_line = f"Removed club assignment for player: {player_to_check.get('firstName')} {player_to_check.get('lastName')} {birthdate_str} -> {club.club_name}"
                                                logger.info(log_line)
                                                log_lines.append(log_line)
                                                ishd_log_player_remove.action = IshdAction.DEL_CLUB
                                            else:
                                                logger.debug(
                                                    f"--- No club assignment removed for {player_to_check.get('firstName')} {player_to_check.get('lastName')}"
                                                )
                                        else:
                                            raise DatabaseOperationException(
                                                operation="update_one",
                                                collection="players",
                                                details={
                                                    "player_id": player_to_check["_id"],
                                                    "reason": "Failed to remove player from team",
                                                },
                                            )
                                else:
                                    if mode == "test":
                                        print("player exists in team - do not remove")

                                if ishd_log_player_remove.action is not None:
                                    ishd_log_team.players.append(ishd_log_player_remove)

                    if ishd_log_team:
                        ishd_log_club.teams.append(ishd_log_team)

                if ishd_log_club:
                    ishd_log_base.clubs.append(ishd_log_club)

        # Persist ISHD log to database (skip in dry mode)
        ishd_log_base_enc = jsonable_encoder(ishd_log_base)
        # Ensure processDate is stored as a datetime object in MongoDB, not a string
        ishd_log_base_enc["processDate"] = ishd_log_base.processDate
        if mode != "dry":
            result = await self.db["ishdLogs"].insert_one(ishd_log_base_enc)
            if result.inserted_id:
                log_line = "Inserted ISHD log into ishdLogs collection."
                log_lines.append(log_line)
            else:
                raise DatabaseOperationException(
                    operation="insert_one",
                    collection="ishdLogs",
                    details={"reason": "Insert operation did not return inserted_id"},
                )

        return {
            "logs": log_lines,
            "stats": stats,
            "ishdLog": ishd_log_base_enc,
        }

    async def bootstrap_ishd_sync(self, mode: str = "live", reset: bool = False) -> dict[str, Any]:
        """
        Orchestrate ISHD synchronization for all managedByISHD=True players.

        Args:
          mode: Sync mode - "live", "test", or "dry"
          reset: If True and mode is "test", delete all players before sync

        Returns:
          Dict containing sync results
        """
        log_lines: list[str] = []

        # If reset is True and mode is test, delete all managed players first
        if reset and mode == "test":
            result = await self.db["players"].delete_many({"managedByISHD": {"$ne": False}})
            log_line = f"Reset: Deleted {result.deleted_count} players with managedByISHD=True"
            logger.warning(log_line)
            log_lines.append(log_line)

        # Run the ISHD sync
        result = await self.process_ishd_sync(mode=mode, run=1)
        result["logs"] = log_lines + result.get("logs", [])

        return result
