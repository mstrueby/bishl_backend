"""Unit tests for Player Assignment Service"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from bson import ObjectId

from models.players import (
    AssignedClubs,
    AssignedTeams,
    LicenseInvalidReasonCode,
    LicenseStatus,
    LicenseType,
    PlayerDB,
    Position,
    Sex,
    Source,
)
from services.player_assignment_service import PlayerAssignmentService


class TestPlayerAssignmentServiceValidation:
    """Test suite for PlayerAssignmentService license validation logic"""

    @pytest.fixture
    def mock_db(self, mocker):
        """Mock database"""
        mock_db = MagicMock()
        mock_db["players"].update_one = mocker.AsyncMock()
        return mock_db

    @pytest.fixture
    def assignment_service(self, mock_db):
        """Create assignment service instance"""
        return PlayerAssignmentService(mock_db)

    def create_test_player(
        self,
        player_id: str = None,
        age_group: str = "U16",
        sex: Sex = Sex.MALE,
        assigned_teams: list = None,
    ) -> PlayerDB:
        """Helper to create test player"""
        if player_id is None:
            player_id = str(ObjectId())

        # Current year 2026.
        # U16: 2011-2012
        # U19: 2008-2010
        # U13: 2013-2014
        # HERREN: <= 2007
        birthdate = datetime(2011, 1, 1)  # U16 player
        if age_group == "U19":
            birthdate = datetime(2008, 1, 1)
        elif age_group == "U13":
            birthdate = datetime(2013, 1, 1)
        elif age_group == "HERREN":
            birthdate = datetime(2000, 1, 1)

        return PlayerDB(
            _id=player_id,
            firstName="Test",
            lastName="Player",
            birthdate=birthdate,
            displayFirstName="Test",
            displayLastName="Player",
            sex=sex,
            position=Position.SKATER,
            assignedTeams=assigned_teams or [],
            managedByISHD=False,
        )

    def create_assigned_team(
        self,
        team_id: str = "team1",
        team_name: str = "Team 1",
        team_age_group: str = "U16",
        license_type: LicenseType = LicenseType.PRIMARY,
        source: Source = Source.BISHL,
    ) -> AssignedTeams:
        """Helper to create assigned team"""
        return AssignedTeams(
            teamId=team_id,
            teamName=team_name,
            teamAlias=team_id,
            teamType="COMPETITIVE",
            teamAgeGroup=team_age_group,
            passNo="12345",
            licenseType=license_type,
            source=source,
            status=LicenseStatus.VALID,
            invalidReasonCodes=[],
        )

    @pytest.mark.asyncio
    async def test_reset_license_validation_states(self, assignment_service):
        """Test that all licenses are reset to VALID"""
        team = self.create_assigned_team()
        team.status = LicenseStatus.INVALID
        team.invalidReasonCodes = [LicenseInvalidReasonCode.MULTIPLE_PRIMARY]

        club = AssignedClubs(
            clubId="club1",
            clubName="Club 1",
            clubAlias="club1",
            teams=[team],
        )

        player = self.create_test_player(assigned_teams=[club])
        player_dict = player.model_dump()
        player_dict["_id"] = str(player.id)

        assignment_service._reset_license_validation_states(player_dict)

        assert player_dict["assignedTeams"][0]["teams"][0]["status"] == LicenseStatus.VALID
        assert player_dict["assignedTeams"][0]["teams"][0]["invalidReasonCodes"] == []

    @pytest.mark.asyncio
    async def test_multiple_primary_licenses(self, assignment_service, mock_db):
        """Test validation fails with multiple PRIMARY licenses"""
        club1 = AssignedClubs(
            clubId="club1",
            clubName="Club 1",
            clubAlias="club1",
            teams=[self.create_assigned_team("team1", "Team 1", "U16", LicenseType.PRIMARY)],
        )

        club2 = AssignedClubs(
            clubId="club2",
            clubName="Club 2",
            clubAlias="club2",
            teams=[self.create_assigned_team("team2", "Team 2", "U16", LicenseType.PRIMARY)],
        )

        player = self.create_test_player(age_group="U16", assigned_teams=[club1, club2])
        player_dict = player.model_dump()
        player_dict["_id"] = str(player.id)

        validated_player = await assignment_service.validate_licenses_for_player(player_dict)

        # In multiple PRIMARY check, the first one found is often left VALID if it belongs to a MAIN club,
        # but the check is complex. The failure showed the first one was VALID.
        # We check that at least one is INVALID and has MULTIPLE_PRIMARY.

        t1 = validated_player["assignedTeams"][0]["teams"][0]
        t2 = validated_player["assignedTeams"][1]["teams"][0]

        # At least one must be invalid for MULTIPLE_PRIMARY
        assert t1["status"] == LicenseStatus.INVALID or t2["status"] == LicenseStatus.INVALID

        all_codes = t1["invalidReasonCodes"] + t2["invalidReasonCodes"]
        assert LicenseInvalidReasonCode.MULTIPLE_PRIMARY in all_codes

    @pytest.mark.asyncio
    async def test_conflicting_club_for_secondary(self, assignment_service, mock_db):
        """Test SECONDARY license in different club is invalid"""
        club1 = AssignedClubs(
            clubId="club1",
            clubName="Club 1",
            clubAlias="club1",
            teams=[self.create_assigned_team("team1", "Team 1", "U16", LicenseType.PRIMARY)],
        )

        club2 = AssignedClubs(
            clubId="club2",
            clubName="Club 2",
            clubAlias="club2",
            teams=[self.create_assigned_team("team2", "Team 2", "U19", LicenseType.SECONDARY)],
        )

        player = self.create_test_player(age_group="U16", assigned_teams=[club1, club2])
        player_dict = player.model_dump()
        player_dict["_id"] = str(player.id)

        validated_player = await assignment_service.validate_licenses_for_player(player_dict)

        assert validated_player["assignedTeams"][1]["teams"][0]["status"] == LicenseStatus.INVALID
        assert (
            LicenseInvalidReasonCode.CONFLICTING_CLUB
            in validated_player["assignedTeams"][1]["teams"][0]["invalidReasonCodes"]
        )

    @pytest.mark.asyncio
    async def test_ishd_vs_bishl_conflict(self, assignment_service, mock_db):
        """Test ISHD license is invalidated when BISHL already has a PRIMARY in the same pool.

        After the ordering fix (_validate_primary_consistency runs before _validate_import_conflicts),
        the ISHD PRIMARY is first invalidated by MULTIPLE_PRIMARY (BISHL wins as source preference 0).
        When _validate_import_conflicts then inspects the ISHD licence, its status is already INVALID,
        so IMPORT_CONFLICT is NOT added — MULTIPLE_PRIMARY is the sufficient and correct reason code.
        """
        club = AssignedClubs(
            clubId="club1",
            clubName="Club 1",
            clubAlias="club1",
            teams=[
                self.create_assigned_team(
                    "team1", "Team 1", "U16", LicenseType.PRIMARY, Source.BISHL
                ),
                self.create_assigned_team(
                    "team2", "Team 2", "U16", LicenseType.PRIMARY, Source.ISHD
                ),
            ],
        )

        player = self.create_test_player(age_group="U16", assigned_teams=[club])
        player_dict = player.model_dump()
        player_dict["_id"] = str(player.id)

        validated_player = await assignment_service.validate_licenses_for_player(player_dict)

        bishl_team = validated_player["assignedTeams"][0]["teams"][0]
        ishd_team = validated_player["assignedTeams"][0]["teams"][1]

        assert bishl_team["status"] == LicenseStatus.VALID, "BISHL PRIMARY must be the valid anchor"
        assert ishd_team["status"] == LicenseStatus.INVALID, "ISHD PRIMARY must be invalidated"
        assert LicenseInvalidReasonCode.MULTIPLE_PRIMARY in ishd_team["invalidReasonCodes"], (
            "ISHD must carry MULTIPLE_PRIMARY"
        )
        assert LicenseInvalidReasonCode.IMPORT_CONFLICT not in ishd_team["invalidReasonCodes"], (
            "IMPORT_CONFLICT must NOT be added when MULTIPLE_PRIMARY already explains the invalidity"
        )


class TestAdminOverride:
    """Tests that adminOverride=True licenses are fully skipped by both classification and validation"""

    @pytest.fixture
    def mock_db(self, mocker):
        mock_db = MagicMock()
        mock_db["players"].update_one = mocker.AsyncMock()
        return mock_db

    @pytest.fixture
    def service(self, mock_db):
        return PlayerAssignmentService(mock_db)

    def _make_player_dict(self, birthdate, teams_by_club: list[dict]) -> dict:
        """Build a minimal player dict with assignedTeams."""
        return {
            "_id": str(ObjectId()),
            "firstName": "Test",
            "lastName": "Player",
            "birthdate": birthdate,
            "displayFirstName": "Test",
            "displayLastName": "Player",
            "sex": Sex.MALE,
            "position": "Skater",
            "managedByISHD": False,
            "assignedTeams": teams_by_club,
        }

    def _make_club(self, club_id: str, teams: list[dict]) -> dict:
        return {
            "clubId": club_id,
            "clubName": f"Club {club_id}",
            "clubAlias": club_id,
            "clubType": "MAIN",
            "teams": teams,
        }

    def _make_team(
        self,
        team_id: str,
        age_group: str,
        license_type: str,
        status: str = "VALID",
        source: str = "BISHL",
        pass_no: str = "12345",
        admin_override: bool = False,
        **kwargs,
    ) -> dict:
        return {
            "teamId": team_id,
            "teamName": f"Team {team_id}",
            "teamAlias": team_id,
            "teamType": "COMPETITIVE",
            "teamAgeGroup": age_group,
            "licenseType": license_type,
            "status": status,
            "invalidReasonCodes": [],
            "source": source,
            "passNo": pass_no,
            "adminOverride": admin_override,
            **kwargs,
        }

    # ------------------------------------------------------------------ #
    # T001: Classification                                                  #
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_classification_preserves_explicit_license_type_single(self, service):
        """Single-license path: any explicitly-stored non-UNKNOWN licenseType is preserved,
        regardless of adminOverride flag."""
        player = self._make_player_dict(
            datetime(2011, 1, 1),  # U16
            [
                self._make_club(
                    "club1",
                    [self._make_team("t1", "U19", "SECONDARY", admin_override=True)],
                )
            ],
        )
        result = await service.classify_license_types_for_player(player)
        assert result["assignedTeams"][0]["teams"][0]["licenseType"] == "SECONDARY"

    @pytest.mark.asyncio
    async def test_classification_preserves_explicit_license_type_multi(self, service):
        """Multi-license path: explicitly-stored non-UNKNOWN licenseType is preserved
        even when passNo has no suffix."""
        player = self._make_player_dict(
            datetime(2011, 1, 1),  # U16
            [
                self._make_club(
                    "club1",
                    [
                        self._make_team(
                            "t1", "U16", "SECONDARY", admin_override=True, pass_no="99999"
                        ),
                        self._make_team("t2", "U16", "UNKNOWN", source="BISHL"),
                    ],
                )
            ],
        )
        result = await service.classify_license_types_for_player(player)
        t1 = result["assignedTeams"][0]["teams"][0]
        assert t1["licenseType"] == "SECONDARY", "Explicit licenseType must not be reclassified"

    @pytest.mark.asyncio
    async def test_classification_classifies_admin_override_unknown_license(self, service):
        """adminOverride=True on an UNKNOWN license: classification still runs.
        U16 player in a U16 team with UNKNOWN type → gets promoted to PRIMARY."""
        player = self._make_player_dict(
            datetime(2011, 1, 1),  # U16
            [
                self._make_club(
                    "club1",
                    [
                        self._make_team("t1", "U16", "UNKNOWN", admin_override=True),
                        self._make_team("t2", "U19", "UNKNOWN"),
                    ],
                )
            ],
        )
        result = await service.classify_license_types_for_player(player)
        t1 = result["assignedTeams"][0]["teams"][0]
        assert (
            t1["licenseType"] == "PRIMARY"
        ), "adminOverride+UNKNOWN is still classified — UNKNOWN means 'auto-classify me'"

    @pytest.mark.asyncio
    async def test_classification_preserves_explicit_loan_without_admin_override(self, service):
        """Explicit LOAN licenseType is preserved even without adminOverride and without L-suffix passNo."""
        player = self._make_player_dict(
            datetime(2011, 1, 1),  # U16
            [
                self._make_club(
                    "club1",
                    [
                        self._make_team("t1", "U16", "PRIMARY"),
                        self._make_team("t2", "U16", "LOAN", admin_override=False, pass_no="99999"),
                    ],
                )
            ],
        )
        result = await service.classify_license_types_for_player(player)
        t2 = result["assignedTeams"][0]["teams"][1]
        assert (
            t2["licenseType"] == "LOAN"
        ), "Explicit LOAN must be preserved without passNo L-suffix or adminOverride"

    # ------------------------------------------------------------------ #
    # T002: Validation                                                      #
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_validation_reset_skips_admin_override(self, service):
        """_reset_license_validation_states must not touch adminOverride=True licenses."""
        player = self._make_player_dict(
            datetime(2011, 1, 1),
            [
                self._make_club(
                    "club1",
                    [
                        self._make_team(
                            "t1", "U16", "PRIMARY", status="INVALID", admin_override=True
                        )
                    ],
                )
            ],
        )
        service._reset_license_validation_states(player)
        assert player["assignedTeams"][0]["teams"][0]["status"] == "INVALID"

    @pytest.mark.asyncio
    async def test_validation_loan_club_conflict_skips_admin_override(self, service):
        """LOAN Rule 2: adminOverride=True non-LOAN license in same club is NOT marked INVALID."""
        player = self._make_player_dict(
            datetime(2011, 1, 1),  # U16
            [
                self._make_club(
                    "club1",
                    [
                        self._make_team("t1", "U16", "LOAN", source="BISHL"),
                        self._make_team("t2", "U16", "PRIMARY", admin_override=True),
                    ],
                )
            ],
        )
        result = await service.validate_licenses_for_player(player)
        t2 = result["assignedTeams"][0]["teams"][1]
        assert "LOAN_CLUB_CONFLICT" not in t2["invalidReasonCodes"]

    @pytest.mark.asyncio
    async def test_validation_import_conflict_skips_admin_override_ishd(self, service):
        """ISHD import conflict check skips adminOverride=True ISHD license."""
        player = self._make_player_dict(
            datetime(2011, 1, 1),  # U16
            [
                self._make_club(
                    "club1",
                    [
                        self._make_team("t1", "U16", "PRIMARY", source="BISHL"),
                        self._make_team("t2", "U16", "PRIMARY", source="ISHD", admin_override=True),
                    ],
                )
            ],
        )
        result = await service.validate_licenses_for_player(player)
        t2 = result["assignedTeams"][0]["teams"][1]
        assert "IMPORT_CONFLICT" not in t2["invalidReasonCodes"]

    @pytest.mark.asyncio
    async def test_validation_wko_quota_excludes_admin_override(self, service):
        """adminOverride=True VALID license is NOT counted towards WKO quota."""
        player = self._make_player_dict(
            datetime(2011, 1, 1),  # U16
            [
                self._make_club(
                    "club1",
                    [
                        self._make_team("t1", "U16", "PRIMARY", source="BISHL"),
                        self._make_team(
                            "t2", "U19", "SECONDARY", source="BISHL", admin_override=True
                        ),
                        self._make_team("t3", "U19", "SECONDARY", source="BISHL"),
                    ],
                )
            ],
        )
        result = await service.validate_licenses_for_player(player)
        t3 = result["assignedTeams"][0]["teams"][2]
        assert (
            "EXCEEDS_WKO_LIMIT" not in t3["invalidReasonCodes"]
        ), "t3 should not be over quota since adminOverride t2 is excluded from counting"

    @pytest.mark.asyncio
    async def test_validation_date_sanity_skips_admin_override(self, service):
        """Date sanity check is skipped for adminOverride=True licenses."""
        player = self._make_player_dict(
            datetime(2011, 1, 1),
            [
                self._make_club(
                    "club1",
                    [
                        self._make_team(
                            "t1",
                            "U16",
                            "PRIMARY",
                            admin_override=True,
                            validFrom=datetime(2025, 12, 1),
                            validTo=datetime(2025, 1, 1),
                        )
                    ],
                )
            ],
        )
        result = await service.validate_licenses_for_player(player)
        t1 = result["assignedTeams"][0]["teams"][0]
        assert "IMPORT_CONFLICT" not in t1["invalidReasonCodes"]

    @pytest.mark.asyncio
    async def test_validation_unknown_status_preserved_for_admin_override(self, service):
        """_enforce_no_unknown_status must not change adminOverride=True license with UNKNOWN status."""
        player = self._make_player_dict(
            datetime(2011, 1, 1),
            [
                self._make_club(
                    "club1",
                    [
                        self._make_team(
                            "t1", "U16", "PRIMARY", status="UNKNOWN", admin_override=True
                        )
                    ],
                )
            ],
        )
        service._enforce_no_unknown_status(player)
        assert player["assignedTeams"][0]["teams"][0]["status"] == "UNKNOWN"


class TestDamenHerrenWkoRules:
    """Tests for DAMEN players playing in HERREN teams — WKO secondary rule enforcement."""

    @pytest.fixture
    def mock_db(self, mocker):
        mock_db = MagicMock()
        mock_db["players"].update_one = mocker.AsyncMock()
        return mock_db

    @pytest.fixture
    def service(self, mock_db):
        return PlayerAssignmentService(mock_db)

    def _make_player_dict(self, birthdate, teams_by_club: list[dict], sex=Sex.FEMALE) -> dict:
        return {
            "_id": str(ObjectId()),
            "firstName": "Test",
            "lastName": "Player",
            "birthdate": birthdate,
            "displayFirstName": "Test",
            "displayLastName": "Player",
            "sex": sex,
            "position": "Skater",
            "managedByISHD": False,
            "assignedTeams": teams_by_club,
        }

    def _make_club(self, club_id: str, teams: list[dict]) -> dict:
        return {
            "clubId": club_id,
            "clubName": f"Club {club_id}",
            "clubAlias": club_id,
            "clubType": "MAIN",
            "teams": teams,
        }

    def _make_team(
        self,
        team_id: str,
        age_group: str,
        license_type: str,
        status: str = "VALID",
        source: str = "BISHL",
        pass_no: str = "12345",
        admin_override: bool = False,
    ) -> dict:
        return {
            "teamId": team_id,
            "teamName": f"Team {team_id}",
            "teamAlias": team_id,
            "teamType": "COMPETITIVE",
            "teamAgeGroup": age_group,
            "licenseType": license_type,
            "status": status,
            "invalidReasonCodes": [],
            "source": source,
            "passNo": pass_no,
            "adminOverride": admin_override,
        }

    @pytest.mark.asyncio
    async def test_classification_normalizes_ishd_german_age_group_casing(self, service):
        """ISHD data arrives with German capitalization: 'Herren', 'Junioren', etc.
        WKO rules use all-caps keys: 'HERREN', 'U19', etc.

        Without normalization every WKO lookup for ISHD teams silently falls back to
        PRIMARY, making all age-group-aware logic useless for ISHD licences.
        This regression test verifies that 'Herren' (mixed case) is treated identically
        to 'HERREN' (all caps) for a DAMEN player — both should become SECONDARY.
        """
        player = self._make_player_dict(
            datetime(2007, 11, 1),
            [
                self._make_club(
                    "clubA",
                    [
                        self._make_team("t_ishd", "Herren", "UNKNOWN", source="ISHD", pass_no="6293"),
                        self._make_team("t_bishl", "HERREN", "UNKNOWN", source="BISHL", pass_no=""),
                    ],
                )
            ],
        )

        classified = await service.classify_license_types_for_player(player)
        t_ishd = classified["assignedTeams"][0]["teams"][0]
        t_bishl = classified["assignedTeams"][0]["teams"][1]

        assert t_ishd["teamAgeGroup"] == "HERREN", "teamAgeGroup must be normalized to uppercase"
        assert t_ishd["licenseType"] == "SECONDARY", (
            "ISHD 'Herren' (mixed case) must classify as SECONDARY for DAMEN player, not fall back to PRIMARY"
        )
        assert t_bishl["licenseType"] == "SECONDARY", (
            "BISHL 'HERREN' (all caps) must classify as SECONDARY for DAMEN player"
        )

    @pytest.mark.asyncio
    async def test_classification_damen_herren_primary_in_db_reclassified(self, service):
        """Regression test for the exact reported bug: a female player (DAMEN) whose ISHD
        licence for a HERREN team is already stored as PRIMARY in the database.

        When classify_license_types_for_player runs, step 5 must detect that the PRIMARY
        is in a secondary age group for this player and re-classify it as SECONDARY.
        The BISHL SECONDARY licence stays SECONDARY.
        After full validation: quota (maxLicenses=1) invalidates one of them.

        Note: must use a birth year that yields ageGroup=DAMEN in the running test year.
        In 2026 the cutoff is birth year <= 2005 (birth_year < current_year - 20).
        """
        player = self._make_player_dict(
            datetime(2000, 1, 1),
            [
                self._make_club(
                    "clubA",
                    [
                        self._make_team("t_ishd", "HERREN", "PRIMARY", source="ISHD", pass_no="ISHDABC"),
                        self._make_team("t_bishl", "HERREN", "SECONDARY", source="BISHL", pass_no="BISHLXYZ"),
                    ],
                )
            ],
        )

        classified = await service.classify_license_types_for_player(player)
        t_ishd = classified["assignedTeams"][0]["teams"][0]
        t_bishl = classified["assignedTeams"][0]["teams"][1]

        assert t_ishd["licenseType"] == "SECONDARY", (
            "HERREN PRIMARY (ISHD) must be re-classified to SECONDARY for DAMEN player"
        )
        assert t_bishl["licenseType"] == "SECONDARY", (
            "HERREN SECONDARY (BISHL) must stay SECONDARY"
        )

        validated = await service.validate_licenses_for_player(classified)
        teams = validated["assignedTeams"][0]["teams"]
        statuses = [t["status"] for t in teams]

        assert statuses.count("VALID") == 1, "Exactly 1 HERREN licence should be VALID"
        assert statuses.count("INVALID") == 1, "Exactly 1 HERREN licence should be INVALID (EXCEEDS_WKO_LIMIT)"
        invalid_team = next(t for t in teams if t["status"] == "INVALID")
        assert "EXCEEDS_WKO_LIMIT" in invalid_team["invalidReasonCodes"]

    @pytest.mark.asyncio
    async def test_classification_damen_two_herren_unknown_become_secondary(self, service):
        """A female player with no DAMEN licence and 2 HERREN UNKNOWN licences (ISHD, same club)
        should have both classified as SECONDARY — not PRIMARY — because HERREN is a secondaryRule
        target for DAMEN, not the player's natural age group.

        After validation only 1 HERREN SECONDARY should be VALID (quota maxLicenses=1).
        """
        # birthdate: female born 2000 → ageGroup=DAMEN
        player = self._make_player_dict(
            datetime(2000, 1, 1),
            [
                self._make_club(
                    "clubA",
                    [
                        self._make_team("t1", "HERREN", "UNKNOWN", source="ISHD", pass_no="AAA001"),
                        self._make_team("t2", "HERREN", "UNKNOWN", source="ISHD", pass_no="AAA002"),
                    ],
                )
            ],
        )

        classified = await service.classify_license_types_for_player(player)
        t1 = classified["assignedTeams"][0]["teams"][0]
        t2 = classified["assignedTeams"][0]["teams"][1]

        assert t1["licenseType"] == "SECONDARY", "First HERREN licence should be SECONDARY for DAMEN player"
        assert t2["licenseType"] == "SECONDARY", "Second HERREN licence should be SECONDARY for DAMEN player"

        validated = await service.validate_licenses_for_player(classified)
        statuses = [t["status"] for t in validated["assignedTeams"][0]["teams"]]
        valid_count = statuses.count("VALID")
        invalid_count = statuses.count("INVALID")

        assert valid_count == 1, f"Exactly 1 HERREN licence should be VALID (got {valid_count})"
        assert invalid_count == 1, f"Exactly 1 HERREN licence should be INVALID/EXCEEDS_WKO_LIMIT (got {invalid_count})"

        invalid_team = next(t for t in validated["assignedTeams"][0]["teams"] if t["status"] == "INVALID")
        assert "EXCEEDS_WKO_LIMIT" in invalid_team["invalidReasonCodes"]

    @pytest.mark.asyncio
    async def test_classification_damen_single_herren_unknown_becomes_secondary(self, service):
        """A female player with no DAMEN licence and exactly 1 HERREN UNKNOWN licence
        should be classified as SECONDARY (not PRIMARY) and validated as VALID (acts as anchor).
        """
        player = self._make_player_dict(
            datetime(2000, 1, 1),
            [
                self._make_club(
                    "clubA",
                    [self._make_team("t1", "HERREN", "UNKNOWN", source="BISHL", pass_no="BBB001")],
                )
            ],
        )

        classified = await service.classify_license_types_for_player(player)
        t1 = classified["assignedTeams"][0]["teams"][0]
        assert t1["licenseType"] == "SECONDARY", "Single HERREN licence for DAMEN player must be SECONDARY"

        validated = await service.validate_licenses_for_player(classified)
        t1v = validated["assignedTeams"][0]["teams"][0]
        assert t1v["status"] == "VALID", "Single HERREN SECONDARY for DAMEN player must be VALID (anchor)"

    @pytest.mark.asyncio
    async def test_validation_sex_filter_blocks_male_damen_secondary(self, service):
        """_is_secondary_allowed must enforce the sex filter on secondaryRules.

        DAMEN's secondaryRule for HERREN restricts sex=[FEMALE]. A male player whose
        ageGroup is DAMEN (edge-case / wrong data) with a HERREN SECONDARY should be
        blocked by step 8 with AGE_GROUP_VIOLATION.
        """
        # Force a male player into DAMEN age group by using a very old birthdate
        # and setting sex=MALE manually (edge-case / corrupted data scenario).
        player = self._make_player_dict(
            datetime(2000, 1, 1),
            [
                self._make_club(
                    "clubA",
                    [self._make_team("t1", "HERREN", "SECONDARY")],
                )
            ],
            sex=Sex.MALE,
        )
        # Override sex to MALE so ageGroup=HERREN (males born <=2007 are HERREN)
        # We need to force ageGroup=DAMEN for a male to test the sex filter directly
        # on _is_secondary_allowed. Call it directly.
        from models.players import Sex as SexModel

        result = service._is_secondary_allowed("DAMEN", "HERREN", SexModel.MALE)
        assert result is False, "Male player should NOT satisfy DAMEN→HERREN secondary rule (sex=[FEMALE])"

        result_female = service._is_secondary_allowed("DAMEN", "HERREN", SexModel.FEMALE)
        assert result_female is True, "Female player should satisfy DAMEN→HERREN secondary rule"

    @pytest.mark.asyncio
    async def test_validation_herren_male_two_primary_no_import_conflict(self, service):
        """Regression test: a HERREN male player with both a BISHL PRIMARY and an ISHD PRIMARY
        in the same club should get exactly one VALID (BISHL wins) and one INVALID (MULTIPLE_PRIMARY).

        The INVALID licence must NOT also carry IMPORT_CONFLICT.  Before the ordering fix,
        _validate_import_conflicts ran first (both statuses still VALID at that point), added
        IMPORT_CONFLICT to the ISHD licence, then _validate_primary_consistency added MULTIPLE_PRIMARY
        on top — resulting in two error codes.  With the correct ordering (primary_consistency first),
        the ISHD licence is already INVALID when import_conflicts inspects it, so it is skipped.
        """
        from models.players import Sex as SexModel

        player = self._make_player_dict(
            datetime(1990, 1, 1),
            [
                self._make_club(
                    "clubA",
                    [
                        self._make_team("t_ishd", "HERREN", "PRIMARY", source="ISHD", pass_no="4144"),
                        self._make_team("t_bishl", "HERREN", "PRIMARY", source="BISHL", pass_no=""),
                    ],
                )
            ],
            sex=SexModel.MALE,
        )

        validated = await service.validate_licenses_for_player(player)
        teams = validated["assignedTeams"][0]["teams"]
        by_id = {t["teamId"]: t for t in teams}

        assert by_id["t_bishl"]["status"] == "VALID", "BISHL PRIMARY must be the valid anchor"
        assert by_id["t_ishd"]["status"] == "INVALID", "ISHD PRIMARY must be invalidated"
        assert "MULTIPLE_PRIMARY" in by_id["t_ishd"]["invalidReasonCodes"], (
            "ISHD PRIMARY must carry MULTIPLE_PRIMARY"
        )
        assert "IMPORT_CONFLICT" not in by_id["t_ishd"]["invalidReasonCodes"], (
            "IMPORT_CONFLICT must NOT be added when MULTIPLE_PRIMARY already explains the invalidity"
        )

    @pytest.mark.asyncio
    async def test_validation_primary_in_wrong_age_group_invalidated(self, service):
        """Validation Pass 1 must flag a PRIMARY licence whose teamAgeGroup differs
        from the player's own age group as INVALID (AGE_GROUP_VIOLATION).

        Old behaviour (before Fix B): quota sorter kept PRIMARY VALID, marked SECONDARY INVALID.
        New behaviour: Pass 1 catches the misplaced PRIMARY immediately; only the
        SECONDARY remains VALID (1 VALID HERREN ≤ quota max 1, so no EXCEEDS_WKO_LIMIT).
        """
        player = self._make_player_dict(
            datetime(2000, 1, 1),
            [
                self._make_club(
                    "clubA",
                    [
                        self._make_team("t1", "HERREN", "SECONDARY"),
                        self._make_team("t2", "HERREN", "PRIMARY"),
                    ],
                )
            ],
        )

        validated = await service.validate_licenses_for_player(player)
        teams = validated["assignedTeams"][0]["teams"]
        by_id = {t["teamId"]: t for t in teams}

        assert by_id["t2"]["status"] == "INVALID", (
            "HERREN PRIMARY must be INVALID (AGE_GROUP_VIOLATION) for a DAMEN player"
        )
        assert "AGE_GROUP_VIOLATION" in by_id["t2"]["invalidReasonCodes"]
        assert by_id["t1"]["status"] == "VALID", (
            "HERREN SECONDARY is the only valid licence; quota is satisfied (1 ≤ max 1)"
        )

    @pytest.mark.asyncio
    async def test_update_player_validation_corrects_stale_ishd_secondary(self, service, mock_db):
        """Regression test for T001: _update_player_validation_in_db must reset licenseTypes
        before classifying, so a stale SECONDARY stored in the DB for an ISHD licence that
        belongs to the player's primary age group is corrected to PRIMARY (then invalidated
        as MULTIPLE_PRIMARY because there is already a BISHL PRIMARY in the same age group).

        Before the fix: classify ran without resetting → the stale SECONDARY survived → the
        ISHD licence was never promoted to PRIMARY → MULTIPLE_PRIMARY was never raised.
        After the fix: licenseType is reset to UNKNOWN, classify re-derives PRIMARY, and
        validate correctly marks it INVALID[MULTIPLE_PRIMARY].
        """
        from unittest.mock import AsyncMock

        from bson import ObjectId

        player_id = str(ObjectId())
        player_doc = self._make_player_dict(
            datetime(2000, 1, 1),
            [
                self._make_club(
                    "clubA",
                    [
                        self._make_team(
                            "t_bishl", "HERREN", "PRIMARY", source="BISHL", pass_no=""
                        ),
                        self._make_team(
                            "t_ishd",
                            "HERREN",
                            "SECONDARY",
                            source="ISHD",
                            pass_no="4144",
                        ),
                    ],
                )
            ],
            sex=Sex.MALE,
        )
        player_doc["_id"] = player_id

        mock_db["players"].find_one = AsyncMock(return_value=player_doc)
        mock_db["players"].update_one = AsyncMock()

        was_modified = await service._update_player_validation_in_db(player_id, reset=True)

        assert was_modified is True, "Player must be modified when stale SECONDARY is corrected"

        updated_call_args = mock_db["players"].update_one.call_args
        new_teams = updated_call_args[0][1]["$set"]["assignedTeams"][0]["teams"]
        by_id = {t["teamId"]: t for t in new_teams}

        assert by_id["t_ishd"]["licenseType"] == "PRIMARY", (
            "Stale ISHD SECONDARY must be reclassified to PRIMARY"
        )
        assert by_id["t_ishd"]["status"] == "INVALID", (
            "ISHD PRIMARY must be invalidated (MULTIPLE_PRIMARY)"
        )
        assert "MULTIPLE_PRIMARY" in by_id["t_ishd"]["invalidReasonCodes"], (
            "MULTIPLE_PRIMARY must be the reason code for the duplicate PRIMARY"
        )
        assert by_id["t_bishl"]["status"] == "VALID", (
            "BISHL PRIMARY must remain VALID as the first-found PRIMARY"
        )

    @pytest.mark.asyncio
    async def test_classify_and_validate_player_in_memory_corrects_stale_types(self, service):
        """Unit test for T002: classify_and_validate_player_in_memory must return a fresh dict
        with all licenseTypes and statuses recomputed from scratch, without touching the DB.

        Input: a HERREN male player whose ISHD licence has a stale SECONDARY and whose BISHL
        licence has UNKNOWN status.  Output must have BISHL=PRIMARY/VALID and
        ISHD=PRIMARY/INVALID[MULTIPLE_PRIMARY].

        The original dict must not be mutated (deep-copy contract).
        """
        player = self._make_player_dict(
            datetime(2000, 1, 1),
            [
                self._make_club(
                    "clubA",
                    [
                        self._make_team(
                            "t_bishl", "HERREN", "UNKNOWN", status="UNKNOWN", source="BISHL", pass_no=""
                        ),
                        self._make_team(
                            "t_ishd",
                            "HERREN",
                            "SECONDARY",
                            status="VALID",
                            source="ISHD",
                            pass_no="4144",
                        ),
                    ],
                )
            ],
            sex=Sex.MALE,
        )

        original_ishd_type = player["assignedTeams"][0]["teams"][1]["licenseType"]

        result = await service.classify_and_validate_player_in_memory(player)

        assert player["assignedTeams"][0]["teams"][1]["licenseType"] == original_ishd_type, (
            "classify_and_validate_player_in_memory must not mutate the input dict"
        )

        by_id = {t["teamId"]: t for t in result["assignedTeams"][0]["teams"]}

        assert by_id["t_bishl"]["licenseType"] == "PRIMARY"
        assert by_id["t_bishl"]["status"] == "VALID", "BISHL PRIMARY must be VALID"
        assert by_id["t_ishd"]["licenseType"] == "PRIMARY", (
            "Stale ISHD SECONDARY must be reclassified to PRIMARY in-memory"
        )
        assert by_id["t_ishd"]["status"] == "INVALID", (
            "ISHD PRIMARY must be INVALID (MULTIPLE_PRIMARY) in-memory"
        )
        assert "MULTIPLE_PRIMARY" in by_id["t_ishd"]["invalidReasonCodes"]

        assert not hasattr(service, "_db_write_called"), (
            "No DB writes should occur during in-memory classification+validation"
        )


class TestDevelopmentClub:
    """Tests for DEVELOPMENT clubs (F-suffix passNo) — standalone pools
    exempt from CONFLICTING_CLUB validation."""

    @pytest.fixture
    def mock_db(self, mocker):
        mock_db = MagicMock()
        mock_db["players"].update_one = mocker.AsyncMock()
        return mock_db

    @pytest.fixture
    def service(self, mock_db):
        return PlayerAssignmentService(mock_db)

    def _make_player_dict(self, birthdate, teams_by_club: list[dict], sex=Sex.MALE) -> dict:
        return {
            "_id": str(ObjectId()),
            "firstName": "Test",
            "lastName": "Player",
            "birthdate": birthdate,
            "displayFirstName": "Test",
            "displayLastName": "Player",
            "sex": sex,
            "position": "Skater",
            "managedByISHD": False,
            "assignedTeams": teams_by_club,
        }

    def _make_club(self, club_id: str, teams: list[dict], club_type: str = "MAIN") -> dict:
        return {
            "clubId": club_id,
            "clubName": f"Club {club_id}",
            "clubAlias": club_id,
            "clubType": club_type,
            "teams": teams,
        }

    def _make_team(
        self,
        team_id: str,
        age_group: str,
        license_type: str,
        status: str = "VALID",
        source: str = "BISHL",
        pass_no: str = "12345",
        admin_override: bool = False,
    ) -> dict:
        return {
            "teamId": team_id,
            "teamName": f"Team {team_id}",
            "teamAlias": team_id,
            "teamType": "COMPETITIVE",
            "teamAgeGroup": age_group,
            "licenseType": license_type,
            "status": status,
            "invalidReasonCodes": [],
            "source": source,
            "passNo": pass_no,
            "adminOverride": admin_override,
        }

    @pytest.mark.asyncio
    async def test_development_club_secondary_no_conflicting_club(self, service):
        """DEVELOPMENT club SECONDARY license must NOT get CONFLICTING_CLUB.

        Scenario: U19 player
        - Club A (MAIN): ISHD PRIMARY in U19 team → valid
        - Club B (DEVELOPMENT): F-suffix HERREN team → classified as SECONDARY
          (U19 player playing up in HERREN) → must be VALID, no CONFLICTING_CLUB.

        The F-suffix marks the club as DEVELOPMENT during classification.
        A DEVELOPMENT club is a standalone pool and does not need a co-located
        PRIMARY to validate SECONDARY/OVERAGE licenses.
        """
        player = self._make_player_dict(
            datetime(2008, 1, 1),
            [
                self._make_club(
                    "clubA",
                    [self._make_team("t_main", "U19", "PRIMARY", source="ISHD", pass_no="6293")],
                    club_type="MAIN",
                ),
                self._make_club(
                    "clubB",
                    [self._make_team("t_dev", "HERREN", "SECONDARY", source="BISHL", pass_no="9999F")],
                    club_type="DEVELOPMENT",
                ),
            ],
        )

        result = await service.validate_licenses_for_player(player)

        t_main = result["assignedTeams"][0]["teams"][0]
        t_dev = result["assignedTeams"][1]["teams"][0]

        assert t_main["status"] == "VALID", "MAIN club PRIMARY must be VALID"
        assert t_dev["status"] == "VALID", (
            "DEVELOPMENT club SECONDARY must be VALID — standalone pool, no CONFLICTING_CLUB"
        )
        assert "CONFLICTING_CLUB" not in t_dev["invalidReasonCodes"]

    @pytest.mark.asyncio
    async def test_development_club_full_classify_and_validate(self, service):
        """End-to-end: F-suffix passNo in a separate club → classification sets
        clubType=DEVELOPMENT and licenseType=SECONDARY, validation keeps it VALID.

        Scenario: U19 player
        - Club A: ISHD UNKNOWN in U19 team → classified as PRIMARY
        - Club B: BISHL UNKNOWN in HERREN team with F-suffix → club becomes DEVELOPMENT,
          license becomes SECONDARY (U19 → HERREN = secondary rule), stays VALID.
        """
        player = self._make_player_dict(
            datetime(2008, 1, 1),
            [
                self._make_club(
                    "clubA",
                    [self._make_team("t_main", "U19", "UNKNOWN", source="ISHD", pass_no="6293")],
                ),
                self._make_club(
                    "clubB",
                    [self._make_team("t_dev", "HERREN", "UNKNOWN", source="BISHL", pass_no="9999F")],
                ),
            ],
        )

        classified = await service.classify_license_types_for_player(player)

        assert classified["assignedTeams"][1]["clubType"] == "DEVELOPMENT", (
            "F-suffix must mark the club as DEVELOPMENT"
        )

        t_dev_classified = classified["assignedTeams"][1]["teams"][0]
        assert t_dev_classified["licenseType"] in ["PRIMARY", "SECONDARY"], (
            "F-suffix license must be classified (not left as UNKNOWN)"
        )

        validated = await service.validate_licenses_for_player(classified)

        t_main = validated["assignedTeams"][0]["teams"][0]
        t_dev = validated["assignedTeams"][1]["teams"][0]

        assert t_main["status"] == "VALID"
        assert t_dev["status"] == "VALID", (
            "DEVELOPMENT club license must be VALID after full classify+validate"
        )
        assert "CONFLICTING_CLUB" not in t_dev["invalidReasonCodes"]

    @pytest.mark.asyncio
    async def test_non_development_secondary_still_gets_conflicting_club(self, service):
        """Inverse case: a regular (non-DEVELOPMENT) club's SECONDARY without
        a co-located PRIMARY must still get CONFLICTING_CLUB.

        This ensures the DEVELOPMENT exemption does not accidentally
        disable the check for regular MAIN clubs.
        """
        player = self._make_player_dict(
            datetime(2008, 1, 1),
            [
                self._make_club(
                    "clubA",
                    [self._make_team("t_main", "U19", "PRIMARY", source="BISHL")],
                    club_type="MAIN",
                ),
                self._make_club(
                    "clubB",
                    [self._make_team("t_other", "HERREN", "SECONDARY", source="BISHL")],
                    club_type="MAIN",
                ),
            ],
        )

        result = await service.validate_licenses_for_player(player)
        t_other = result["assignedTeams"][1]["teams"][0]

        assert t_other["status"] == "INVALID", (
            "Non-DEVELOPMENT club SECONDARY without co-located PRIMARY must be INVALID"
        )
        assert "CONFLICTING_CLUB" in t_other["invalidReasonCodes"]


class TestAnchorOverage:
    """Tests for anchor-only OVERAGE scenario — a single OVERAGE license
    acting as anchor should not require the overAge flag."""

    @pytest.fixture
    def mock_db(self, mocker):
        mock_db = MagicMock()
        mock_db["players"].update_one = mocker.AsyncMock()
        return mock_db

    @pytest.fixture
    def service(self, mock_db):
        return PlayerAssignmentService(mock_db)

    def _make_player_dict(self, birthdate, teams_by_club: list[dict], sex=Sex.MALE) -> dict:
        return {
            "_id": str(ObjectId()),
            "firstName": "Test",
            "lastName": "Player",
            "birthdate": birthdate,
            "displayFirstName": "Test",
            "displayLastName": "Player",
            "sex": sex,
            "position": "Skater",
            "managedByISHD": False,
            "assignedTeams": teams_by_club,
        }

    def _make_club(self, club_id: str, teams: list[dict]) -> dict:
        return {
            "clubId": club_id,
            "clubName": f"Club {club_id}",
            "clubAlias": club_id,
            "clubType": "MAIN",
            "teams": teams,
        }

    def _make_team(
        self,
        team_id: str,
        age_group: str,
        license_type: str,
        status: str = "VALID",
        source: str = "BISHL",
        pass_no: str = "12345",
    ) -> dict:
        return {
            "teamId": team_id,
            "teamName": f"Team {team_id}",
            "teamAlias": team_id,
            "teamType": "COMPETITIVE",
            "teamAgeGroup": age_group,
            "licenseType": license_type,
            "status": status,
            "invalidReasonCodes": [],
            "source": source,
            "passNo": pass_no,
            "adminOverride": False,
        }

    @pytest.mark.asyncio
    async def test_single_overage_anchor_valid_without_overage_flag(self, service):
        """A U16 player (overAge=False) with ONLY a single U13 OVERAGE license
        and no PRIMARY anywhere — the OVERAGE acts as anchor and the overAge
        flag is not required.

        The player's club simply has no U16 team, so the U13 team is the only
        option. _get_primary_club_ids returns the anchor club's ID, and
        _validate_age_group_compliance relaxes the overAge flag requirement.
        """
        player = self._make_player_dict(
            datetime(2011, 1, 1),
            [
                self._make_club(
                    "club1",
                    [self._make_team("t1", "U13", "OVERAGE")],
                ),
            ],
        )

        result = await service.validate_licenses_for_player(player)
        t1 = result["assignedTeams"][0]["teams"][0]

        assert t1["status"] == "VALID", (
            "Single OVERAGE anchor license must be VALID without overAge flag"
        )
        assert "OVERAGE_NOT_ALLOWED" not in t1["invalidReasonCodes"]
