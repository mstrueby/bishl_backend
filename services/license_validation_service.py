
"""
License Validation Service - Business logic for player license validation

Validates player licenses according to WKO/BISHL rules and updates status and invalidReasonCodes.
"""

from datetime import datetime

from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from config import settings
from logging_config import logger
from models.players import (
    AssignedClubs,
    AssignedTeams,
    LicenseInvalidReasonCode,
    LicenseStatusEnum,
    LicenseTypeEnum,
    PlayerDB,
    SourceEnum,
)


class AgeGroupRule(BaseModel):
    """WKO Age Group Configuration"""
    key: str
    value: str
    sortOrder: int
    altKey: str
    canAlsoPlayIn: list[str] = Field(default_factory=list)
    canPlayOverAgeIn: list[str] = Field(default_factory=list)
    maxOverAgePlayers: int | None = None
    requiresOverAge: bool = False


class LicenseValidationReport(BaseModel):
    """Report of license validation results"""
    playerId: str
    changedLicenses: int
    errors: list[str] = Field(default_factory=list)
    validLicenses: int = 0
    invalidLicenses: int = 0


class LicenseValidationService:
    """Service for validating player licenses according to WKO/BISHL rules"""

    # WKO Age Group Configuration
    AGE_GROUP_CONFIG: list[AgeGroupRule] = [
        AgeGroupRule(
            key="HERREN",
            value="Herren",
            sortOrder=1,
            altKey="Herren",
            canAlsoPlayIn=[],
        ),
        AgeGroupRule(
            key="DAMEN",
            value="Damen",
            sortOrder=2,
            altKey="Damen",
            canAlsoPlayIn=["HERREN"],
            canPlayOverAgeIn=["U19"],
        ),
        AgeGroupRule(
            key="U19",
            value="U19",
            sortOrder=3,
            altKey="Junioren",
            canAlsoPlayIn=["HERREN"],
            canPlayOverAgeIn=["U16"],
            maxOverAgePlayers=3,
        ),
        AgeGroupRule(
            key="U16",
            value="U16",
            sortOrder=4,
            altKey="Jugend",
            canAlsoPlayIn=["U19", "DAMEN"],
            canPlayOverAgeIn=["U13"],
            maxOverAgePlayers=3,
        ),
        AgeGroupRule(
            key="U13",
            value="U13",
            sortOrder=5,
            altKey="Schüler",
            canAlsoPlayIn=["U16"],
            canPlayOverAgeIn=["U10"],
            maxOverAgePlayers=3,
        ),
        AgeGroupRule(
            key="U10",
            value="U10",
            sortOrder=6,
            altKey="Bambini",
            canAlsoPlayIn=["U13"],
            requiresOverAge=True,
            maxOverAgePlayers=2,
        ),
        AgeGroupRule(
            key="U8",
            value="U8",
            sortOrder=7,
            altKey="Mini",
            canAlsoPlayIn=["U10"],
            maxOverAgePlayers=2,
        ),
    ]

    # Maximum number of active age class participations allowed by WKO
    MAX_AGE_CLASS_PARTICIPATIONS = 2

    def __init__(self, db):
        self.db = db
        self._age_group_map = {rule.key: rule for rule in self.AGE_GROUP_CONFIG}

    async def revalidate_player_licenses(
        self, player: PlayerDB
    ) -> LicenseValidationReport:
        """
        Recomputes status and invalidReasonCodes for all AssignedTeams of the player
        based on WKO/BISHL rules. Persists changes in the database.

        Args:
            player: PlayerDB object with all assigned teams

        Returns:
            LicenseValidationReport with validation results
        """
        if settings.DEBUG_LEVEL > 0:
            logger.debug(
                f"Starting license validation for player {player.id} ({player.firstName} {player.lastName})"
            )

        original_state = self._capture_license_state(player)

        # Step 1: Reset all license states
        self._reset_license_states(player)

        # Step 2: Validate PRIMARY consistency
        self._validate_primary_consistency(player)

        # Step 3: Validate LOAN consistency
        self._validate_loan_consistency(player)

        # Step 4: Validate ISHD vs BISHL conflicts
        self._validate_import_conflicts(player)

        # Step 5: Determine primary club
        primary_club_id = self._get_primary_club_id(player)

        # Step 6: Validate club consistency for SECONDARY/OVERAGE
        if primary_club_id:
            self._validate_club_consistency(player, primary_club_id)

        # Step 7: Validate age group violations and OVERAGE rules
        self._validate_age_group_compliance(player)

        # Step 8: Validate WKO limits (max participations)
        self._validate_wko_limits(player)

        # Step 9: Validate date sanity
        self._validate_date_sanity(player)

        # Count changes and persist
        changed_count = self._count_changes(original_state, player)

        if changed_count > 0:
            await self._persist_changes(player)

        # Generate report
        report = self._generate_report(player, changed_count)

        if settings.DEBUG_LEVEL > 0:
            logger.debug(
                f"License validation complete for player {player.id}: "
                f"{report.validLicenses} valid, {report.invalidLicenses} invalid, "
                f"{changed_count} changed"
            )

        return report

    def _reset_license_states(self, player: PlayerDB) -> None:
        """Reset all licenses to VALID with empty invalidReasonCodes"""
        if not player.assignedTeams:
            return

        for club in player.assignedTeams:
            for team in club.teams:
                team.status = LicenseStatusEnum.VALID
                team.invalidReasonCodes = []

    def _validate_primary_consistency(self, player: PlayerDB) -> None:
        """Validate that player has at most one PRIMARY license"""
        if not player.assignedTeams:
            return

        primary_licenses = []
        for club in player.assignedTeams:
            for team in club.teams:
                if team.licenseType == LicenseTypeEnum.PRIMARY:
                    primary_licenses.append((club, team))

        if len(primary_licenses) > 1:
            # Mark all PRIMARY licenses as invalid
            for club, team in primary_licenses:
                team.status = LicenseStatusEnum.INVALID
                if LicenseInvalidReasonCode.MULTIPLE_PRIMARY not in team.invalidReasonCodes:
                    team.invalidReasonCodes.append(LicenseInvalidReasonCode.MULTIPLE_PRIMARY)

    def _validate_loan_consistency(self, player: PlayerDB) -> None:
        """Validate that player has at most one LOAN license"""
        if not player.assignedTeams:
            return

        loan_licenses = []
        for club in player.assignedTeams:
            for team in club.teams:
                if team.licenseType == LicenseTypeEnum.LOAN and team.status == LicenseStatusEnum.VALID:
                    loan_licenses.append((club, team))

        if len(loan_licenses) > 1:
            # Mark all LOAN licenses as invalid
            for club, team in loan_licenses:
                team.status = LicenseStatusEnum.INVALID
                if LicenseInvalidReasonCode.TOO_MANY_LOAN not in team.invalidReasonCodes:
                    team.invalidReasonCodes.append(LicenseInvalidReasonCode.TOO_MANY_LOAN)

    def _validate_import_conflicts(self, player: PlayerDB) -> None:
        """Validate ISHD vs BISHL conflicts - ISHD never overrides BISHL"""
        if not player.assignedTeams:
            return

        # Collect BISHL licenses by type
        bishl_licenses: dict[LicenseTypeEnum, set[str]] = {}

        for club in player.assignedTeams:
            for team in club.teams:
                if team.source == SourceEnum.BISHL and team.status == LicenseStatusEnum.VALID:
                    if team.licenseType not in bishl_licenses:
                        bishl_licenses[team.licenseType] = set()
                    bishl_licenses[team.licenseType].add(team.teamId)

        # Check ISHD licenses for conflicts
        for club in player.assignedTeams:
            for team in club.teams:
                if team.source == SourceEnum.ISHD and team.status == LicenseStatusEnum.VALID:
                    # If there's a BISHL license of the same type, mark ISHD as conflict
                    if team.licenseType in bishl_licenses:
                        # For PRIMARY, any BISHL PRIMARY conflicts
                        if team.licenseType == LicenseTypeEnum.PRIMARY:
                            team.status = LicenseStatusEnum.INVALID
                            if LicenseInvalidReasonCode.IMPORT_CONFLICT not in team.invalidReasonCodes:
                                team.invalidReasonCodes.append(LicenseInvalidReasonCode.IMPORT_CONFLICT)

    def _get_primary_club_id(self, player: PlayerDB) -> str | None:
        """Get the club ID of the valid PRIMARY license"""
        if not player.assignedTeams:
            return None

        for club in player.assignedTeams:
            for team in club.teams:
                if (team.licenseType == LicenseTypeEnum.PRIMARY 
                    and team.status == LicenseStatusEnum.VALID):
                    return club.clubId

        return None

    def _validate_club_consistency(self, player: PlayerDB, primary_club_id: str) -> None:
        """Validate that SECONDARY and OVERAGE licenses belong to the primary club"""
        if not player.assignedTeams:
            return

        for club in player.assignedTeams:
            for team in club.teams:
                if team.licenseType in [LicenseTypeEnum.SECONDARY, LicenseTypeEnum.OVERAGE]:
                    if club.clubId != primary_club_id:
                        team.status = LicenseStatusEnum.INVALID
                        if LicenseInvalidReasonCode.CONFLICTING_CLUB not in team.invalidReasonCodes:
                            team.invalidReasonCodes.append(LicenseInvalidReasonCode.CONFLICTING_CLUB)

    def _validate_age_group_compliance(self, player: PlayerDB) -> None:
        """Validate age group compliance and OVERAGE rules"""
        if not player.assignedTeams:
            return

        player_age_group = player.ageGroup
        player_is_overage = player.overAge

        for club in player.assignedTeams:
            for team in club.teams:
                if team.status != LicenseStatusEnum.VALID:
                    continue

                team_age_group = team.teamAgeGroup

                # Handle OVERAGE licenses
                if team.licenseType == LicenseTypeEnum.OVERAGE:
                    if not self._is_overage_allowed(player_age_group, team_age_group, player_is_overage):
                        team.status = LicenseStatusEnum.INVALID
                        if LicenseInvalidReasonCode.OVERAGE_NOT_ALLOWED not in team.invalidReasonCodes:
                            team.invalidReasonCodes.append(LicenseInvalidReasonCode.OVERAGE_NOT_ALLOWED)

                # Handle SECONDARY licenses - check if allowed to play in this age group
                elif team.licenseType == LicenseTypeEnum.SECONDARY:
                    if not self._is_secondary_allowed(player_age_group, team_age_group):
                        team.status = LicenseStatusEnum.INVALID
                        if LicenseInvalidReasonCode.AGE_GROUP_VIOLATION not in team.invalidReasonCodes:
                            team.invalidReasonCodes.append(LicenseInvalidReasonCode.AGE_GROUP_VIOLATION)

                # Handle PRIMARY licenses - basic age group check
                elif team.licenseType == LicenseTypeEnum.PRIMARY:
                    if not self._is_age_group_compatible(player_age_group, team_age_group):
                        team.status = LicenseStatusEnum.INVALID
                        if LicenseInvalidReasonCode.AGE_GROUP_VIOLATION not in team.invalidReasonCodes:
                            team.invalidReasonCodes.append(LicenseInvalidReasonCode.AGE_GROUP_VIOLATION)

    def _is_overage_allowed(self, player_age_group: str, team_age_group: str, player_is_overage: bool) -> bool:
        """Check if OVERAGE license is allowed based on WKO rules"""
        if not player_is_overage:
            return False

        if player_age_group not in self._age_group_map:
            return False

        player_rule = self._age_group_map[player_age_group]

        # Check if the team age group is in the allowed overage list
        return team_age_group in player_rule.canPlayOverAgeIn

    def _is_secondary_allowed(self, player_age_group: str, team_age_group: str) -> bool:
        """Check if SECONDARY license in this age group is allowed"""
        if player_age_group not in self._age_group_map:
            return False

        player_rule = self._age_group_map[player_age_group]

        # SECONDARY can be in same age group or allowed play-up groups
        if team_age_group == player_age_group:
            return True

        return team_age_group in player_rule.canAlsoPlayIn

    def _is_age_group_compatible(self, player_age_group: str, team_age_group: str) -> bool:
        """Check if player can play in the team's age group (play-up allowed, play-down not)"""
        if player_age_group not in self._age_group_map or team_age_group not in self._age_group_map:
            return True  # Unknown age groups - allow for now

        player_rule = self._age_group_map[player_age_group]
        team_rule = self._age_group_map[team_age_group]

        # Same age group is always OK
        if player_age_group == team_age_group:
            return True

        # Playing up (younger player in older group) is OK if in canAlsoPlayIn
        if team_rule.sortOrder < player_rule.sortOrder:
            return team_age_group in player_rule.canAlsoPlayIn

        # Playing down (older player in younger group) is not allowed without OVERAGE
        return False

    def _validate_wko_limits(self, player: PlayerDB) -> None:
        """Validate WKO limits on number of age class participations"""
        if not player.assignedTeams:
            return

        # Count valid participations by age group (PRIMARY, SECONDARY, OVERAGE)
        participations: list[tuple] = []

        for club in player.assignedTeams:
            for team in club.teams:
                if (team.status == LicenseStatusEnum.VALID 
                    and team.licenseType in [LicenseTypeEnum.PRIMARY, LicenseTypeEnum.SECONDARY, LicenseTypeEnum.OVERAGE]):
                    participations.append((club, team, team.teamAgeGroup))

        # If exceeds WKO limit, mark excess as invalid
        if len(participations) > self.MAX_AGE_CLASS_PARTICIPATIONS:
            # Keep PRIMARY first, then sort by age group order
            def sort_key(item):
                club, team, age_group = item
                priority = 0 if team.licenseType == LicenseTypeEnum.PRIMARY else 1
                age_order = self._age_group_map.get(age_group, AgeGroupRule(key="", value="", sortOrder=999, altKey="")).sortOrder
                return (priority, age_order)

            participations.sort(key=sort_key)

            # Mark excess as invalid
            for club, team, _ in participations[self.MAX_AGE_CLASS_PARTICIPATIONS:]:
                team.status = LicenseStatusEnum.INVALID
                if LicenseInvalidReasonCode.EXCEEDS_WKO_LIMIT not in team.invalidReasonCodes:
                    team.invalidReasonCodes.append(LicenseInvalidReasonCode.EXCEEDS_WKO_LIMIT)

    def _validate_date_sanity(self, player: PlayerDB) -> None:
        """Validate date sanity (validFrom <= validTo)"""
        if not player.assignedTeams:
            return

        for club in player.assignedTeams:
            for team in club.teams:
                if team.validFrom and team.validTo:
                    if team.validFrom > team.validTo:
                        team.status = LicenseStatusEnum.INVALID
                        if LicenseInvalidReasonCode.IMPORT_CONFLICT not in team.invalidReasonCodes:
                            team.invalidReasonCodes.append(LicenseInvalidReasonCode.IMPORT_CONFLICT)

    def _capture_license_state(self, player: PlayerDB) -> dict:
        """Capture current state of all licenses for comparison"""
        state = {}
        if not player.assignedTeams:
            return state

        for club_idx, club in enumerate(player.assignedTeams):
            for team_idx, team in enumerate(club.teams):
                key = f"{club_idx}_{team_idx}"
                state[key] = {
                    "status": team.status,
                    "invalidReasonCodes": team.invalidReasonCodes.copy() if team.invalidReasonCodes else []
                }

        return state

    def _count_changes(self, original_state: dict, player: PlayerDB) -> int:
        """Count how many licenses changed"""
        changed = 0
        if not player.assignedTeams:
            return changed

        for club_idx, club in enumerate(player.assignedTeams):
            for team_idx, team in enumerate(club.teams):
                key = f"{club_idx}_{team_idx}"
                if key in original_state:
                    orig = original_state[key]
                    if (orig["status"] != team.status 
                        or set(orig["invalidReasonCodes"]) != set(team.invalidReasonCodes or [])):
                        changed += 1

        return changed

    async def _persist_changes(self, player: PlayerDB) -> None:
        """Persist license changes to database"""
        update_data = {
            "assignedTeams": jsonable_encoder(player.assignedTeams)
        }

        await self.db["players"].update_one(
            {"_id": str(player.id)},
            {"$set": update_data}
        )

        logger.info(
            "License validation persisted",
            extra={
                "player_id": str(player.id),
                "player_name": f"{player.firstName} {player.lastName}"
            }
        )

    def _generate_report(self, player: PlayerDB, changed_count: int) -> LicenseValidationReport:
        """Generate validation report"""
        valid_count = 0
        invalid_count = 0
        errors = []

        if player.assignedTeams:
            for club in player.assignedTeams:
                for team in club.teams:
                    if team.status == LicenseStatusEnum.VALID:
                        valid_count += 1
                    else:
                        invalid_count += 1
                        if team.invalidReasonCodes:
                            errors.append(
                                f"{team.teamName} ({team.licenseType}): {', '.join(team.invalidReasonCodes)}"
                            )

        return LicenseValidationReport(
            playerId=str(player.id),
            changedLicenses=changed_count,
            validLicenses=valid_count,
            invalidLicenses=invalid_count,
            errors=errors
        )
