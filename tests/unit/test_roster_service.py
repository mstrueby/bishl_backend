
"""Unit tests for RosterService"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from services.roster_service import RosterService
from exceptions import (
    ValidationException,
    ResourceNotFoundException,
    AuthorizationException,
    DatabaseOperationException,
)


@pytest.fixture
def mock_db():
    """Mock MongoDB database"""
    from bson import ObjectId
    
    db = MagicMock()
    
    mock_matches_collection = MagicMock()
    mock_matches_collection.find_one = AsyncMock()
    mock_matches_collection.update_one = AsyncMock()
    
    mock_players_collection = MagicMock()
    mock_players_collection.find_one = AsyncMock(return_value=None)
    
    db._matches_collection = mock_matches_collection
    
    db.__getitem__ = MagicMock(side_effect=lambda name: {
        'matches': mock_matches_collection,
        'players': mock_players_collection,
    }.get(name))
    
    return db


@pytest.fixture
def roster_service(mock_db):
    """RosterService instance with mocked database"""
    return RosterService(mock_db)


class TestGetRoster:
    """Test roster retrieval"""
    


    @pytest.mark.asyncio
    async def test_validate_roster_duplicate_players(self, roster_service):
        """Test validation fails when roster contains duplicate players"""
        from models.matches import RosterPlayer, EventPlayer
        from bson import ObjectId
        
        match_id = str(ObjectId())
        match = {
            "_id": match_id,
            "home": {
                "scores": [],
                "penalties": []
            }
        }
        
        # Create roster with duplicate player
        new_roster = [
            RosterPlayer(
                player=EventPlayer(playerId="p1", firstName="John", lastName="Doe"),
                playerPosition={"key": "FW", "value": "Forward"},
                passNumber="123"
            ),
            RosterPlayer(
                player=EventPlayer(playerId="p1", firstName="John", lastName="Doe"),
                playerPosition={"key": "DF", "value": "Defense"},
                passNumber="456"
            )
        ]
        
        with pytest.raises(ValidationException) as exc_info:
            await roster_service.validate_roster_changes(match, "home", new_roster)
        
        assert "duplicate players" in exc_info.value.message.lower()
        assert "p1" in exc_info.value.details["duplicate_player_ids"]

    @pytest.mark.asyncio
    async def test_get_roster_success(self, roster_service, mock_db):
        """Test successful roster retrieval"""
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
                        "goals": 2,
                        "assists": 1
                    }
                ]
            }
        }
        
        mock_db._matches_collection.find_one = AsyncMock(return_value=test_match)
        
        result = await roster_service.get_roster(match_id, "home")
        
        assert len(result) == 1
        assert result[0].player.playerId == "p1"
        assert result[0].goals == 2
    
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
            "home": {"roster": []}
        }
        
        mock_db._matches_collection.find_one = AsyncMock(return_value=test_match)
        
        result = await roster_service.get_roster(match_id, "home")
        
        assert result == []


class TestValidateRosterChanges:
    """Test roster validation"""
    
    @pytest.mark.asyncio
    async def test_validate_roster_with_scores_success(self, roster_service):
        """Test successful validation when players in scores are in roster"""
        from models.matches import RosterPlayer, EventPlayer
        from bson import ObjectId
        
        match_id = str(ObjectId())
        match = {
            "_id": match_id,
            "home": {
                "scores": [
                    {"goalPlayer": {"playerId": "p1"}, "assistPlayer": {"playerId": "p2"}}
                ],
                "penalties": []
            }
        }
        
        new_roster = [
            RosterPlayer(
                player=EventPlayer(playerId="p1", firstName="John", lastName="Doe"),
                playerPosition={"key": "FW", "value": "Forward"},
                passNumber="123"
            ),
            RosterPlayer(
                player=EventPlayer(playerId="p2", firstName="Jane", lastName="Doe"),
                playerPosition={"key": "DF", "value": "Defense"},
                passNumber="456"
            )
        ]
        
        # Should not raise exception
        await roster_service.validate_roster_changes(match, "home", new_roster)
    
    @pytest.mark.asyncio
    async def test_validate_roster_missing_goal_player(self, roster_service):
        """Test validation fails when goal player not in roster"""
        from models.matches import RosterPlayer, EventPlayer
        from bson import ObjectId
        
        match_id = str(ObjectId())
        match = {
            "_id": match_id,
            "home": {
                "scores": [
                    {"goalPlayer": {"playerId": "p1"}, "assistPlayer": None}
                ],
                "penalties": []
            }
        }
        
        new_roster = [
            RosterPlayer(
                player=EventPlayer(playerId="p2", firstName="Jane", lastName="Doe"),
                playerPosition={"key": "DF", "value": "Defense"},
                passNumber="456"
            )
        ]
        
        with pytest.raises(ValidationException) as exc_info:
            await roster_service.validate_roster_changes(match, "home", new_roster)
        
        assert "players in scores must be in roster" in exc_info.value.message
    
    @pytest.mark.asyncio
    async def test_validate_roster_missing_penalty_player(self, roster_service):
        """Test validation fails when penalty player not in roster"""
        from models.matches import RosterPlayer, EventPlayer
        from bson import ObjectId
        
        match_id = str(ObjectId())
        match = {
            "_id": match_id,
            "home": {
                "scores": [],
                "penalties": [
                    {"penaltyPlayer": {"playerId": "p1"}}
                ]
            }
        }
        
        new_roster = [
            RosterPlayer(
                player=EventPlayer(playerId="p2", firstName="Jane", lastName="Doe"),
                playerPosition={"key": "DF", "value": "Defense"},
                passNumber="456"
            )
        ]
        
        with pytest.raises(ValidationException) as exc_info:
            await roster_service.validate_roster_changes(match, "home", new_roster)
        
        assert "players in penalties must be in roster" in exc_info.value.message


class TestUpdateJerseyNumbers:
    """Test jersey number updates"""
    
    @pytest.mark.asyncio
    async def test_update_jersey_numbers_in_scores(self, roster_service, mock_db):
        """Test jersey numbers updated in scores"""
        from bson import ObjectId
        
        match_id = str(ObjectId())
        jersey_updates = {"p1": 99, "p2": 88}
        
        await roster_service.update_jersey_numbers(match_id, "home", jersey_updates)
        
        # Should have called update_one 4 times (goal players, assist players, penalties for each player)
        assert mock_db._matches_collection.update_one.call_count == 6  # 2 players * 3 updates each
    
    @pytest.mark.asyncio
    async def test_update_jersey_numbers_empty_updates(self, roster_service, mock_db):
        """Test no updates when jersey_updates is empty"""
        from bson import ObjectId
        
        match_id = str(ObjectId())
        await roster_service.update_jersey_numbers(match_id, "home", {})
        
        # Should not call update_one
        mock_db._matches_collection.update_one.assert_not_called()


class TestUpdateRoster:
    """Test roster update operation"""
    
    @pytest.mark.asyncio
    async def test_update_roster_success(self, roster_service, mock_db):
        """Test successful roster update"""
        from models.matches import RosterPlayer, EventPlayer
        from bson import ObjectId
        
        match_id = str(ObjectId())
        test_match = {
            "_id": match_id,
            "home": {
                "roster": [],
                "scores": [],
                "penalties": []
            }
        }
        
        mock_db._matches_collection.find_one = AsyncMock(return_value=test_match)
        mock_db._matches_collection.update_one = AsyncMock(
            return_value=MagicMock(modified_count=1)
        )
        
        new_roster = [
            RosterPlayer(
                player=EventPlayer(playerId="p1", firstName="John", lastName="Doe", jerseyNumber=10),
                playerPosition={"key": "FW", "value": "Forward"},
                passNumber="123"
            )
        ]
        
        with patch('services.roster_service.populate_event_player_fields', new_callable=AsyncMock):
            result = await roster_service.update_roster(
                match_id, "home", new_roster, user_roles=["ADMIN"]
            )
        
        # Verify update was called
        assert mock_db._matches_collection.update_one.called
    
    @pytest.mark.asyncio
    async def test_update_roster_unauthorized(self, roster_service, mock_db):
        """Test authorization check fails"""
        from models.matches import RosterPlayer
        from bson import ObjectId
        
        match_id = str(ObjectId())
        with pytest.raises(AuthorizationException):
            await roster_service.update_roster(
                match_id, "home", [], user_roles=["USER"]
            )
    
    @pytest.mark.asyncio
    async def test_update_roster_no_changes(self, roster_service, mock_db):
        """Test error when no changes detected"""
        from models.matches import RosterPlayer, EventPlayer
        from bson import ObjectId
        
        match_id = str(ObjectId())
        test_match = {
            "_id": match_id,
            "home": {
                "roster": [],
                "scores": [],
                "penalties": []
            }
        }
        
        mock_db._matches_collection.find_one = AsyncMock(return_value=test_match)
        mock_db._matches_collection.update_one = AsyncMock(
            return_value=MagicMock(modified_count=0)
        )
        
        new_roster = [
            RosterPlayer(
                player=EventPlayer(playerId="p1", firstName="John", lastName="Doe"),
                playerPosition={"key": "FW", "value": "Forward"},
                passNumber="123"
            )
        ]
        
        with patch('services.roster_service.populate_event_player_fields', new_callable=AsyncMock):
            with pytest.raises(DatabaseOperationException):
                await roster_service.update_roster(
                    match_id, "home", new_roster, user_roles=["ADMIN"]
                )
