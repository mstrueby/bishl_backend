
"""Unit tests for ScoreService"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from services.score_service import ScoreService
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
def score_service(mock_db):
    """ScoreService instance with mocked database"""
    return ScoreService(mock_db)


class TestGetScores:
    """Test score retrieval"""
    
    @pytest.mark.asyncio
    async def test_get_scores_success(self, score_service, mock_db):
        """Test successful scores retrieval"""
        test_match = {
            "_id": "match-1",
            "home": {
                "scores": [
                    {
                        "_id": "score-1",
                        "matchSeconds": 630,
                        "goalPlayer": {"playerId": "p1", "firstName": "John", "lastName": "Doe"}
                    }
                ]
            }
        }
        
        mock_db._matches_collection.find_one = AsyncMock(return_value=test_match)
        
        with patch('services.score_service.populate_event_player_fields', new_callable=AsyncMock):
            result = await score_service.get_scores("match-1", "home")
        
        assert len(result) == 1
        assert result[0].matchTime == "10:30"
    
    @pytest.mark.asyncio
    async def test_get_scores_invalid_team_flag(self, score_service):
        """Test error with invalid team flag"""
        with pytest.raises(ValidationException) as exc_info:
            await score_service.get_scores("match-1", "invalid")
        
        assert "Must be 'home' or 'away'" in exc_info.value.message


class TestValidateMatchStatus:
    """Test match status validation"""
    
    @pytest.mark.asyncio
    async def test_validate_inprogress_status_success(self, score_service):
        """Test validation passes for INPROGRESS match"""
        match = {"matchStatus": {"key": "INPROGRESS"}}
        
        # Should not raise exception
        await score_service._validate_match_status(match)
    
    @pytest.mark.asyncio
    async def test_validate_scheduled_status_fails(self, score_service):
        """Test validation fails for SCHEDULED match"""
        match = {"matchStatus": {"key": "SCHEDULED"}}
        
        with pytest.raises(ValidationException) as exc_info:
            await score_service._validate_match_status(match)
        
        assert "INPROGRESS" in exc_info.value.message


class TestValidatePlayerInRoster:
    """Test player roster validation"""
    
    @pytest.mark.asyncio
    async def test_validate_goal_player_in_roster(self, score_service):
        """Test validation passes when goal player is in roster"""
        match = {
            "_id": "match-1",
            "home": {
                "roster": [
                    {"player": {"playerId": "p1"}}
                ]
            }
        }
        
        score_data = {
            "goalPlayer": {"playerId": "p1"},
            "assistPlayer": None
        }
        
        # Should not raise exception
        await score_service._validate_player_in_roster(match, "home", score_data)
    
    @pytest.mark.asyncio
    async def test_validate_goal_player_not_in_roster(self, score_service):
        """Test validation fails when goal player not in roster"""
        match = {
            "_id": "match-1",
            "home": {
                "roster": [
                    {"player": {"playerId": "p2"}}
                ]
            }
        }
        
        score_data = {
            "goalPlayer": {"playerId": "p1"}
        }
        
        with pytest.raises(ValidationException) as exc_info:
            await score_service._validate_player_in_roster(match, "home", score_data)
        
        assert "not in roster" in exc_info.value.message
    
    @pytest.mark.asyncio
    async def test_validate_assist_player_not_in_roster(self, score_service):
        """Test validation fails when assist player not in roster"""
        match = {
            "_id": "match-1",
            "home": {
                "roster": [
                    {"player": {"playerId": "p1"}}
                ]
            }
        }
        
        score_data = {
            "goalPlayer": {"playerId": "p1"},
            "assistPlayer": {"playerId": "p2"}
        }
        
        with pytest.raises(ValidationException) as exc_info:
            await score_service._validate_player_in_roster(match, "home", score_data)
        
        assert "Assist player" in exc_info.value.message


class TestCreateScore:
    """Test score creation"""
    
    @pytest.mark.asyncio
    async def test_create_score_success(self, score_service, mock_db):
        """Test successful score creation with incremental updates"""
        from models.matches import ScoresBase, EventPlayer
        
        test_match = {
            "_id": "match-1",
            "matchStatus": {"key": "INPROGRESS"},
            "tournament": {"alias": "test-tournament"},
            "season": {"alias": "test-season"},
            "round": {"alias": "test-round"},
            "matchday": {"alias": "test-matchday"},
            "home": {
                "roster": [
                    {"player": {"playerId": "p1"}},
                    {"player": {"playerId": "p2"}}
                ]
            }
        }
        
        mock_db._matches_collection.find_one = AsyncMock(return_value=test_match)
        mock_db._matches_collection.update_one = AsyncMock(
            return_value=MagicMock(modified_count=1)
        )
        
        score = ScoresBase(
            matchTime="10:30",
            goalPlayer=EventPlayer(playerId="p1", firstName="John", lastName="Doe"),
            assistPlayer=EventPlayer(playerId="p2", firstName="Jane", lastName="Doe")
        )
        
        with patch.object(score_service.stats_service, 'aggregate_round_standings', new_callable=AsyncMock):
            with patch.object(score_service.stats_service, 'aggregate_matchday_standings', new_callable=AsyncMock):
                with patch.object(score_service, 'get_score_by_id', new_callable=AsyncMock):
                    await score_service.create_score("match-1", "home", score)
        
        # Verify update was called with incremental operations
        update_call = mock_db._matches_collection.update_one.call_args
        update_operations = update_call[0][1]
        
        assert "$push" in update_operations
        assert "$inc" in update_operations
        assert update_operations["$inc"]["home.stats.goalsFor"] == 1
        assert update_operations["$inc"]["away.stats.goalsAgainst"] == 1
    
    @pytest.mark.asyncio
    async def test_create_score_wrong_status(self, score_service, mock_db):
        """Test score creation fails when match not INPROGRESS"""
        from models.matches import ScoresBase, EventPlayer
        
        test_match = {
            "_id": "match-1",
            "matchStatus": {"key": "SCHEDULED"}
        }
        
        mock_db._matches_collection.find_one = AsyncMock(return_value=test_match)
        
        score = ScoresBase(
            matchTime="10:30",
            goalPlayer=EventPlayer(playerId="p1", firstName="John", lastName="Doe")
        )
        
        with pytest.raises(ValidationException):
            await score_service.create_score("match-1", "home", score)


class TestDeleteScore:
    """Test score deletion"""
    
    @pytest.mark.asyncio
    async def test_delete_score_success(self, score_service, mock_db):
        """Test successful score deletion with decremental updates"""
        test_match = {
            "_id": "match-1",
            "matchStatus": {"key": "INPROGRESS"},
            "tournament": {"alias": "test-tournament"},
            "season": {"alias": "test-season"},
            "round": {"alias": "test-round"},
            "matchday": {"alias": "test-matchday"},
            "home": {
                "scores": [
                    {
                        "_id": "score-1",
                        "goalPlayer": {"playerId": "p1"},
                        "assistPlayer": {"playerId": "p2"}
                    }
                ]
            }
        }
        
        mock_db._matches_collection.find_one = AsyncMock(return_value=test_match)
        mock_db._matches_collection.update_one = AsyncMock(
            return_value=MagicMock(modified_count=1)
        )
        
        with patch.object(score_service.stats_service, 'aggregate_round_standings', new_callable=AsyncMock):
            with patch.object(score_service.stats_service, 'aggregate_matchday_standings', new_callable=AsyncMock):
                await score_service.delete_score("match-1", "home", "score-1")
        
        # Verify decremental update was called
        update_call = mock_db._matches_collection.update_one.call_args
        update_operations = update_call[0][1]
        
        assert "$pull" in update_operations
        assert "$inc" in update_operations
        assert update_operations["$inc"]["home.stats.goalsFor"] == -1
        assert update_operations["$inc"]["away.stats.goalsAgainst"] == -1
    
    @pytest.mark.asyncio
    async def test_delete_score_not_found(self, score_service, mock_db):
        """Test error when score not found"""
        test_match = {
            "_id": "match-1",
            "matchStatus": {"key": "INPROGRESS"},
            "home": {
                "scores": []
            }
        }
        
        mock_db._matches_collection.find_one = AsyncMock(return_value=test_match)
        
        with pytest.raises(ResourceNotFoundException):
            await score_service.delete_score("match-1", "home", "invalid-score")


class TestUpdateScore:
    """Test score updates"""
    
    @pytest.mark.asyncio
    async def test_update_score_success(self, score_service, mock_db):
        """Test successful score update"""
        from models.matches import ScoresUpdate
        
        test_match = {
            "_id": "match-1",
            "matchStatus": {"key": "INPROGRESS"},
            "home": {
                "roster": [{"player": {"playerId": "p1"}}]
            }
        }
        
        mock_db._matches_collection.find_one = AsyncMock(return_value=test_match)
        mock_db._matches_collection.update_one = AsyncMock(
            return_value=MagicMock(modified_count=1)
        )
        
        score_update = ScoresUpdate(matchTime="15:00")
        
        with patch.object(score_service.stats_service, 'calculate_roster_stats', new_callable=AsyncMock):
            with patch.object(score_service, 'get_score_by_id', new_callable=AsyncMock):
                await score_service.update_score("match-1", "home", "score-1", score_update)
        
        # Verify recalculation was triggered
        score_service.stats_service.calculate_roster_stats.assert_called_once()
