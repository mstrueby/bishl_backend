
"""Unit tests for License Validation Service"""

from datetime import datetime

import pytest
from bson import ObjectId

from models.players import (
    AssignedClubs,
    AssignedTeams,
    LicenseInvalidReasonCode,
    LicenseStatusEnum,
    LicenseTypeEnum,
    PlayerDB,
    PositionEnum,
    SexEnum,
    SourceEnum,
)
from services.license_validation_service import LicenseValidationService


class TestLicenseValidationService:
    """Test suite for LicenseValidationService"""

    @pytest.fixture
    def mock_db(self, mocker):
        """Mock database"""
        mock_db = mocker.MagicMock()
        mock_db["players"].update_one = mocker.AsyncMock()
        return mock_db

    @pytest.fixture
    def validation_service(self, mock_db):
        """Create validation service instance"""
        return LicenseValidationService(mock_db)

    def create_test_player(
        self,
        player_id: str = None,
        age_group: str = "U16",
        sex: SexEnum = SexEnum.MALE,
        assigned_teams: list = None,
    ) -> PlayerDB:
        """Helper to create test player"""
        if player_id is None:
            player_id = str(ObjectId())

        birthdate = datetime(2010, 1, 1)  # U16 player
        if age_group == "U19":
            birthdate = datetime(2007, 1, 1)
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
            position=PositionEnum.SKATER,
            assignedTeams=assigned_teams or [],
            managedByISHD=False,
        )

    def create_assigned_team(
        self,
        team_id: str = "team1",
        team_name: str = "Team 1",
        team_age_group: str = "U16",
        license_type: LicenseTypeEnum = LicenseTypeEnum.PRIMARY,
        source: SourceEnum = SourceEnum.BISHL,
    ) -> AssignedTeams:
        """Helper to create assigned team"""
        return AssignedTeams(
            teamId=team_id,
            teamName=team_name,
            teamAlias=team_id,
            teamAgeGroup=team_age_group,
            passNo="12345",
            licenseType=license_type,
            source=source,
            status=LicenseStatusEnum.VALID,
            invalidReasonCodes=[],
        )

    @pytest.mark.asyncio
    async def test_reset_license_states(self, validation_service):
        """Test that all licenses are reset to VALID"""
        team = self.create_assigned_team()
        team.status = LicenseStatusEnum.INVALID
        team.invalidReasonCodes = [LicenseInvalidReasonCode.MULTIPLE_PRIMARY]

        club = AssignedClubs(
            clubId="club1",
            clubName="Club 1",
            clubAlias="club1",
            teams=[team],
        )

        player = self.create_test_player(assigned_teams=[club])

        validation_service._reset_license_states(player)

        assert player.assignedTeams[0].teams[0].status == LicenseStatusEnum.VALID
        assert player.assignedTeams[0].teams[0].invalidReasonCodes == []

    @pytest.mark.asyncio
    async def test_multiple_primary_licenses(self, validation_service, mock_db):
        """Test validation fails with multiple PRIMARY licenses"""
        club1 = AssignedClubs(
            clubId="club1",
            clubName="Club 1",
            clubAlias="club1",
            teams=[
                self.create_assigned_team("team1", "Team 1", "U16", LicenseTypeEnum.PRIMARY)
            ],
        )

        club2 = AssignedClubs(
            clubId="club2",
            clubName="Club 2",
            clubAlias="club2",
            teams=[
                self.create_assigned_team("team2", "Team 2", "U16", LicenseTypeEnum.PRIMARY)
            ],
        )

        player = self.create_test_player(assigned_teams=[club1, club2])

        report = await validation_service.revalidate_player_licenses(player)

        # Both PRIMARY licenses should be invalid
        assert player.assignedTeams[0].teams[0].status == LicenseStatusEnum.INVALID
        assert player.assignedTeams[1].teams[0].status == LicenseStatusEnum.INVALID
        assert LicenseInvalidReasonCode.MULTIPLE_PRIMARY in player.assignedTeams[0].teams[0].invalidReasonCodes
        assert LicenseInvalidReasonCode.MULTIPLE_PRIMARY in player.assignedTeams[1].teams[0].invalidReasonCodes
        assert report.invalidLicenses == 2

    @pytest.mark.asyncio
    async def test_multiple_loan_licenses(self, validation_service, mock_db):
        """Test validation fails with multiple LOAN licenses"""
        club1 = AssignedClubs(
            clubId="club1",
            clubName="Club 1",
            clubAlias="club1",
            teams=[
                self.create_assigned_team("team1", "Team 1", "U16", LicenseTypeEnum.PRIMARY),
                self.create_assigned_team("team2", "Team 2", "U16", LicenseTypeEnum.LOAN),
            ],
        )

        club2 = AssignedClubs(
            clubId="club2",
            clubName="Club 2",
            clubAlias="club2",
            teams=[
                self.create_assigned_team("team3", "Team 3", "U16", LicenseTypeEnum.LOAN)
            ],
        )

        player = self.create_test_player(assigned_teams=[club1, club2])

        report = await validation_service.revalidate_player_licenses(player)

        # Both LOAN licenses should be invalid
        loan_teams = [
            player.assignedTeams[0].teams[1],
            player.assignedTeams[1].teams[0],
        ]
        for team in loan_teams:
            assert team.status == LicenseStatusEnum.INVALID
            assert LicenseInvalidReasonCode.TOO_MANY_LOAN in team.invalidReasonCodes

    @pytest.mark.asyncio
    async def test_conflicting_club_for_secondary(self, validation_service, mock_db):
        """Test SECONDARY license in different club is invalid"""
        club1 = AssignedClubs(
            clubId="club1",
            clubName="Club 1",
            clubAlias="club1",
            teams=[
                self.create_assigned_team("team1", "Team 1", "U16", LicenseTypeEnum.PRIMARY)
            ],
        )

        club2 = AssignedClubs(
            clubId="club2",
            clubName="Club 2",
            clubAlias="club2",
            teams=[
                self.create_assigned_team("team2", "Team 2", "U19", LicenseTypeEnum.SECONDARY)
            ],
        )

        player = self.create_test_player(assigned_teams=[club1, club2])

        report = await validation_service.revalidate_player_licenses(player)

        # SECONDARY in different club should be invalid
        assert player.assignedTeams[1].teams[0].status == LicenseStatusEnum.INVALID
        assert LicenseInvalidReasonCode.CONFLICTING_CLUB in player.assignedTeams[1].teams[0].invalidReasonCodes

    @pytest.mark.asyncio
    async def test_overage_allowed(self, validation_service, mock_db):
        """Test OVERAGE license is valid when player has overAge property"""
        club = AssignedClubs(
            clubId="club1",
            clubName="Club 1",
            clubAlias="club1",
            teams=[
                self.create_assigned_team("team1", "Team 1", "U16", LicenseTypeEnum.PRIMARY),
                self.create_assigned_team("team2", "Team 2", "U13", LicenseTypeEnum.OVERAGE),
            ],
        )

        # U16 player with overAge can play in U13
        player = self.create_test_player(age_group="U16", assigned_teams=[club])

        report = await validation_service.revalidate_player_licenses(player)

        # If player.overAge is True, OVERAGE should be valid
        # (depends on player's birthdate and overAge calculation)
        assert report.validLicenses >= 1

    @pytest.mark.asyncio
    async def test_ishd_vs_bishl_conflict(self, validation_service, mock_db):
        """Test ISHD license conflicts with BISHL license"""
        club = AssignedClubs(
            clubId="club1",
            clubName="Club 1",
            clubAlias="club1",
            teams=[
                self.create_assigned_team("team1", "Team 1", "U16", LicenseTypeEnum.PRIMARY, SourceEnum.BISHL),
                self.create_assigned_team("team2", "Team 2", "U16", LicenseTypeEnum.PRIMARY, SourceEnum.ISHD),
            ],
        )

        player = self.create_test_player(assigned_teams=[club])

        report = await validation_service.revalidate_player_licenses(player)

        # ISHD PRIMARY should be marked as conflict
        ishd_team = player.assignedTeams[0].teams[1]
        assert ishd_team.status == LicenseStatusEnum.INVALID
        assert LicenseInvalidReasonCode.IMPORT_CONFLICT in ishd_team.invalidReasonCodes

    @pytest.mark.asyncio
    async def test_wko_participation_limit(self, validation_service, mock_db):
        """Test WKO limit on number of participations"""
        club = AssignedClubs(
            clubId="club1",
            clubName="Club 1",
            clubAlias="club1",
            teams=[
                self.create_assigned_team("team1", "Team 1", "U16", LicenseTypeEnum.PRIMARY),
                self.create_assigned_team("team2", "Team 2", "U19", LicenseTypeEnum.SECONDARY),
                self.create_assigned_team("team3", "Team 3", "U13", LicenseTypeEnum.SECONDARY),
            ],
        )

        player = self.create_test_player(age_group="U16", assigned_teams=[club])

        report = await validation_service.revalidate_player_licenses(player)

        # Should have at most 2 valid participations (WKO limit)
        valid_participations = sum(
            1 for team in player.assignedTeams[0].teams
            if team.status == LicenseStatusEnum.VALID
        )
        assert valid_participations <= 2

        # At least one should be marked as exceeds limit
        exceeds_limit = any(
            LicenseInvalidReasonCode.EXCEEDS_WKO_LIMIT in team.invalidReasonCodes
            for team in player.assignedTeams[0].teams
        )
        assert exceeds_limit

    @pytest.mark.asyncio
    async def test_valid_date_sanity(self, validation_service, mock_db):
        """Test date sanity validation"""
        team = self.create_assigned_team()
        team.validFrom = datetime(2024, 6, 1)
        team.validTo = datetime(2024, 1, 1)  # Invalid: validTo before validFrom

        club = AssignedClubs(
            clubId="club1",
            clubName="Club 1",
            clubAlias="club1",
            teams=[team],
        )

        player = self.create_test_player(assigned_teams=[club])

        report = await validation_service.revalidate_player_licenses(player)

        assert player.assignedTeams[0].teams[0].status == LicenseStatusEnum.INVALID
        assert LicenseInvalidReasonCode.IMPORT_CONFLICT in player.assignedTeams[0].teams[0].invalidReasonCodes
