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
      ),
      WkoRule(
          ageGroup="DAMEN",
          label="Damen",
          sortOrder=2,
          altKey="Damen",
          sex=[SexEnum.FEMALE],
          secondaryRules=[
              SecondaryRule(targetAgeGroup="HERREN",
                            sex=[SexEnum.FEMALE],
                            maxLicenses=1)
          ],
          overAgeRules=[
              OverAgeRule(targetAgeGroup="U19",
                          sex=[SexEnum.FEMALE],
                          maxLicenses=1,
                          maxOverAgePlayersPerTeam=3)
          ],
      ),
      WkoRule(ageGroup="U19",
              label="U19",
              sortOrder=3,
              altKey="Junioren",
              sex=[SexEnum.MALE, SexEnum.FEMALE],
              secondaryRules=[
                  SecondaryRule(targetAgeGroup="HERREN",
                                sex=[SexEnum.MALE, SexEnum.FEMALE],
                                maxLicenses=1),
                  SecondaryRule(targetAgeGroup="DAMEN",
                                sex=[SexEnum.FEMALE],
                                maxLicenses=1)
              ],
              overAgeRules=[
                  OverAgeRule(targetAgeGroup="U17",
                              sex=[SexEnum.MALE, SexEnum.FEMALE],
                              maxLicenses=1,
                              maxOverAgePlayersPerTeam=3)
              ]),
      WkoRule(ageGroup="U16",
              label="U16",
              sortOrder=4,
              altKey="Jugend",
              sex=[SexEnum.MALE, SexEnum.FEMALE],
              secondaryRules=[
                  SecondaryRule(targetAgeGroup="U19",
                                sex=[SexEnum.MALE, SexEnum.FEMALE],
                                maxLicenses=1),
                  SecondaryRule(targetAgeGroup="HERREN",
                                sex=[SexEnum.MALE],
                                maxLicenses=1),
                  SecondaryRule(targetAgeGroup="DAMEN",
                                sex=[SexEnum.FEMALE],
                                maxLicenses=1),
              ],
              overAgeRules=[
                  OverAgeRule(targetAgeGroup="U13",
                              sex=[SexEnum.MALE, SexEnum.FEMALE],
                              maxLicenses=1,
                              maxOverAgePlayersPerTeam=3)
              ]),
      WkoRule(ageGroup="U13",
              label="U13",
              sortOrder=5,
              altKey="Schüler",
              sex=[SexEnum.MALE, SexEnum.FEMALE],
              secondaryRules=[
                  SecondaryRule(targetAgeGroup="U16",
                                sex=[SexEnum.MALE, SexEnum.FEMALE],
                                maxLicenses=1)
              ],
              overAgeRules=[
                  OverAgeRule(targetAgeGroup="U10",
                              sex=[SexEnum.MALE, SexEnum.FEMALE],
                              maxLicenses=1,
                              maxOverAgePlayersPerTeam=3)
              ]),
      WkoRule(ageGroup="U10",
              label="U10",
              sortOrder=6,
              altKey="Bambini",
              sex=[SexEnum.MALE, SexEnum.FEMALE],
              secondaryRules=[
                  SecondaryRule(targetAgeGroup="U13",
                                sex=[SexEnum.MALE, SexEnum.FEMALE],
                                maxLicenses=1)
              ],
              overAgeRules=[
                  OverAgeRule(targetAgeGroup="U8",
                              sex=[SexEnum.MALE, SexEnum.FEMALE],
                              maxLicenses=1,
                              maxOverAgePlayersPerTeam=2)
              ]),
      WkoRule(ageGroup="U8",
              label="U8",
              sortOrder=7,
              altKey="Mini",
              sex=[SexEnum.MALE, SexEnum.FEMALE],
              secondaryRules=[
                  SecondaryRule(targetAgeGroup="U10",
                                sex=[SexEnum.MALE, SexEnum.FEMALE],
                                maxLicenses=1)
              ])
  ]

  # Maximum number of active age class participations allowed by WKO
  # TODO: maybe add to WKO_RULES
  MAX_AGE_CLASS_PARTICIPATIONS = 2

  def __init__(self, db):
    self.db = db
    # Build age group map from WKO_RULES, converting WkoRule instances to dicts
    self._age_group_map = {rule.ageGroup: rule.model_dump() for rule in self.WKO_RULES}

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
    if len(all_licenses) == 1:
      club, team = all_licenses[0]
      team["licenseType"] = LicenseTypeEnum.PRIMARY
      if settings.DEBUG_LEVEL > 0:
        logger.debug(
            f"Set single license to PRIMARY for player {player.get('firstName')} {player.get('lastName')}"
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
    if player_age_group in self._age_group_map:
      player_rule = self._age_group_map[player_age_group]
      player_sort_order = player_rule["sortOrder"]

      for club, team in all_licenses:
        # Only check UNKNOWN licenses
        if team.get("licenseType") == LicenseTypeEnum.UNKNOWN:
          team_age_group = team.get("teamAgeGroup")
          if not team_age_group or team_age_group not in self._age_group_map:
            continue

          team_rule = self._age_group_map[team_age_group]
          team_sort_order = team_rule["sortOrder"]

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
    Returns the modified player dict; does not persist to database.
    
    Args:
      player: Raw player dict from MongoDB (including assignedTeams)
      
    Returns:
      Modified player dict
    """
    if not player.get("assignedTeams"):
      return player

    # Step 1: Reset all license states to VALID with empty codes
    self._reset_license_validation_states(player)

    # Step 2: Validate UNKNOWN license types
    self._validate_unknown_license_types(player)

    # Step 3: Validate PRIMARY consistency
    self._validate_primary_consistency(player)

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

    # Step 9: Validate WKO limits (max participations)
    self._validate_wko_limits(player)

    # Step 10: Validate date sanity
    self._validate_date_sanity(player)

    # Step 11: Validate HOBBY exclusivity
    self._validate_hobby_exclusivity(player)

    # Step 12: Ensure no UNKNOWN status remains
    self._enforce_no_unknown_status(player)

    return player

  def _reset_license_validation_states(self, player: dict) -> None:
    """Reset all licenses to VALID with empty invalidReasonCodes"""
    if not player.get("assignedTeams"):
      return

    for club in player["assignedTeams"]:
      for team in club.get("teams", []):
        team["status"] = LicenseStatusEnum.VALID
        team["invalidReasonCodes"] = []

  def _validate_unknown_license_types(self, player: dict) -> None:
    """Mark licenses with UNKNOWN license type as INVALID"""
    if not player.get("assignedTeams"):
      return

    for club in player["assignedTeams"]:
      for team in club.get("teams", []):
        if team.get("licenseType") == LicenseTypeEnum.UNKNOWN:
          team["status"] = LicenseStatusEnum.INVALID
          if LicenseInvalidReasonCode.UNKNOWN_LICENCE_TYPE not in team.get(
              "invalidReasonCodes", []):
            team.setdefault("invalidReasonCodes", []).append(
                LicenseInvalidReasonCode.UNKNOWN_LICENCE_TYPE)

  def _validate_primary_consistency(self, player: dict) -> None:
    """Validate that player has at most one PRIMARY license"""
    if not player.get("assignedTeams"):
      return

    primary_licenses = []
    for club in player["assignedTeams"]:
      for team in club.get("teams", []):
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
    """Validate that player has at most one LOAN license"""
    if not player.get("assignedTeams"):
      return

    loan_licenses = []
    for club in player["assignedTeams"]:
      for team in club.get("teams", []):
        if (team.get("licenseType") == LicenseTypeEnum.LOAN):
          loan_licenses.append((club, team))

    if len(loan_licenses) > 1:
      # Mark all LOAN licenses as invalid
      for club, team in loan_licenses:
        team["status"] = LicenseStatusEnum.INVALID
        if LicenseInvalidReasonCode.TOO_MANY_LOAN not in team.get(
            "invalidReasonCodes", []):
          team.setdefault("invalidReasonCodes",
                          []).append(LicenseInvalidReasonCode.TOO_MANY_LOAN)

  def _validate_import_conflicts(self, player: dict) -> None:
    """Validate ISHD vs BISHL conflicts - ISHD never overrides BISHL"""
    if not player.get("assignedTeams"):
      return

    # Collect BISHL licenses by type
    bishl_licenses = {}

    for club in player["assignedTeams"]:
      for team in club.get("teams", []):
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

  def _get_primary_club_id(self, player: dict) -> str | None:
    """Get the club ID of the valid PRIMARY license"""
    if not player.get("assignedTeams"):
      return None

    for club in player["assignedTeams"]:
      for team in club.get("teams", []):
        if (team.get("licenseType") == LicenseTypeEnum.PRIMARY
            and team.get("status") == LicenseStatusEnum.VALID):
          return club.get("clubId")

    return None

  def _validate_club_consistency(self, player: dict,
                                 primary_club_id: str) -> None:
    """Validate that SECONDARY and OVERAGE licenses belong to the primary club"""
    if not player.get("assignedTeams"):
      return

    for club in player["assignedTeams"]:
      for team in club.get("teams", []):
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
    """Validate age group compliance and OVERAGE rules"""
    if not player.get("assignedTeams"):
      return

    player_age_group = player_obj.ageGroup
    player_is_overage = player_obj.overAge

    for club in player["assignedTeams"]:
      for team in club.get("teams", []):
        if team.get("status") != LicenseStatusEnum.VALID:
          continue

        team_age_group = team.get("teamAgeGroup")
        license_type = team.get("licenseType")

        # Handle OVERAGE licenses
        if license_type == LicenseTypeEnum.OVERAGE:
          if not self._is_overage_allowed(player_age_group, team_age_group,
                                          player_is_overage):
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

        # Handle PRIMARY licenses
        elif license_type == LicenseTypeEnum.PRIMARY:
          if not self._is_age_group_compatible(player_age_group,
                                               team_age_group):
            team["status"] = LicenseStatusEnum.INVALID
            if LicenseInvalidReasonCode.AGE_GROUP_VIOLATION not in team.get(
                "invalidReasonCodes", []):
              team.setdefault("invalidReasonCodes", []).append(
                  LicenseInvalidReasonCode.AGE_GROUP_VIOLATION)

  def _is_overage_allowed(self, player_age_group: str, team_age_group: str,
                          player_is_overage: bool) -> bool:
    """Check if OVERAGE license is allowed based on WKO rules"""
    if not player_is_overage:
      return False

    if player_age_group not in self._age_group_map:
      return False

    player_rule = self._age_group_map[player_age_group]
    return team_age_group in player_rule.get("canPlayOverAgeIn", [])

  def _is_secondary_allowed(self, player_age_group: str,
                            team_age_group: str) -> bool:
    """Check if SECONDARY license in this age group is allowed"""
    if player_age_group not in self._age_group_map:
      return False

    player_rule = self._age_group_map[player_age_group]

    # SECONDARY can be in same age group or allowed play-up groups
    if team_age_group == player_age_group:
      return True

    return team_age_group in player_rule.get("canAlsoPlayIn", [])

  def _is_age_group_compatible(self, player_age_group: str,
                               team_age_group: str) -> bool:
    """Check if player can play in the team's age group"""
    if player_age_group not in self._age_group_map or team_age_group not in self._age_group_map:
      return True  # Unknown age groups - allow for now

    player_rule = self._age_group_map[player_age_group]
    team_rule = self._age_group_map[team_age_group]

    # Same age group is always OK
    if player_age_group == team_age_group:
      return True

    # Playing up (younger player in older group) is OK if in canAlsoPlayIn
    if team_rule["sortOrder"] < player_rule["sortOrder"]:
      return team_age_group in player_rule.get("canAlsoPlayIn", [])

    # Playing down (older player in younger group) is not allowed without OVERAGE
    return False

  def _validate_wko_limits(self, player: dict) -> None:
    """Validate WKO limits on number of age class participations"""
    if not player.get("assignedTeams"):
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
    if len(participations) > self.MAX_AGE_CLASS_PARTICIPATIONS:
      # Keep PRIMARY first, then sort by age group order
      def sort_key(item):
        club, team, age_group = item
        priority = 0 if team.get(
            "licenseType") == LicenseTypeEnum.PRIMARY else 1
        age_order = self._age_group_map.get(age_group,
                                            {"sortOrder": 999})["sortOrder"]
        return (priority, age_order)

      participations.sort(key=sort_key)

      # Mark excess as invalid
      for club, team, _ in participations[self.MAX_AGE_CLASS_PARTICIPATIONS:]:
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
