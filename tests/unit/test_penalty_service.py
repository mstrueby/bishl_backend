"""Unit tests for PenaltyService"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from services.penalty_service import PenaltyService
from exceptions import (
    ValidationException,
    ResourceNotFoundException,
    DatabaseOperationException,
)


@pytest.fixture
def mock_db():
    """Mock MongoDB database"""
    db = MagicMock()

    mock_matches_collection = MagicMock()
    mock_matches_collection.find_one = AsyncMock()
    mock_matches_collection.update_one = AsyncMock()

    db._matches_collection = mock_matches_collection

    db.__getitem__ = MagicMock(side_effect=lambda name: {
        'matches': mock_matches_collection,
    }.get(name))

    return db


@pytest.fixture
def penalty_service(mock_db):
    """PenaltyService instance with mocked database"""
    return PenaltyService(mock_db)


class TestGetPenalties:
    """Test penalty retrieval"""

    @pytest.mark.asyncio
    async def test_get_penalties_success(self, penalty_service, mock_db):
        """Test successful penalties retrieval"""
        from bson import ObjectId

        test_match = {
            "_id": str(ObjectId()),
            "home": {
                "penalties": [
                    {
                        "_id": str(ObjectId()),
                        "matchSecondsStart": 120,
                        "matchSecondsEnd": 240,
                        "penaltyPlayer": {"playerId": "p1", "firstName": "John", "lastName": "Doe"},
                        "penaltyCode": {"key": "B", "value": "Unerlaubter Körperangriff"},
                        "penaltyMinutes": 2
                    }
                ]
            }
        }
        match_id = str(test_match["_id"])

        mock_db._matches_collection.find_one = AsyncMock(return_value=test_match)

        with patch('services.penalty_service.populate_event_player_fields', new_callable=AsyncMock):
            result = await penalty_service.get_penalties(match_id, "home")

        assert len(result) == 1
        assert result[0].matchTimeStart == "02:00"
        assert result[0].matchTimeEnd == "04:00"

    @pytest.mark.asyncio
    async def test_get_penalties_invalid_team_flag(self, penalty_service):
        """Test error with invalid team flag"""
        with pytest.raises(ValidationException) as exc_info:
            await penalty_service.get_penalties("match-1", "invalid")

        assert "Must be 'home' or 'away'" in exc_info.value.message


class TestValidatePenaltyPlayer:
    """Test penalty player validation"""

    @pytest.mark.asyncio
    async def test_validate_player_in_roster(self, penalty_service):
        """Test validation passes when penalty player is in roster"""
        match = {
            "_id": str(ObjectId()),
            "home": {
                "roster": [
                    {"player": {"playerId": "p1"}}
                ]
            }
        }

        penalty_data = {
            "penaltyPlayer": {"playerId": "p1"}
        }

        # Should not raise exception
        await penalty_service._validate_player_in_roster(match, "home", penalty_data)

    @pytest.mark.asyncio
    async def test_validate_player_not_in_roster(self, penalty_service):
        """Test validation fails when penalty player not in roster"""
        match = {
            "_id": str(ObjectId()),
            "home": {
                "roster": [
                    {"player": {"playerId": "p2"}}
                ]
            }
        }

        penalty_data = {
            "penaltyPlayer": {"playerId": "p1"}
        }

        with pytest.raises(ValidationException) as exc_info:
            await penalty_service._validate_player_in_roster(match, "home", penalty_data)

        assert "not in roster" in exc_info.value.message


class TestCreatePenalty:
    """Test penalty creation"""

    @pytest.mark.asyncio
    async def test_create_penalty_success(self, penalty_service, mock_db):
        """Test successful penalty creation with incremental updates"""
        from models.matches import PenaltiesBase, EventPlayer
        from bson import ObjectId

        test_match = {
            "_id": str(ObjectId()),
            "matchStatus": {"key": "INPROGRESS"},
            "home": {
                "roster": [
                    {"player": {"playerId": "p1"}}
                ]
            }
        }
        match_id = str(test_match["_id"])

        mock_db._matches_collection.find_one = AsyncMock(return_value=test_match)
        mock_db._matches_collection.update_one = AsyncMock(
            return_value=MagicMock(modified_count=1)
        )

        penalty = PenaltiesBase(
            matchTimeStart="10:00",
            penaltyPlayer=EventPlayer(playerId="p1", firstName="John", lastName="Doe"),
            penaltyCode={"key": "2MIN", "value": "2 Minutes"},
            penaltyMinutes=2
        )

        with patch.object(penalty_service, 'get_penalty_by_id', new_callable=AsyncMock):
            await penalty_service.create_penalty(match_id, "home", penalty)

        # Verify update was called with incremental operations
        update_call = mock_db._matches_collection.update_one.call_args
        update_operations = update_call[0][1]

        assert "$push" in update_operations
        assert "$inc" in update_operations
        assert update_operations["$inc"]["home.roster.$[penaltyPlayer].penaltyMinutes"] == 2

    @pytest.mark.asyncio
    async def test_create_penalty_wrong_status(self, penalty_service, mock_db):
        """Test penalty creation fails when match not INPROGRESS"""
        from models.matches import PenaltiesBase, EventPlayer
        from bson import ObjectId

        test_match = {
            "_id": str(ObjectId()),
            "matchStatus": {"key": "SCHEDULED"}
        }
        match_id = str(test_match["_id"])

        mock_db._matches_collection.find_one = AsyncMock(return_value=test_match)

        penalty = PenaltiesBase(
            matchTimeStart="10:00",
            penaltyPlayer=EventPlayer(playerId="p1", firstName="John", lastName="Doe"),
            penaltyCode={"key": "2MIN", "value": "2 Minutes"},
            penaltyMinutes=2
        )

        with pytest.raises(ValidationException):
            await penalty_service.create_penalty(match_id, "home", penalty)

    @pytest.mark.asyncio
    async def test_create_game_misconduct_penalty(self, penalty_service, mock_db):
        """Test creation of game misconduct penalty"""
        from models.matches import PenaltiesBase, EventPlayer
        from bson import ObjectId

        test_match = {
            "_id": str(ObjectId()),
            "matchStatus": {"key": "INPROGRESS"},
            "home": {
                "roster": [
                    {"player": {"playerId": "p1"}}
                ]
            }
        }
        match_id = str(test_match["_id"])


        mock_db._matches_collection.find_one = AsyncMock(return_value=test_match)
        mock_db._matches_collection.update_one = AsyncMock(
            return_value=MagicMock(modified_count=1)
        )

        penalty = PenaltiesBase(
            matchTimeStart="15:00",
            penaltyPlayer=EventPlayer(playerId="p1", firstName="John", lastName="Doe"),
            penaltyCode={"key": "GM", "value": "Game Misconduct"},
            penaltyMinutes=10,
            isGM=True
        )

        with patch.object(penalty_service, 'get_penalty_by_id', new_callable=AsyncMock):
            await penalty_service.create_penalty(match_id, "home", penalty)

        # Verify 10 minutes were added
        update_call = mock_db._matches_collection.update_one.call_args
        update_operations = update_call[0][1]
        assert update_operations["$inc"]["home.roster.$[penaltyPlayer].penaltyMinutes"] == 10


class TestDeletePenalty:
    """Test penalty deletion"""

    @pytest.mark.asyncio
    async def test_delete_penalty_success(self, penalty_service, mock_db):
        """Test successful penalty deletion with decremental updates"""
        from bson import ObjectId

        penalty_id = str(ObjectId())
        test_match = {
            "_id": str(ObjectId()),
            "matchStatus": {"key": "INPROGRESS"},
            "home": {
                "penalties": [
                    {
                        "_id": penalty_id,
                        "penaltyPlayer": {"playerId": "p1"},
                        "penaltyMinutes": 2
                    }
                ]
            }
        }
        match_id = str(test_match["_id"])

        mock_db._matches_collection.find_one = AsyncMock(return_value=test_match)
        mock_db._matches_collection.update_one = AsyncMock(
            return_value=MagicMock(modified_count=1)
        )

        await penalty_service.delete_penalty(match_id, "home", penalty_id)

        # Verify decremental update was called
        update_call = mock_db._matches_collection.update_one.call_args
        update_operations = update_call[0][1]

        assert "$pull" in update_operations
        assert "$inc" in update_operations
        assert update_operations["$inc"]["home.roster.$[penaltyPlayer].penaltyMinutes"] == -2

    @pytest.mark.asyncio
    async def test_delete_penalty_not_found(self, penalty_service, mock_db):
        """Test error when penalty not found"""
        test_match = {
            "_id": "match-1",
            "matchStatus": {"key": "INPROGRESS"},
            "home": {
                "penalties": []
            }
        }

        mock_db._matches_collection.find_one = AsyncMock(return_value=test_match)

        with pytest.raises(ResourceNotFoundException):
            await penalty_service.delete_penalty("match-1", "home", "invalid-penalty")


class TestUpdatePenalty:
    """Test penalty updates"""

    @pytest.mark.asyncio
    async def test_update_penalty_success(self, penalty_service, mock_db):
        """Test successful penalty update"""
        from models.matches import PenaltiesUpdate
        from bson import ObjectId

        test_match = {
            "_id": str(ObjectId()),
            "matchStatus": {"key": "INPROGRESS"},
            "home": {
                "roster": [{"player": {"playerId": "p1"}}]
            }
        }
        match_id = str(test_match["_id"])


        mock_db._matches_collection.find_one = AsyncMock(return_value=test_match)
        mock_db._matches_collection.update_one = AsyncMock(
            return_value=MagicMock(modified_count=1)
        )

        penalty_update = PenaltiesUpdate(matchTimeEnd="12:00")

        with patch.object(penalty_service.stats_service, 'calculate_roster_stats', new_callable=AsyncMock):
            with patch.object(penalty_service, 'get_penalty_by_id', new_callable=AsyncMock):
                await penalty_service.update_penalty(match_id, "home", "penalty-1", penalty_update)

        # Verify recalculation was triggered
        penalty_service.stats_service.calculate_roster_stats.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_penalty_no_changes(self, penalty_service, mock_db):
        """Test update with no actual changes"""
        from models.matches import PenaltiesUpdate
        from bson import ObjectId

        test_match = {
            "_id": str(ObjectId()),
            "matchStatus": {"key": "INPROGRESS"},
            "home": {
                "roster": [{"player": {"playerId": "p1"}}]
            }
        }
        match_id = str(test_match["_id"])

        mock_db._matches_collection.find_one = AsyncMock(return_value=test_match)

        penalty_update = PenaltiesUpdate()

        with patch.object(penalty_service, 'get_penalty_by_id', new_callable=AsyncMock) as mock_get:
            await penalty_service.update_penalty(match_id, "home", "penalty-1", penalty_update)

            # Should call get to return current penalty since no changes
            mock_get.assert_called_once()