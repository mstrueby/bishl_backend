"""
Player Assignment Service - Unified license classification and validation

Responsibilities:
1. Classification: Set licenseType based on passNo suffixes and heuristics
2. Validation: Set status and invalidReasonCodes based on WKO/BISHL rules

This service is the single entry point for all license-related operations.
"""

from datetime import datetime

from fastapi.encoders import jsonable_encoder

from config import settings
from logging_config import logger
from models.players import (LicenseStatusEnum, LicenseTypeEnum,
                            LicenseInvalidReasonCode, OverAgeRule,
                            SecondaryRule, SourceEnum, PlayerDB, WkoRule,
                            SexEnum)


class PlayerAssignmentService:
  """Service for player license classification and validation"""

  # WKO Rule Configuration
  WKO_RULES: list[WkoRule] = [
      WkoRule(
          ageGroup="HERREN",
          label="Herren",
          sortOrder=1,
          altKey="Herren",
          sex=[SexEnum.MALE, SexEnum.FEMALE],
          maxTotalAgeClasses={
              SexEnum.MALE: 2,
              SexEnum.FEMALE: 2
          },
      ),
      WkoRule(ageGroup="DAMEN",
              label="Damen",
              sortOrder=2,
              altKey="Damen",
              sex=[SexEnum.FEMALE],
              secondaryRules=[
                  SecondaryRule(targetAgeGroup="HERREN",
                                sex=[SexEnum.FEMALE],
                                maxLicenses=1,
                                requiresAdmin=False)
              ],
              overAgeRules=[
                  OverAgeRule(targetAgeGroup="U19",
                              sex=[SexEnum.FEMALE],
                              maxLicenses=1,
                              maxOverAgePlayersPerTeam=3)
              ],
              maxTotalAgeClasses={
                  SexEnum.MALE: 2,
                  SexEnum.FEMALE: 2
              }),
      WkoRule(ageGroup="U19",
              label="U19",
              sortOrder=3,
              altKey="Junioren",
              sex=[SexEnum.MALE, SexEnum.FEMALE],
              secondaryRules=[
                  SecondaryRule(targetAgeGroup="HERREN",
                                sex=[SexEnum.MALE],
                                maxLicenses=99,
                                requiresAdmin=False),
                  SecondaryRule(targetAgeGroup="DAMEN",
                                sex=[SexEnum.FEMALE],
                                maxLicenses=99,
                                requiresAdmin=False)
              ],
              overAgeRules=[
                  OverAgeRule(targetAgeGroup="U16",
                              sex=[SexEnum.MALE, SexEnum.FEMALE],
                              maxLicenses=1,
                              maxOverAgePlayersPerTeam=3)
              ],
              maxTotalAgeClasses={
                  SexEnum.MALE: 2,
                  SexEnum.FEMALE: 3
              }),
      WkoRule(ageGroup="U16",
              label="U16",
              sortOrder=4,
              altKey="Jugend",
              sex=[SexEnum.MALE, SexEnum.FEMALE],
              secondaryRules=[
                  SecondaryRule(targetAgeGroup="U19",
                                sex=[SexEnum.MALE, SexEnum.FEMALE],
                                maxLicenses=1,
                                requiresAdmin=False),
                  SecondaryRule(targetAgeGroup="HERREN",
                                sex=[SexEnum.MALE],
                                maxLicenses=1,
                                requiresAdmin=False),
                  SecondaryRule(targetAgeGroup="DAMEN",
                                sex=[SexEnum.FEMALE],
                                maxLicenses=1,
                                requiresAdmin=True),
              ],
              overAgeRules=[
                  OverAgeRule(targetAgeGroup="U13",
                              sex=[SexEnum.MALE, SexEnum.FEMALE],
                              maxLicenses=1,
                              maxOverAgePlayersPerTeam=3)
              ],
              maxTotalAgeClasses={
                  SexEnum.MALE: 2,
                  SexEnum.FEMALE: 3
              }),
      WkoRule(ageGroup="U13",
              label="U13",
              sortOrder=5,
              altKey="Schüler",
              sex=[SexEnum.MALE, SexEnum.FEMALE],
              secondaryRules=[
                  SecondaryRule(targetAgeGroup="U16",
                                sex=[SexEnum.MALE, SexEnum.FEMALE],
                                maxLicenses=1,
                                requiresAdmin=False),
                  SecondaryRule(targetAgeGroup="DAMEN",
                                sex=[SexEnum.FEMALE],
                                maxLicenses=1,
                                requiresAdmin=True)
              ],
              overAgeRules=[
                  OverAgeRule(targetAgeGroup="U10",
                              sex=[SexEnum.MALE, SexEnum.FEMALE],
                              maxLicenses=1,
                              maxOverAgePlayersPerTeam=3)
              ],
              maxTotalAgeClasses={
                  SexEnum.MALE: 2,
                  SexEnum.FEMALE: 3
              }),
      WkoRule(ageGroup="U10",
              label="U10",
              sortOrder=6,
              altKey="Bambini",
              sex=[SexEnum.MALE, SexEnum.FEMALE],
              secondaryRules=[
                  SecondaryRule(targetAgeGroup="U13",
                                sex=[SexEnum.MALE, SexEnum.FEMALE],
                                maxLicenses=1,
                                requiresAdmin=False),
                  SecondaryRule(targetAgeGroup="DAMEN",
                                sex=[SexEnum.FEMALE],
                                maxLicenses=1,
                                requiresAdmin=True)
              ],
              overAgeRules=[
                  OverAgeRule(targetAgeGroup="U8",
                              sex=[SexEnum.MALE, SexEnum.FEMALE],
                              maxLicenses=1,
                              maxOverAgePlayersPerTeam=2),
              ],
              maxTotalAgeClasses={
                  SexEnum.MALE: 2,
                  SexEnum.FEMALE: 3
              }),
      WkoRule(ageGroup="U8",
              label="U8",
              sortOrder=7,
              altKey="Mini",
              sex=[SexEnum.MALE, SexEnum.FEMALE],
              secondaryRules=[
                  SecondaryRule(targetAgeGroup="U10",
                                sex=[SexEnum.MALE, SexEnum.FEMALE],
                                maxLicenses=1,
                                requiresAdmin=False),
                  SecondaryRule(targetAgeGroup="DAMEN",
                                sex=[SexEnum.FEMALE],
                                maxLicenses=1,
                                requiresAdmin=True)
              ],
              maxTotalAgeClasses={
                  SexEnum.MALE: 2,
                  SexEnum.FEMALE: 3
              })
  ]

  # DEFAULT Maximum number of active age class participations allowed by WKO
  MAX_AGE_CLASS_PARTICIPATIONS = 2

  def _is_primary_like(self, license_type: LicenseTypeEnum) -> bool:
    """DEVELOPMENT acts as PRIMARY-like for anchor/quotas/consistency."""
    return license_type in [LicenseTypeEnum.PRIMARY, LicenseTypeEnum.DEVELOPMENT]

  def __init__(self, db):
    self.db = db
    # Build age group map from WKO_RULES, keeping as Pydantic model objects
    self._wko_rules = {rule.ageGroup: rule for rule in self.WKO_RULES}
    # License types that count as "primary-like" for WKO participation limits
    # DEVELOPMENT licenses are Förderlizenz for BISHL Unitas.Team origin clubs
    # They behave like PRIMARY for age class counting but don't conflict with PRIMARY
    self.PRIMARY_LIKE_TYPES = {LicenseTypeEnum.PRIMARY, LicenseTypeEnum.DEVELOPMENT}

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
      team_age_group = team.get("teamAgeGroup")
      
      # Get player's age group for comparison
      player_obj = PlayerDB(**player)
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
      # Only classify if licenseType is UNKNOWN or not set
      if team.get("licenseType"
                  ) == LicenseTypeEnum.UNKNOWN or not team.get("licenseType"):
        license_type = self._classify_by_pass_suffix(team.get("passNo", ""))
        team["licenseType"] = license_type

    # Step 3: Apply PRIMARY heuristic for UNKNOWN licenses based on age group match
    # We need to determine player's age group first
    player_obj = PlayerDB(**player)
    player_age_group = player_obj.ageGroup

    for club, team in all_licenses:
      if team.get("licenseType") == LicenseTypeEnum.UNKNOWN:
        team_age_group = team.get("teamAgeGroup")
        # If team age group matches player age group, set as PRIMARY
        if team_age_group and team_age_group == player_age_group:
          team["licenseType"] = LicenseTypeEnum.PRIMARY
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

      for club, team in all_licenses:
        # Only check UNKNOWN licenses
        if team.get("licenseType") == LicenseTypeEnum.UNKNOWN:
          team_age_group = team.get("teamAgeGroup")
          if not team_age_group or team_age_group not in self._wko_rules:
            continue

          team_rule = self._wko_rules[team_age_group]
          team_sort_order = team_rule.sortOrder

          # OVERAGE: team is exactly one age group below player
          # (higher sortOrder means younger age group)
          if team_sort_order == player_sort_order + 1:
            team["licenseType"] = LicenseTypeEnum.OVERAGE
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
        if team.get("licenseType") == LicenseTypeEnum.PRIMARY:
          clubs_with_primary.add(club.get("clubId"))
          break

    # Step 6:
    # For each club without PRIMARY, set first ISHD UNKNOWN license to PRIMARY
    for club in player.get("assignedTeams", []):
      club_id = club.get("clubId")
      if club_id not in clubs_with_primary:
        # Find ISHD UNKNOWN licenses in this club
        ishd_unknown_licenses = [
            team for team in club.get("teams", [])
            if team.get("licenseType") == LicenseTypeEnum.UNKNOWN
            and team.get("source") == SourceEnum.ISHD
        ]

        # Set first ISHD UNKNOWN to PRIMARY
        if ishd_unknown_licenses:
          ishd_unknown_licenses[0]["licenseType"] = LicenseTypeEnum.PRIMARY
          clubs_with_primary.add(club_id)
          if settings.DEBUG_LEVEL > 0:
            logger.debug(
                f"Set ISHD UNKNOWN license to PRIMARY in club without PRIMARY for player "
                f"{player.get('firstName')} {player.get('lastName')}")

    # Step 7: Convert UNKNOWN to SECONDARY in clubs with PRIMARY license
    # Then, convert UNKNOWN licenses in those clubs to SECONDARY
    for club in player.get("assignedTeams", []):
      if club.get("clubId") in clubs_with_primary:
        for team in club.get("teams", []):
          if team.get("licenseType") == LicenseTypeEnum.UNKNOWN:
            team["licenseType"] = LicenseTypeEnum.SECONDARY
            if settings.DEBUG_LEVEL > 0:
              logger.debug(
                  f"Set UNKNOWN license to SECONDARY in club with PRIMARY for player "
                  f"{player.get('firstName')} {player.get('lastName')}")

    # Step 8: Apply PRIMARY heuristic for remaining UNKNOWN licenses
    unknown_licenses = [(club, team) for club, team in all_licenses
                        if team.get("licenseType") == LicenseTypeEnum.UNKNOWN]

    # If exactly one UNKNOWN license remains, make it PRIMARY
    if len(unknown_licenses) == 1:
      club, team = unknown_licenses[0]
      team["licenseType"] = LicenseTypeEnum.PRIMARY
      if settings.DEBUG_LEVEL > 0:
        logger.debug(
            f"Set single UNKNOWN license to PRIMARY for player {player.get('firstName')} {player.get('lastName')}"
        )

    return player

  def _classify_single_license_by_age_group(
      self, player_age_group: str, team_age_group: str, player_is_overage: bool
  ) -> LicenseTypeEnum:
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
      LicenseTypeEnum (PRIMARY, OVERAGE, or SECONDARY)
    """
    if not player_age_group or not team_age_group:
      return LicenseTypeEnum.PRIMARY
    
    # Same age group -> PRIMARY
    if player_age_group == team_age_group:
      return LicenseTypeEnum.PRIMARY
    
    # Check WKO rules for age group relationship
    if player_age_group not in self._wko_rules:
      return LicenseTypeEnum.PRIMARY
    
    player_rule = self._wko_rules[player_age_group]
    
    # Check if this is an OVERAGE scenario (playing in younger age group)
    for overage_rule in player_rule.overAgeRules:
      if overage_rule.targetAgeGroup == team_age_group:
        return LicenseTypeEnum.OVERAGE
    
    # Check if this is a SECONDARY scenario (playing in older age group)
    for secondary_rule in player_rule.secondaryRules:
      if secondary_rule.targetAgeGroup == team_age_group:
        return LicenseTypeEnum.SECONDARY
    
    # Fallback to PRIMARY if no rule matches
    # Validation step will catch any age group violations
    return LicenseTypeEnum.PRIMARY

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
      if settings.DEBUG_LEVEL > 0:
        logger.debug(f"Classified license {pass_no} as DEVELOPMENT")
      return LicenseTypeEnum.DEVELOPMENT
    elif pass_no_normalized.endswith("A"):
      if settings.DEBUG_LEVEL > 0:
        logger.debug(f"Classified license {pass_no} as SECONDARY")
      return LicenseTypeEnum.SECONDARY
    elif pass_no_normalized.endswith("L"):
      if settings.DEBUG_LEVEL > 0:
        logger.debug(f"Classified license {pass_no} as LOAN")
      return LicenseTypeEnum.LOAN
    else:
      # No recognized suffix - leave as UNKNOWN
      # PRIMARY heuristic will handle single-license case
      return LicenseTypeEnum.UNKNOWN

  async def bootstrap_classification_for_all_players(self,
                                                     reset: bool = False,
                                                     batch_size: int = 1000
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

    logger.info(
        f"Starting bootstrap classification of all player licenses (reset={reset})..."
    )

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
              p["_id"], reset=reset)
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
      was_modified = await self._update_player_classification_in_db(
          p["_id"], reset=reset)
      if was_modified:
        modified_ids.append(str(p["_id"]))
        total_modified += 1

    logger.info(
        f"Classification bootstrap complete: processed {total_processed} players, "
        f"modified {total_modified} players")

    return modified_ids

  async def _update_player_classification_in_db(self,
                                                player_id: str,
                                                reset: bool = False) -> bool:
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
          team["licenseType"] = LicenseTypeEnum.UNKNOWN
          team["status"] = LicenseStatusEnum.UNKNOWN
          team["invalidReasonCodes"] = []

    # Apply classification
    player = await self.classify_license_types_for_player(player)

    # Check if anything changed
    new_assigned_teams = jsonable_encoder(player.get("assignedTeams", []))
    if original_assigned_teams == new_assigned_teams:
      return False

    # Persist changes
    await self.db["players"].update_one(
        {"_id": player_id}, {"$set": {
            "assignedTeams": new_assigned_teams
        }})

    logger.info(f"Updated license classifications for player {player_id}: "
                f"{player.get('firstName')} {player.get('lastName')}")
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

    # Step 3: Validate PRIMARY-like consistency
    self._validate_primary_like_consistency(player)

    # Step 3.5: Validate DEVELOPMENT uniqueness and redundancy
    self._validate_development_uniqueness_redundancy(player)

    # Step 4: Validate LOAN consistency
    self._validate_loan_consistency(player)

    # Step 5: Validate ISHD vs BISHL conflicts
    self._validate_import_conflicts(player)

    # Step 6: Determine primary club
    primary_club_id = self._get_primary_club_id(player)

    # Step 7: Validate club consistency for SECONDARY/OVERAGE
    if primary_club_id:
      self._validate_club_consistency(player, primary_club_id)

    # Step 8: Validate age group violations and OVERAGE rules
    # We need to create a PlayerDB instance for age group properties
    player_obj = PlayerDB(**player)
    self._validate_age_group_compliance(player, player_obj)

    # Step 9: Validate WKO license quotas (maxLicenses per target age group)
    self._validate_wko_license_quota(player, player_obj)

    # Step 10: Validate WKO limits (max participations)
    self._validate_wko_limits(player)

    # Step 11: Validate date sanity
    self._validate_date_sanity(player)

    # Step 12: Validate HOBBY exclusivity
    self._validate_hobby_exclusivity(player)

    # Step 13: Ensure no UNKNOWN status remains
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
        team["status"] = LicenseStatusEnum.VALID
        team["invalidReasonCodes"] = []

  def _validate_unknown_license_types(self, player: dict) -> None:
    """Mark licenses with UNKNOWN license type as INVALID (skip adminOverride=True)"""
    if not player.get("assignedTeams"):
      return

    for club in player["assignedTeams"]:
      for team in club.get("teams", []):
        if team.get("adminOverride"):
          continue
        if team.get("licenseType") == LicenseTypeEnum.UNKNOWN:
          team["status"] = LicenseStatusEnum.INVALID
          if LicenseInvalidReasonCode.UNKNOWN_LICENCE_TYPE not in team.get(
              "invalidReasonCodes", []):
            team.setdefault("invalidReasonCodes", []).append(
                LicenseInvalidReasonCode.UNKNOWN_LICENCE_TYPE)

  def _validate_primary_consistency(self, player: dict) -> None:
    """Validate that player has at most one PRIMARY license (skip adminOverride=True)"""
    if not player.get("assignedTeams"):
      return

    primary_licenses = []
    for club in player["assignedTeams"]:
      for team in club.get("teams", []):
        # Skip licenses with adminOverride=True
        if team.get("adminOverride"):
          continue
        if team.get("licenseType") == LicenseTypeEnum.PRIMARY:
          primary_licenses.append((club, team))

    if len(primary_licenses) > 1:
      # Mark all PRIMARY licenses as invalid
      for club, team in primary_licenses:
        team["status"] = LicenseStatusEnum.INVALID
        if LicenseInvalidReasonCode.MULTIPLE_PRIMARY not in team.get(
            "invalidReasonCodes", []):
          team.setdefault("invalidReasonCodes",
                          []).append(LicenseInvalidReasonCode.MULTIPLE_PRIMARY)

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
        if team.get("licenseType") == LicenseTypeEnum.LOAN:
          loan_licenses.append({
              "club": club,
              "team": team,
              "clubId": club.get("clubId"),
              "ageGroup": team.get("teamAgeGroup")
          })

    if not loan_licenses:
      return

    # Rule 1: At most one LOAN license
    if len(loan_licenses) > 1:
      for loan_info in loan_licenses:
        team = loan_info["team"]
        team["status"] = LicenseStatusEnum.INVALID
        if LicenseInvalidReasonCode.TOO_MANY_LOAN not in team.get(
            "invalidReasonCodes", []):
          team.setdefault("invalidReasonCodes",
                          []).append(LicenseInvalidReasonCode.TOO_MANY_LOAN)
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
        if team.get("licenseType") == LicenseTypeEnum.LOAN:
          continue
        # Any other license in the same club as LOAN is invalid
        team["status"] = LicenseStatusEnum.INVALID
        if LicenseInvalidReasonCode.LOAN_CLUB_CONFLICT not in team.get(
            "invalidReasonCodes", []):
          team.setdefault("invalidReasonCodes",
                          []).append(LicenseInvalidReasonCode.LOAN_CLUB_CONFLICT)

    # Rule 3: No other license in same age group as LOAN in other clubs
    for club in player["assignedTeams"]:
      if club.get("clubId") == loan_club_id:
        continue
      for team in club.get("teams", []):
        if team.get("teamAgeGroup") == loan_age_group:
          team["status"] = LicenseStatusEnum.INVALID
          if LicenseInvalidReasonCode.AGE_GROUP_VIOLATION not in team.get(
              "invalidReasonCodes", []):
            team.setdefault("invalidReasonCodes", []).append(
                LicenseInvalidReasonCode.AGE_GROUP_VIOLATION)

  def _validate_import_conflicts(self, player: dict) -> None:
    """Validate ISHD vs BISHL conflicts - ISHD never overrides BISHL (skip adminOverride=True)"""
    if not player.get("assignedTeams"):
      return

    # Collect BISHL licenses by type
    bishl_licenses = {}

    for club in player["assignedTeams"]:
      for team in club.get("teams", []):
        if team.get("adminOverride"):
          continue
        if team.get("source") == SourceEnum.BISHL and team.get(
            "status") == LicenseStatusEnum.VALID:
          license_type = team.get("licenseType")
          if license_type not in bishl_licenses:
            bishl_licenses[license_type] = set()
          bishl_licenses[license_type].add(team.get("teamId"))

    # Check ISHD licenses for conflicts
    for club in player["assignedTeams"]:
      for team in club.get("teams", []):
        if team.get("source") == SourceEnum.ISHD and team.get(
            "status") == LicenseStatusEnum.VALID:
          # If there's a BISHL license of the same type, mark ISHD as conflict
          license_type = team.get("licenseType")
          if license_type in bishl_licenses:
            # For PRIMARY, any BISHL PRIMARY conflicts
            if license_type == LicenseTypeEnum.PRIMARY:
              team["status"] = LicenseStatusEnum.INVALID
              if LicenseInvalidReasonCode.IMPORT_CONFLICT not in team.get(
                  "invalidReasonCodes", []):
                team.setdefault("invalidReasonCodes", []).append(
                    LicenseInvalidReasonCode.IMPORT_CONFLICT)

  def _get_anchor_license(self, player: dict) -> tuple[dict | None, dict | None]:
    """
    Determine the anchor license (PRIMARY or fallback) for a player.
    Priority 1: Valid PRIMARY.
    Priority 2a: Valid DEVELOPMENT (treat as fallback PRIMARY).
    Priority 2b: Single valid license (existing).
    """
    if not player.get("assignedTeams"):
      return None, None

    # Priority 1: Valid PRIMARY
    for club in player["assignedTeams"]:
      for team in club.get("teams", []):
        if (team.get("status") == LicenseStatusEnum.VALID
            and team.get("licenseType") == LicenseTypeEnum.PRIMARY):
          return club, team

    # Priority 2a: Valid DEVELOPMENT
    for club in player["assignedTeams"]:
      for team in club.get("teams", []):
        if (team.get("status") == LicenseStatusEnum.VALID
            and team.get("licenseType") == LicenseTypeEnum.DEVELOPMENT):
          return club, team

    # Priority 2b: Single valid license
    valid_licenses = []
    for club in player["assignedTeams"]:
      for team in club.get("teams", []):
        if team.get("status") == LicenseStatusEnum.VALID:
          valid_licenses.append((club, team))

    if len(valid_licenses) == 1:
      return valid_licenses[0]

    return None, None

  def _validate_primary_like_consistency(self, player: dict) -> None:
    """Validate that player has at most one PRIMARY-like license (skip adminOverride=True)"""
    if not player.get("assignedTeams"):
      return

    primary_like_licenses = []
    for club in player["assignedTeams"]:
      for team in club.get("teams", []):
        # Skip licenses with adminOverride=True
        if team.get("adminOverride"):
          continue
        if self._is_primary_like(team.get("licenseType")):
          primary_like_licenses.append((club, team))

    if len(primary_like_licenses) > 1:
      # Mark all PRIMARY-like licenses as invalid
      for club, team in primary_like_licenses:
        team["status"] = LicenseStatusEnum.INVALID
        if LicenseInvalidReasonCode.MULTIPLE_PRIMARY not in team.get(
            "invalidReasonCodes", []):
          team.setdefault("invalidReasonCodes",
                          []).append(LicenseInvalidReasonCode.MULTIPLE_PRIMARY)

  def _validate_development_uniqueness_redundancy(self, player: dict) -> None:
    """
    Validate DEVELOPMENT license uniqueness and redundancy within club/age group.
    - If PRIMARY exists in same club/age group -> DEVELOPMENT is REDUNDANT_DEVELOPMENT
    - If multiple DEVELOPMENT in same club/age group -> Keep first, others are MULTIPLE_DEVELOPMENT
    """
    if not player.get("assignedTeams"):
      return

    for club in player["assignedTeams"]:
      club_id = club.get("clubId")
      # Group by teamAgeGroup
      groups = {}
      for team in club.get("teams", []):
        if team.get("adminOverride"):
          continue
        age_group = team.get("teamAgeGroup")
        if age_group not in groups:
          groups[age_group] = {"primary": [], "development": []}
        
        if team.get("licenseType") == LicenseTypeEnum.PRIMARY:
          groups[age_group]["primary"].append(team)
        elif team.get("licenseType") == LicenseTypeEnum.DEVELOPMENT:
          groups[age_group]["development"].append(team)

      for age_group, group in groups.items():
        # Case 1: PRIMARY exists -> all DEVELOPMENT are redundant
        if group["primary"] and group["development"]:
          for dev_team in group["development"]:
            dev_team["status"] = LicenseStatusEnum.INVALID
            if LicenseInvalidReasonCode.REDUNDANT_DEVELOPMENT not in dev_team.get("invalidReasonCodes", []):
              dev_team.setdefault("invalidReasonCodes", []).append(LicenseInvalidReasonCode.REDUNDANT_DEVELOPMENT)
            logger.debug(f"Invalidated DEVELOPMENT due to redundant PRIMARY in club {club_id} age {age_group}")

        # Case 2: No PRIMARY but multiple DEVELOPMENT
        elif len(group["development"]) > 1:
          # Keep the first one, invalidate others
          for dev_team in group["development"][1:]:
            dev_team["status"] = LicenseStatusEnum.INVALID
            if LicenseInvalidReasonCode.MULTIPLE_DEVELOPMENT not in dev_team.get("invalidReasonCodes", []):
              dev_team.setdefault("invalidReasonCodes", []).append(LicenseInvalidReasonCode.MULTIPLE_DEVELOPMENT)
            logger.debug(f"Invalidated DEVELOPMENT due to multiple DEVELOPMENT in club {club_id} age {age_group}")

  def _get_primary_club_id(self, player: dict) -> str | None:
    """Get the club ID of the anchor license (PRIMARY or single valid license)"""
    anchor_club, anchor_team = self._get_anchor_license(player)
    if anchor_club:
      return anchor_club.get("clubId")
    return None

  def _validate_club_consistency(self, player: dict,
                                 primary_club_id: str) -> None:
    """Validate that SECONDARY and OVERAGE licenses belong to the primary club (skip adminOverride=True)"""
    if not player.get("assignedTeams"):
      return

    for club in player["assignedTeams"]:
      for team in club.get("teams", []):
        if team.get("adminOverride"):
          continue
        if team.get("licenseType") in [
            LicenseTypeEnum.SECONDARY, LicenseTypeEnum.OVERAGE
        ]:
          if club.get("clubId") != primary_club_id:
            team["status"] = LicenseStatusEnum.INVALID
            if LicenseInvalidReasonCode.CONFLICTING_CLUB not in team.get(
                "invalidReasonCodes", []):
              team.setdefault("invalidReasonCodes", []).append(
                  LicenseInvalidReasonCode.CONFLICTING_CLUB)

  def _validate_age_group_compliance(self, player: dict,
                                     player_obj: PlayerDB) -> None:
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
    is_anchor_only = (anchor_team is not None and 
                      anchor_team.get("licenseType") != LicenseTypeEnum.PRIMARY)

    # PASS 1: Validate PRIMARY licenses first
    for club in player["assignedTeams"]:
      for team in club.get("teams", []):
        if team.get("adminOverride"):
          continue
        if team.get("status") != LicenseStatusEnum.VALID:
          continue

        license_type = team.get("licenseType")
        if license_type != LicenseTypeEnum.PRIMARY:
          continue

        team_age_group = team.get("teamAgeGroup")
        if not self._is_age_group_compatible(player_age_group, team_age_group):
          team["status"] = LicenseStatusEnum.INVALID
          if LicenseInvalidReasonCode.AGE_GROUP_VIOLATION not in team.get(
              "invalidReasonCodes", []):
            team.setdefault("invalidReasonCodes", []).append(
                LicenseInvalidReasonCode.AGE_GROUP_VIOLATION)

    # PASS 2: Validate SECONDARY, OVERAGE, and LOAN licenses
    for club in player["assignedTeams"]:
      for team in club.get("teams", []):
        if team.get("adminOverride"):
          continue
        if team.get("status") != LicenseStatusEnum.VALID:
          continue

        team_age_group = team.get("teamAgeGroup")
        license_type = team.get("licenseType")
        
        # Check if this team is the anchor license
        is_this_anchor = (is_anchor_only and team is anchor_team)

        # Handle OVERAGE licenses
        if license_type == LicenseTypeEnum.OVERAGE:
          if not self._is_overage_allowed(player_age_group, team_age_group,
                                          player_is_overage,
                                          is_anchor_license=is_this_anchor):
            team["status"] = LicenseStatusEnum.INVALID
            if LicenseInvalidReasonCode.OVERAGE_NOT_ALLOWED not in team.get(
                "invalidReasonCodes", []):
              team.setdefault("invalidReasonCodes", []).append(
                  LicenseInvalidReasonCode.OVERAGE_NOT_ALLOWED)

        # Handle SECONDARY licenses
        elif license_type == LicenseTypeEnum.SECONDARY:
          if not self._is_secondary_allowed(player_age_group, team_age_group):
            team["status"] = LicenseStatusEnum.INVALID
            if LicenseInvalidReasonCode.AGE_GROUP_VIOLATION not in team.get(
                "invalidReasonCodes", []):
              team.setdefault("invalidReasonCodes", []).append(
                  LicenseInvalidReasonCode.AGE_GROUP_VIOLATION)

        # Handle LOAN licenses (similar to SECONDARY rules)
        elif license_type == LicenseTypeEnum.LOAN:
          if not self._is_secondary_allowed(player_age_group, team_age_group):
            team["status"] = LicenseStatusEnum.INVALID
            if LicenseInvalidReasonCode.AGE_GROUP_VIOLATION not in team.get(
                "invalidReasonCodes", []):
              team.setdefault("invalidReasonCodes", []).append(
                  LicenseInvalidReasonCode.AGE_GROUP_VIOLATION)

  def _is_overage_allowed(self, player_age_group: str, team_age_group: str,
                          player_is_overage: bool,
                          is_anchor_license: bool = False) -> bool:
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
    return any(over_age_rule.targetAgeGroup == team_age_group
               for over_age_rule in player_rule.overAgeRules)

  def _is_secondary_allowed(self, player_age_group: str,
                            team_age_group: str) -> bool:
    """Check if SECONDARY license in this age group is allowed"""
    if player_age_group not in self._wko_rules:
      return False

    player_rule = self._wko_rules[player_age_group]

    # SECONDARY can be in same age group or allowed play-up groups
    if team_age_group == player_age_group:
      return True

    return any(secondary_rule.targetAgeGroup == team_age_group
               for secondary_rule in player_rule.secondaryRules)

  def _is_age_group_compatible(self, player_age_group: str,
                               team_age_group: str) -> bool:
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
      allowed = any(secondary_rule.targetAgeGroup == team_age_group for secondary_rule in player_rule.secondaryRules)
      logger.debug(f"{player_age_group} is {'allowed' if allowed else 'NOT allowed'} to play up in {team_age_group}")
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
        if team.get("status") == LicenseStatusEnum.VALID:
          target_age_group = team.get("teamAgeGroup")
          if target_age_group not in result:
            result[target_age_group] = []
          result[target_age_group].append({"club": club, "team": team})
    
    return result

  def _get_max_licenses_for_age_group(self, player_age_group: str, 
                                       target_age_group: str,
                                       player_sex: SexEnum) -> int | None:
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
          player_age_group, target_age_group, player_sex)
      
      if max_licenses is not None and len(licenses) > max_licenses:
        # Mark excess licenses as invalid (keep first max_licenses)
        for entry in licenses[max_licenses:]:
          team = entry["team"]
          team["status"] = LicenseStatusEnum.INVALID
          if LicenseInvalidReasonCode.EXCEEDS_WKO_LIMIT not in team.get(
              "invalidReasonCodes", []):
            team.setdefault("invalidReasonCodes", []).append(
                LicenseInvalidReasonCode.EXCEEDS_WKO_LIMIT)
          logger.debug(f"Player {player_obj.firstName} {player_obj.lastName}: "
                       f"licenses in {target_age_group} exceeds quota "
                       f"({len(licenses)} > {max_licenses})")

  def _validate_wko_limits(self, player: dict) -> None:
    """Validate WKO limits on number of age class participations"""
    if not player.get("assignedTeams"):
      return

    # Get player details
    player_obj = PlayerDB(**player)
    player_age_group = player_obj.ageGroup
    player_sex = player_obj.sex

    # Check if player's age group is known
    if player_age_group not in self._wko_rules:
      return

    # Count valid participations by age group
    participations = []

    for club in player["assignedTeams"]:
      for team in club.get("teams", []):
        if (team.get("status") == LicenseStatusEnum.VALID
            and team.get("licenseType") in [
                LicenseTypeEnum.PRIMARY, LicenseTypeEnum.SECONDARY,
                LicenseTypeEnum.OVERAGE
            ]):
          participations.append((club, team, team.get("teamAgeGroup")))

    # If exceeds WKO limit, mark excess as invalid
    # Check if player's sex has maxTotalAgeClasses defined
    player_rule = self._wko_rules[player_age_group]
    max_participations_dict = player_rule.maxTotalAgeClasses or {}

    if player_sex not in max_participations_dict:
      # No limit defined for this sex, use default
      max_participations = self.MAX_AGE_CLASS_PARTICIPATIONS
    else:
      max_participations = max_participations_dict[player_sex]
      if max_participations is None:
        # None value means no limit
        return

    if len(participations) > max_participations:
      # Keep PRIMARY first, then sort by age group order
      def sort_key(item):
        club, team, age_group = item
        priority = 0 if team.get(
            "licenseType") == LicenseTypeEnum.PRIMARY else 1
        age_order = self._wko_rules[
            age_group].sortOrder if age_group in self._wko_rules else 999
        return (priority, age_order)

      participations.sort(key=sort_key)

      # Mark excess as invalid
      for club, team, _ in participations[max_participations:]:
        team["status"] = LicenseStatusEnum.INVALID
        if LicenseInvalidReasonCode.EXCEEDS_WKO_LIMIT not in team.get(
            "invalidReasonCodes", []):
          team.setdefault("invalidReasonCodes", []).append(
              LicenseInvalidReasonCode.EXCEEDS_WKO_LIMIT)

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
            team["status"] = LicenseStatusEnum.INVALID
            if LicenseInvalidReasonCode.IMPORT_CONFLICT not in team.get(
                "invalidReasonCodes", []):
              team.setdefault("invalidReasonCodes", []).append(
                  LicenseInvalidReasonCode.IMPORT_CONFLICT)

  def _validate_hobby_exclusivity(self, player: dict) -> None:
    """
    Validate that if a HOBBY team exists, no COMPETITIVE teams can exist.
    
    HOBBY teams are mutually exclusive with COMPETITIVE teams.
    """
    if not player.get("assignedTeams"):
      return

    # First, check if player has any HOBBY teams
    has_hobby = False
    hobby_teams = []

    for club in player["assignedTeams"]:
      for team in club.get("teams", []):
        if team.get("teamType") == "HOBBY":
          has_hobby = True
          hobby_teams.append((club, team))

    if not has_hobby:
      return

    # If HOBBY exists, check for conflicting COMPETITIVE teams
    for club in player["assignedTeams"]:
      for team in club.get("teams", []):
        team_type = team.get("teamType")

        # If this is a COMPETITIVE team, mark both HOBBY and COMPETITIVE as invalid
        if team_type == "COMPETITIVE":
          team["status"] = LicenseStatusEnum.INVALID
          if LicenseInvalidReasonCode.HOBBY_PLAYER_CONFLICT not in team.get(
              "invalidReasonCodes", []):
            team.setdefault("invalidReasonCodes", []).append(
                LicenseInvalidReasonCode.HOBBY_PLAYER_CONFLICT)

          # Also mark all HOBBY teams as invalid
          for hobby_club, hobby_team in hobby_teams:
            hobby_team["status"] = LicenseStatusEnum.INVALID
            if LicenseInvalidReasonCode.HOBBY_PLAYER_CONFLICT not in hobby_team.get(
                "invalidReasonCodes", []):
              hobby_team.setdefault("invalidReasonCodes", []).append(
                  LicenseInvalidReasonCode.HOBBY_PLAYER_CONFLICT)

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
        if team.get("status") == LicenseStatusEnum.UNKNOWN:
          if team.get("licenseType") == LicenseTypeEnum.UNKNOWN:
            # Cannot classify license type, mark as invalid
            team["status"] = LicenseStatusEnum.INVALID
            if LicenseInvalidReasonCode.UNKNOWN_LICENCE_TYPE not in team.get(
                "invalidReasonCodes", []):
              team.setdefault("invalidReasonCodes", []).append(
                  LicenseInvalidReasonCode.UNKNOWN_LICENCE_TYPE)
          else:
            # License type is known and no structural issues found
            team["status"] = LicenseStatusEnum.VALID

  async def bootstrap_validation_for_all_players(self,
                                                 reset: bool = False,
                                                 batch_size: int = 1000
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

    logger.info(
        f"Starting bootstrap validation of all player licenses (reset={reset})..."
    )

    # Process in batches to avoid memory issues
    cursor = self.db["players"].find({})
    batch = []

    async for player in cursor:
      batch.append(player)

      if len(batch) >= batch_size:
        # Process batch
        for p in batch:
          total_processed += 1
          was_modified = await self._update_player_validation_in_db(
              p["_id"], reset=reset)
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
      was_modified = await self._update_player_validation_in_db(p["_id"],
                                                                reset=reset)
      if was_modified:
        modified_ids.append(str(p["_id"]))
        total_modified += 1

    logger.info(
        f"Validation bootstrap complete: processed {total_processed} players, "
        f"modified {total_modified} players")

    return modified_ids

  async def _update_player_validation_in_db(self,
                                            player_id: str,
                                            reset: bool = False) -> bool:
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
          team["status"] = LicenseStatusEnum.UNKNOWN
          team["invalidReasonCodes"] = []

    # Apply validation
    player = await self.validate_licenses_for_player(player)

    # Check if anything changed
    new_assigned_teams = jsonable_encoder(player.get("assignedTeams", []))
    if original_assigned_teams == new_assigned_teams:
      return False

    # Persist changes
    await self.db["players"].update_one(
        {"_id": player_id}, {"$set": {
            "assignedTeams": new_assigned_teams
        }})

    logger.info(f"Updated license validations for player {player_id}: "
                f"{player.get('firstName')} {player.get('lastName')}")
    return True

  # ========================================================================
  # ORCHESTRATION METHODS
  # ========================================================================

  async def bootstrap_all_players(self,
                                  reset_classification: bool = False,
                                  reset_validation: bool = False,
                                  batch_size: int = 1000) -> dict:
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
        reset=reset_classification, batch_size=batch_size)

    # Step 2: Validation
    validation_modified = await self.bootstrap_validation_for_all_players(
        reset=reset_validation, batch_size=batch_size)

    # Get statistics
    stats = await self.get_classification_stats()

    logger.info("Full bootstrap complete")

    return {
        "classification_modified_count": len(classification_modified),
        "classification_modified_ids":
        classification_modified[:100],  # First 100 IDs
        "validation_modified_count": len(validation_modified),
        "validation_modified_ids": validation_modified[:100],  # First 100 IDs
        "stats": stats,
    }

  # ========================================================================
  # HELPER METHODS
  # ========================================================================

  async def apply_heuristics_for_imported_player(self,
                                                 player_doc: dict) -> dict:
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
          stats["by_type"][license_type] = stats["by_type"].get(
              license_type, 0) + 1

          status = team.get("status", LicenseStatusEnum.UNKNOWN)
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
            LicenseStatusEnum.VALID: 0,
            LicenseStatusEnum.INVALID: 0,
        },
        "by_invalidReasonCodes": {},
    }

    async for player in self.db["players"].find({}):
      for club in player.get("assignedTeams", []):
        for team in club.get("teams", []):
          stats["total_licenses"] += 1

          # Count by status
          status = team.get("status", LicenseStatusEnum.VALID)
          if status in stats["by_status"]:
            stats["by_status"][status] += 1
          else:
            stats["by_status"][status] = 1

          # Count by invalid reason codes
          if status == LicenseStatusEnum.INVALID:
            reason_codes = team.get("invalidReasonCodes", [])
            for code in reason_codes:
              stats["by_invalidReasonCodes"][code] = (
                  stats["by_invalidReasonCodes"].get(code, 0) + 1)

    return stats
