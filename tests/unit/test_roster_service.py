"""Unit tests for RosterService"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from exceptions import (
    AuthorizationException,
    ResourceNotFoundException,
    ValidationException,
)
from models.matches import RosterStatus, RosterUpdate
from services.roster_service import RosterService


@pytest.fixture
def mock_db():
    """Mock MongoDB database"""

    db = MagicMock()

    mock_matches_collection = MagicMock()
    mock_matches_collection.find_one = AsyncMock()
    mock_matches_collection.update_one = AsyncMock()

    mock_players_collection = MagicMock()
    mock_players_collection.find_one = AsyncMock(return_value=None)

    db._matches_collection = mock_matches_collection

    db.__getitem__ = MagicMock(
        side_effect=lambda name: {
            "matches": mock_matches_collection,
            "players": mock_players_collection,
        }.get(name)
    )

    return db


@pytest.fixture
def roster_service(mock_db):
    """RosterService instance with mocked database"""
    return RosterService(mock_db)


class TestGetRoster:
    """Test roster retrieval"""

    @pytest.mark.asyncio
    async def test_get_roster_returns_roster_object(self, roster_service, mock_db):
        """Test successful roster retrieval returns Roster object"""
        from bson import ObjectId

        from models.matches import Roster

        match_id = str(ObjectId())
        test_match = {
            "_id": match_id,
            "home": {
                "roster": {
                    "players": [
                        {
                            "player": {"playerId": "p1", "firstName": "John", "lastName": "Doe"},
                            "playerPosition": {"key": "FW", "value": "Forward"},
                            "passNumber": "123",
                            "goals": 2,
                            "assists": 1,
                        }
                    ],
                    "status": "SUBMITTED",
                    "published": True,
                    "coach": {"firstName": "Coach", "lastName": "Test"},
                    "staff": [],
                }
            },
        }

        mock_db._matches_collection.find_one = AsyncMock(return_value=test_match)

        result = await roster_service.get_roster(match_id, "home")

        assert isinstance(result, Roster)
        assert len(result.players) == 1
        assert result.players[0].player.playerId == "p1"
        assert result.status == RosterStatus.SUBMITTED
        assert result.published is True
        assert result.coach.firstName == "Coach"

    @pytest.mark.asyncio
    async def test_get_roster_handles_legacy_flat_structure(self, roster_service, mock_db):
        """Test roster retrieval handles legacy flat structure"""
        from bson import ObjectId

        match_id = str(ObjectId())
        test_match = {
            "_id": match_id,
            "home": {
                "roster": [
                    {
                        "player": {"playerId": "p1", "firstName": "John", "lastName": "Doe"},
                        "playerPosition": {"key": "FW", "value": "Forward"},
                        "passNumber": "123",
                    }
                ],
                "rosterStatus": "APPROVED",
                "rosterPublished": True,
                "coach": {"firstName": "Legacy", "lastName": "Coach"},
                "staff": [{"firstName": "Staff", "lastName": "Member", "role": "Trainer"}],
            },
        }

        mock_db._matches_collection.find_one = AsyncMock(return_value=test_match)

        result = await roster_service.get_roster(match_id, "home")

        assert len(result.players) == 1
        assert result.status == RosterStatus.APPROVED
        assert result.published is True
        assert result.coach.firstName == "Legacy"
        assert len(result.staff) == 1

    @pytest.mark.asyncio
    async def test_get_roster_match_not_found(self, roster_service, mock_db):
        """Test error when match not found"""
        from bson import ObjectId

        mock_db._matches_collection.find_one = AsyncMock(return_value=None)

        match_id = str(ObjectId())
        with pytest.raises(ResourceNotFoundException) as exc_info:
            await roster_service.get_roster(match_id, "home")

        assert exc_info.value.details["resource_type"] == "Match"

    @pytest.mark.asyncio
    async def test_get_roster_invalid_team_flag(self, roster_service, mock_db):
        """Test error with invalid team flag"""
        from bson import ObjectId

        match_id = str(ObjectId())
        with pytest.raises(ValidationException) as exc_info:
            await roster_service.get_roster(match_id, "invalid")

        assert "Must be 'home' or 'away'" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_get_roster_empty_roster(self, roster_service, mock_db):
        """Test handling of empty roster"""
        from bson import ObjectId

        match_id = str(ObjectId())
        test_match = {
            "_id": match_id,
            "home": {
                "roster": {
                    "players": [],
                    "status": "DRAFT",
                    "published": False,
                }
            },
        }

        mock_db._matches_collection.find_one = AsyncMock(return_value=test_match)

        result = await roster_service.get_roster(match_id, "home")

        assert result.players == []
        assert result.status == RosterStatus.DRAFT


class TestValidateRosterPlayers:
    """Test roster player validation"""

    @pytest.mark.asyncio
    async def test_validate_roster_duplicate_players(self, roster_service):
        """Test validation fails when roster contains duplicate players"""
        from bson import ObjectId

        from models.matches import EventPlayer, RosterPlayer

        match_id = str(ObjectId())
        match = {"_id": match_id, "home": {"scores": [], "penalties": []}}

        new_players = [
            RosterPlayer(
                player=EventPlayer(playerId="p1", firstName="John", lastName="Doe"),
                playerPosition={"key": "FW", "value": "Forward"},
                passNumber="123",
            ),
            RosterPlayer(
                player=EventPlayer(playerId="p1", firstName="John", lastName="Doe"),
                playerPosition={"key": "DF", "value": "Defense"},
                passNumber="456",
            ),
        ]

        with pytest.raises(ValidationException) as exc_info:
            await roster_service.validate_roster_players(match, "home", new_players)

        assert "duplicate players" in exc_info.value.message.lower()
        assert "p1" in exc_info.value.details["duplicate_player_ids"]

    @pytest.mark.asyncio
    async def test_validate_roster_with_scores_success(self, roster_service):
        """Test successful validation when players in scores are in roster"""
        from bson import ObjectId

        from models.matches import EventPlayer, RosterPlayer

        match_id = str(ObjectId())
        match = {
            "_id": match_id,
            "home": {
                "scores": [{"goalPlayer": {"playerId": "p1"}, "assistPlayer": {"playerId": "p2"}}],
                "penalties": [],
            },
        }

        new_players = [
            RosterPlayer(
                player=EventPlayer(playerId="p1", firstName="John", lastName="Doe"),
                playerPosition={"key": "FW", "value": "Forward"},
                passNumber="123",
            ),
            RosterPlayer(
                player=EventPlayer(playerId="p2", firstName="Jane", lastName="Doe"),
                playerPosition={"key": "DF", "value": "Defense"},
                passNumber="456",
            ),
        ]

        await roster_service.validate_roster_players(match, "home", new_players)

    @pytest.mark.asyncio
    async def test_validate_roster_missing_goal_player(self, roster_service):
        """Test validation fails when goal player not in roster"""
        from bson import ObjectId

        from models.matches import EventPlayer, RosterPlayer

        match_id = str(ObjectId())
        match = {
            "_id": match_id,
            "home": {
                "scores": [{"goalPlayer": {"playerId": "p1"}, "assistPlayer": None}],
                "penalties": [],
            },
        }

        new_players = [
            RosterPlayer(
                player=EventPlayer(playerId="p2", firstName="Jane", lastName="Doe"),
                playerPosition={"key": "DF", "value": "Defense"},
                passNumber="456",
            )
        ]

        with pytest.raises(ValidationException) as exc_info:
            await roster_service.validate_roster_players(match, "home", new_players)

        assert "players in scores must be in roster" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_validate_roster_missing_penalty_player(self, roster_service):
        """Test validation fails when penalty player not in roster"""
        from bson import ObjectId

        from models.matches import EventPlayer, RosterPlayer

        match_id = str(ObjectId())
        match = {
            "_id": match_id,
            "home": {"scores": [], "penalties": [{"penaltyPlayer": {"playerId": "p1"}}]},
        }

        new_players = [
            RosterPlayer(
                player=EventPlayer(playerId="p2", firstName="Jane", lastName="Doe"),
                playerPosition={"key": "DF", "value": "Defense"},
                passNumber="456",
            )
        ]

        with pytest.raises(ValidationException) as exc_info:
            await roster_service.validate_roster_players(match, "home", new_players)

        assert "players in penalties must be in roster" in exc_info.value.message


class TestValidateStatusTransition:
    """Test roster status transition validation"""

    def test_valid_draft_to_submitted(self, roster_service):
        """Test DRAFT -> SUBMITTED is allowed"""
        roster_service.validate_status_transition(
            RosterStatus.DRAFT, RosterStatus.SUBMITTED, "match-1", "home"
        )

    def test_valid_submitted_to_approved(self, roster_service):
        """Test SUBMITTED -> APPROVED is allowed"""
        roster_service.validate_status_transition(
            RosterStatus.SUBMITTED, RosterStatus.APPROVED, "match-1", "home"
        )

    def test_valid_any_to_invalid(self, roster_service):
        """Test valid statuses -> INVALID is allowed"""
        for status in [RosterStatus.SUBMITTED, RosterStatus.APPROVED]:
            roster_service.validate_status_transition(
                status, RosterStatus.INVALID, "match-1", "home"
            )

    def test_invalid_draft_to_approved(self, roster_service):
        """Test DRAFT -> APPROVED is not allowed (must go through SUBMITTED)"""
        with pytest.raises(ValidationException) as exc_info:
            roster_service.validate_status_transition(
                RosterStatus.DRAFT, RosterStatus.APPROVED, "match-1", "home"
            )

        assert "cannot transition" in exc_info.value.message.lower()

    def test_valid_approved_to_submitted(self, roster_service):
        """Test APPROVED -> SUBMITTED is allowed"""
        roster_service.validate_status_transition(
            RosterStatus.APPROVED, RosterStatus.SUBMITTED, "match-1", "home"
        )


class TestUpdateJerseyNumbers:
    """Test jersey number updates"""

    @pytest.mark.asyncio
    async def test_update_jersey_numbers_in_scores(self, roster_service, mock_db):
        """Test jersey numbers updated in scores"""
        from bson import ObjectId

        match_id = str(ObjectId())
        jersey_updates = {"p1": 99, "p2": 88}

        await roster_service.update_jersey_numbers(match_id, "home", jersey_updates)

        assert mock_db._matches_collection.update_one.call_count == 6

    @pytest.mark.asyncio
    async def test_update_jersey_numbers_empty_updates(self, roster_service, mock_db):
        """Test no updates when jersey_updates is empty"""
        from bson import ObjectId

        match_id = str(ObjectId())
        await roster_service.update_jersey_numbers(match_id, "home", {})

        mock_db._matches_collection.update_one.assert_not_called()


class TestUpdateRoster:
    """Test roster update operation"""

    @pytest.mark.asyncio
    async def test_update_roster_players(self, roster_service, mock_db):
        """Test successful roster player update"""
        from bson import ObjectId

        from models.matches import EventPlayer, RosterPlayer

        match_id = str(ObjectId())
        test_match = {
            "_id": match_id,
            "home": {
                "roster": {"players": [], "status": "DRAFT", "published": False},
                "scores": [],
                "penalties": [],
            },
        }

        mock_db._matches_collection.find_one = AsyncMock(return_value=test_match)
        mock_db._matches_collection.update_one = AsyncMock(return_value=MagicMock(modified_count=1))

        roster_update = RosterUpdate(
            players=[
                RosterPlayer(
                    player=EventPlayer(
                        playerId="p1", firstName="John", lastName="Doe", jerseyNumber=10
                    ),
                    playerPosition={"key": "FW", "value": "Forward"},
                    passNumber="123",
                )
            ]
        )

        with patch("services.roster_service.populate_event_player_fields", new_callable=AsyncMock):
            result, was_modified = await roster_service.update_roster(
                match_id, "home", roster_update, user_roles=["ADMIN"]
            )

        assert mock_db._matches_collection.update_one.called

    @pytest.mark.asyncio
    async def test_update_roster_strips_transient_fields(self, roster_service, mock_db):
        """Test that display/image fields are stripped from player data before saving"""
        from bson import ObjectId

        from models.matches import EventPlayer, RosterPlayer

        match_id = str(ObjectId())
        test_match = {
            "_id": match_id,
            "home": {
                "roster": {"players": [], "status": "DRAFT", "published": False},
                "scores": [],
                "penalties": [],
            },
        }

        mock_db._matches_collection.find_one = AsyncMock(return_value=test_match)
        mock_db._matches_collection.update_one = AsyncMock(return_value=MagicMock(modified_count=1))

        roster_update = RosterUpdate(
            players=[
                RosterPlayer(
                    player=EventPlayer(
                        playerId="p1",
                        firstName="John",
                        lastName="Doe",
                        jerseyNumber=10,
                        displayFirstName="Johnny",
                        displayLastName="D",
                        imageUrl="https://example.com/photo.jpg",
                        imageVisible=True,
                    ),
                    playerPosition={"key": "FW", "value": "Forward"},
                    passNumber="123",
                )
            ]
        )

        with patch("services.roster_service.populate_event_player_fields", new_callable=AsyncMock):
            result, was_modified = await roster_service.update_roster(
                match_id, "home", roster_update, user_roles=["ADMIN"]
            )

        first_call = mock_db._matches_collection.update_one.call_args_list[0]
        update_dict = first_call[0][1]["$set"]
        saved_player = update_dict["home.roster.players"][0]["player"]
        assert "displayFirstName" not in saved_player
        assert "displayLastName" not in saved_player
        assert "imageUrl" not in saved_player
        assert "imageVisible" not in saved_player
        assert saved_player["playerId"] == "p1"
        assert saved_player["firstName"] == "John"

    @pytest.mark.asyncio
    async def test_update_roster_status_transition(self, roster_service, mock_db):
        """Test roster status update"""
        from bson import ObjectId

        match_id = str(ObjectId())
        test_match = {
            "_id": match_id,
            "home": {
                "roster": {"players": [], "status": "DRAFT", "published": False},
                "scores": [],
                "penalties": [],
            },
        }

        mock_db._matches_collection.find_one = AsyncMock(return_value=test_match)
        mock_db._matches_collection.update_one = AsyncMock(return_value=MagicMock(modified_count=1))

        roster_update = RosterUpdate(status=RosterStatus.SUBMITTED)

        with patch("services.roster_service.populate_event_player_fields", new_callable=AsyncMock):
            result, was_modified = await roster_service.update_roster(
                match_id, "home", roster_update, user_roles=["ADMIN"]
            )

        assert was_modified is True
        call_args = mock_db._matches_collection.update_one.call_args
        update_dict = call_args[0][1]["$set"]
        assert "home.roster.status" in update_dict

    @pytest.mark.asyncio
    async def test_update_roster_submitted_resets_eligibility(self, roster_service, mock_db):
        """Test that transitioning to SUBMITTED resets eligibility data"""
        from bson import ObjectId

        match_id = str(ObjectId())
        test_match = {
            "_id": match_id,
            "home": {
                "roster": {
                    "players": [
                        {
                            "player": {"playerId": "p1", "firstName": "John", "lastName": "Doe"},
                            "playerPosition": {"key": "FW", "value": "Forward"},
                            "passNumber": "123",
                            "eligibilityStatus": "VALID",
                            "invalidReasonCodes": [],
                        }
                    ],
                    "status": "DRAFT",
                    "published": False,
                    "eligibilityTimestamp": "2026-01-01T00:00:00",
                    "eligibilityValidator": "admin-old",
                },
                "scores": [],
                "penalties": [],
            },
        }

        mock_db._matches_collection.find_one = AsyncMock(return_value=test_match)
        mock_db._matches_collection.update_one = AsyncMock(return_value=MagicMock(modified_count=1))

        roster_update = RosterUpdate(status=RosterStatus.SUBMITTED)

        with patch("services.roster_service.populate_event_player_fields", new_callable=AsyncMock):
            result, was_modified = await roster_service.update_roster(
                match_id, "home", roster_update, user_roles=["ADMIN"]
            )

        call_args = mock_db._matches_collection.update_one.call_args
        update_dict = call_args[0][1]["$set"]
        assert update_dict["home.roster.eligibilityTimestamp"] is None
        assert update_dict["home.roster.eligibilityValidator"] is None
        saved_players = update_dict["home.roster.players"]
        for p in saved_players:
            assert p["eligibilityStatus"] == "UNKNOWN"
            assert p["invalidReasonCodes"] == []

    @pytest.mark.asyncio
    async def test_update_roster_draft_resets_eligibility(self, roster_service, mock_db):
        """Test that transitioning to SUBMITTED from APPROVED resets eligibility data"""
        from bson import ObjectId

        match_id = str(ObjectId())
        test_match = {
            "_id": match_id,
            "home": {
                "roster": {
                    "players": [
                        {
                            "player": {"playerId": "p1", "firstName": "John", "lastName": "Doe"},
                            "playerPosition": {"key": "FW", "value": "Forward"},
                            "passNumber": "123",
                            "eligibilityStatus": "INVALID",
                            "invalidReasonCodes": ["SUSPENDED"],
                        }
                    ],
                    "status": "APPROVED",
                    "published": False,
                    "eligibilityTimestamp": "2026-01-01T00:00:00",
                    "eligibilityValidator": "admin-old",
                },
                "scores": [],
                "penalties": [],
            },
        }

        mock_db._matches_collection.find_one = AsyncMock(return_value=test_match)
        mock_db._matches_collection.update_one = AsyncMock(return_value=MagicMock(modified_count=1))

        roster_update = RosterUpdate(status=RosterStatus.SUBMITTED)

        with patch("services.roster_service.populate_event_player_fields", new_callable=AsyncMock):
            result, was_modified = await roster_service.update_roster(
                match_id, "home", roster_update, user_roles=["ADMIN"]
            )

        call_args = mock_db._matches_collection.update_one.call_args
        update_dict = call_args[0][1]["$set"]
        assert update_dict["home.roster.eligibilityTimestamp"] is None
        assert update_dict["home.roster.eligibilityValidator"] is None
        saved_players = update_dict["home.roster.players"]
        assert saved_players[0]["eligibilityStatus"] == "UNKNOWN"
        assert saved_players[0]["invalidReasonCodes"] == []

    @pytest.mark.asyncio
    async def test_update_roster_unauthorized(self, roster_service, mock_db):
        """Test authorization check fails"""
        from bson import ObjectId

        match_id = str(ObjectId())
        roster_update = RosterUpdate(published=True)

        with pytest.raises(AuthorizationException):
            await roster_service.update_roster(match_id, "home", roster_update, user_roles=["USER"])

    @pytest.mark.asyncio
    async def test_update_roster_no_changes(self, roster_service, mock_db):
        """Test handling when no fields provided"""
        from bson import ObjectId

        match_id = str(ObjectId())
        test_match = {
            "_id": match_id,
            "home": {
                "roster": {"players": [], "status": "DRAFT", "published": False},
                "scores": [],
                "penalties": [],
            },
        }

        mock_db._matches_collection.find_one = AsyncMock(return_value=test_match)

        roster_update = RosterUpdate()

        with patch("services.roster_service.populate_event_player_fields", new_callable=AsyncMock):
            result, was_modified = await roster_service.update_roster(
                match_id, "home", roster_update, user_roles=["ADMIN"]
            )

        assert was_modified is False

    @pytest.mark.asyncio
    async def test_update_roster_approved_sets_eligibility(self, roster_service, mock_db):
        """Test that approving roster auto-sets eligibility metadata"""
        from bson import ObjectId

        match_id = str(ObjectId())
        test_match = {
            "_id": match_id,
            "home": {
                "roster": {"players": [], "status": "SUBMITTED", "published": False},
                "scores": [],
                "penalties": [],
            },
        }

        mock_db._matches_collection.find_one = AsyncMock(return_value=test_match)
        mock_db._matches_collection.update_one = AsyncMock(return_value=MagicMock(modified_count=1))

        roster_update = RosterUpdate(status=RosterStatus.APPROVED)

        with patch("services.roster_service.populate_event_player_fields", new_callable=AsyncMock):
            await roster_service.update_roster(
                match_id, "home", roster_update, user_roles=["ADMIN"], user_id="admin-123"
            )

        call_args = mock_db._matches_collection.update_one.call_args
        update_dict = call_args[0][1]["$set"]
        assert "home.roster.eligibilityTimestamp" in update_dict
        assert "home.roster.eligibilityValidator" in update_dict
        assert update_dict["home.roster.eligibilityValidator"] == "admin-123"


class TestGetRosterPlayers:
    """Test get_roster_players convenience method"""

    @pytest.mark.asyncio
    async def test_get_roster_players_returns_list(self, roster_service, mock_db):
        """Test get_roster_players returns player list only"""
        from bson import ObjectId

        match_id = str(ObjectId())
        test_match = {
            "_id": match_id,
            "home": {
                "roster": {
                    "players": [
                        {
                            "player": {"playerId": "p1", "firstName": "John", "lastName": "Doe"},
                            "playerPosition": {"key": "FW", "value": "Forward"},
                            "passNumber": "123",
                        }
                    ],
                    "status": "DRAFT",
                    "published": False,
                }
            },
        }

        mock_db._matches_collection.find_one = AsyncMock(return_value=test_match)

        result = await roster_service.get_roster_players(match_id, "home")

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0].player.playerId == "p1"
