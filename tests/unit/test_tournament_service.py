"""Unit tests for TournamentService"""
from loguru import logger
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime
from bson import ObjectId

from services.tournament_service import TournamentService
from exceptions import ResourceNotFoundException, DatabaseOperationException


@pytest.fixture
def mock_db():
    """Mock MongoDB database"""
    db = MagicMock()

    # Create mock collections
    mock_tournaments_collection = MagicMock()
    mock_tournaments_collection.find_one = AsyncMock()
    mock_tournaments_collection.update_one = AsyncMock(return_value=MagicMock(acknowledged=True))

    mock_matches_collection = MagicMock()
    mock_matches_find = MagicMock()
    mock_matches_find.sort = MagicMock(return_value=mock_matches_find)
    mock_matches_find.to_list = AsyncMock()
    mock_matches_collection.find = MagicMock(return_value=mock_matches_find)

    # Store collections for easier access
    db._tournaments_collection = mock_tournaments_collection
    db._matches_collection = mock_matches_collection
    db._matches_find = mock_matches_find

    db.__getitem__ = MagicMock(side_effect=lambda name: {
        'tournaments': mock_tournaments_collection,
        'matches': mock_matches_collection
    }.get(name))

    return db


@pytest.fixture
def tournament_service(mock_db):
    """TournamentService instance with mocked database"""
    return TournamentService(mock_db)


class TestGetStandingsSettings:
    """Test standings settings retrieval"""

    @pytest.mark.asyncio
    async def test_get_standings_settings_success(self, tournament_service, mock_db):
        """Test successful retrieval of standings settings"""
        test_tournament = {
            "alias": "test-tournament",
            "seasons": [{
                "alias": "test-season",
                "standingsSettings": {
                    "pointsWinReg": 3,
                    "pointsLossReg": 0,
                    "pointsDrawReg": 1
                }
            }]
        }

        mock_db._tournaments_collection.find_one = AsyncMock(return_value=test_tournament)

        result = await tournament_service.get_standings_settings("test-tournament", "test-season")

        assert result["pointsWinReg"] == 3
        assert result["pointsLossReg"] == 0
        assert result["pointsDrawReg"] == 1

    @pytest.mark.asyncio
    async def test_get_standings_settings_tournament_not_found(self, tournament_service, mock_db):
        """Test error when tournament not found"""
        mock_db._tournaments_collection.find_one = AsyncMock(return_value=None)

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await tournament_service.get_standings_settings("invalid-tournament", "test-season")

        assert exc_info.value.details["resource_type"] == "Tournament"
        assert exc_info.value.details["resource_id"] == "invalid-tournament"

    @pytest.mark.asyncio
    async def test_get_standings_settings_season_not_found(self, tournament_service, mock_db):
        """Test error when season not found"""
        test_tournament = {
            "alias": "test-tournament",
            "seasons": [{
                "alias": "other-season",
                "standingsSettings": {}
            }]
        }

        mock_db._tournaments_collection.find_one = AsyncMock(return_value=test_tournament)

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await tournament_service.get_standings_settings("test-tournament", "test-season")

        logger.debug(f"Exception details: {exc_info.value.details}")

        assert exc_info.value.details["resource_type"] == "Season"
        assert exc_info.value.details["resource_id"] == "test-season"

    @pytest.mark.asyncio
    async def test_get_standings_settings_no_settings(self, tournament_service, mock_db):
        """Test error when standings settings missing"""
        test_tournament = {
            "alias": "test-tournament",
            "seasons": [{
                "alias": "test-season"
                # No standingsSettings
            }]
        }

        mock_db._tournaments_collection.find_one = AsyncMock(return_value=test_tournament)

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await tournament_service.get_standings_settings("test-tournament", "test-season")

        assert exc_info.value.details["resource_type"] == "StandingsSettings"


class TestGetMatchdayInfo:
    """Test matchday info retrieval"""

    @pytest.mark.asyncio
    async def test_get_matchday_info_success(self, tournament_service, mock_db):
        """Test successful matchday retrieval"""
        test_tournament = {
            "alias": "test-t",
            "seasons": [{
                "alias": "test-s",
                "rounds": [{
                    "alias": "test-r",
                    "matchdays": [{
                        "alias": "test-md",
                        "refPoints": 50
                    }]
                }]
            }]
        }

        mock_db._tournaments_collection.find_one = AsyncMock(return_value=test_tournament)

        result = await tournament_service.get_matchday_info("test-t", "test-s", "test-r", "test-md")

        assert result["alias"] == "test-md"
        assert result["refPoints"] == 50

    @pytest.mark.asyncio
    async def test_get_matchday_info_not_found(self, tournament_service, mock_db):
        """Test error when matchday not found"""
        test_tournament = {
            "alias": "test-t",
            "seasons": [{
                "alias": "test-s",
                "rounds": [{
                    "alias": "test-r",
                    "matchdays": []
                }]
            }]
        }

        mock_db._tournaments_collection.find_one = AsyncMock(return_value=test_tournament)

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await tournament_service.get_matchday_info("test-t", "test-s", "test-r", "test-md")

        assert exc_info.value.details["resource_type"] == "Matchday"


class TestGetRoundInfo:
    """Test round info retrieval"""

    @pytest.mark.asyncio
    async def test_get_round_info_success(self, tournament_service, mock_db):
        """Test successful round retrieval"""
        test_tournament = {
            "alias": "test-t",
            "seasons": [{
                "alias": "test-s",
                "rounds": [{
                    "alias": "test-r",
                    "name": "Test Round"
                }]
            }]
        }

        mock_db._tournaments_collection.find_one = AsyncMock(return_value=test_tournament)

        result = await tournament_service.get_round_info("test-t", "test-s", "test-r")

        assert result["alias"] == "test-r"
        assert result["name"] == "Test Round"


class TestUpdateRoundDates:
    """Test round date updates"""

    @pytest.mark.asyncio
    async def test_update_round_dates_success(self, tournament_service, mock_db):
        """Test successful round date update"""
        test_matches = [
            {"startDate": datetime(2024, 1, 1, 10, 0)},
            {"startDate": datetime(2024, 1, 15, 10, 0)},
            {"startDate": datetime(2024, 1, 30, 10, 0)}
        ]

        mock_db._matches_find.to_list = AsyncMock(return_value=test_matches)

        await tournament_service.update_round_dates("round-id", "test-t", "test-s", "test-r")

        # Verify update was called with correct dates
        update_call = mock_db._tournaments_collection.update_one.call_args
        assert update_call is not None

        update_doc = update_call[0][1]
        assert update_doc["$set"]["seasons.$[season].rounds.$[round].startDate"] == datetime(2024, 1, 1, 10, 0)
        assert update_doc["$set"]["seasons.$[season].rounds.$[round].endDate"] == datetime(2024, 1, 30, 10, 0)

    @pytest.mark.asyncio
    async def test_update_round_dates_no_matches(self, tournament_service, mock_db):
        """Test handling of no matches found"""
        mock_db._matches_find.to_list = AsyncMock(return_value=[])

        # Should not raise error, just log warning
        await tournament_service.update_round_dates("round-id", "test-t", "test-s", "test-r")

        # Verify update was not called
        mock_db._tournaments_collection.update_one.assert_not_called()


class TestUpdateMatchdayDates:
    """Test matchday date updates"""

    @pytest.mark.asyncio
    async def test_update_matchday_dates_success(self, tournament_service, mock_db):
        """Test successful matchday date update"""
        test_matches = [
            {"startDate": datetime(2024, 1, 5, 18, 0)},
            {"startDate": datetime(2024, 1, 5, 20, 0)}
        ]

        mock_db._matches_find.to_list = AsyncMock(return_value=test_matches)

        await tournament_service.update_matchday_dates("md-id", "test-t", "test-s", "test-r", "test-md")

        # Verify update was called
        update_call = mock_db._tournaments_collection.update_one.call_args
        assert update_call is not None

        update_doc = update_call[0][1]
        assert update_doc["$set"]["seasons.$[season].rounds.$[round].matchdays.$[matchday].startDate"] == datetime(2024, 1, 5, 18, 0)
        assert update_doc["$set"]["seasons.$[season].rounds.$[round].matchdays.$[matchday].endDate"] == datetime(2024, 1, 5, 20, 0)