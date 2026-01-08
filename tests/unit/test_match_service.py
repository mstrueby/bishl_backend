"""Unit tests for MatchService"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.match_service import MatchService


@pytest.fixture
def mock_db():
    """Mock MongoDB database"""
    db = MagicMock()

    mock_matches_collection = MagicMock()
    mock_matches_find = MagicMock()
    mock_matches_find.sort = MagicMock(return_value=mock_matches_find)
    mock_matches_find.to_list = AsyncMock()
    mock_matches_collection.find = MagicMock(return_value=mock_matches_find)

    mock_assignments_collection = MagicMock()
    mock_assignments_find = MagicMock()
    mock_assignments_find.to_list = AsyncMock()
    mock_assignments_collection.find = MagicMock(return_value=mock_assignments_find)

    db._matches_collection = mock_matches_collection
    db._matches_find = mock_matches_find
    db._assignments_collection = mock_assignments_collection
    db._assignments_find = mock_assignments_find

    db.__getitem__ = MagicMock(
        side_effect=lambda name: {
            "matches": mock_matches_collection,
            "assignments": mock_assignments_collection,
        }.get(name)
    )

    return db


@pytest.fixture
def match_service(mock_db):
    """MatchService instance with mocked database"""
    return MatchService(mock_db)


class TestGetMatchesForReferee:
    """Test match retrieval for referees"""

    @pytest.mark.asyncio
    async def test_get_matches_as_referee1(self, match_service, mock_db):
        """Test getting matches where user is referee1"""
        test_matches = [
            {
                "_id": "match-1",
                "referee1": {"userId": "ref-123"},
                "startDate": datetime(2024, 1, 15, 18, 0),
            }
        ]

        mock_db._matches_find.to_list = AsyncMock(return_value=test_matches)

        result = await match_service.get_matches_for_referee("ref-123")

        assert len(result) == 1
        assert result[0]["_id"] == "match-1"

        # Verify query structure
        find_call = mock_db._matches_collection.find.call_args[0][0]
        assert "$or" in find_call
        assert {"referee1.userId": "ref-123"} in find_call["$or"]
        assert {"referee2.userId": "ref-123"} in find_call["$or"]

    @pytest.mark.asyncio
    async def test_get_matches_with_date_filter(self, match_service, mock_db):
        """Test getting matches with date filter"""
        test_matches = [
            {
                "_id": "match-1",
                "referee1": {"userId": "ref-123"},
                "startDate": datetime(2024, 2, 1, 18, 0),
            }
        ]

        mock_db._matches_find.to_list = AsyncMock(return_value=test_matches)

        filter_date = datetime(2024, 1, 1)
        result = await match_service.get_matches_for_referee("ref-123", date_from=filter_date)

        assert len(result) == 1

        # Verify date filter in query
        find_call = mock_db._matches_collection.find.call_args[0][0]
        assert "startDate" in find_call
        assert find_call["startDate"]["$gte"] == filter_date

    @pytest.mark.asyncio
    async def test_get_matches_no_results(self, match_service, mock_db):
        """Test getting matches when none exist"""
        mock_db._matches_find.to_list = AsyncMock(return_value=[])

        result = await match_service.get_matches_for_referee("ref-123")

        assert result == []

    @pytest.mark.asyncio
    async def test_matches_sorted_by_start_date(self, match_service, mock_db):
        """Test that matches are sorted by start date"""
        await match_service.get_matches_for_referee("ref-123")

        # Verify sort was called with correct parameters
        mock_db._matches_find.sort.assert_called_once_with("startDate", 1)


class TestGetRefereeAssignments:
    """Test assignment retrieval for referees"""

    @pytest.mark.asyncio
    async def test_get_assignments_success(self, match_service, mock_db):
        """Test successful assignment retrieval"""
        test_assignments = [
            {"_id": "assign-1", "referee": {"userId": "ref-123"}, "matchId": "match-1"},
            {"_id": "assign-2", "referee": {"userId": "ref-123"}, "matchId": "match-2"},
        ]

        mock_db._assignments_find.to_list = AsyncMock(return_value=test_assignments)

        result = await match_service.get_referee_assignments("ref-123")

        assert len(result) == 2
        assert result[0]["_id"] == "assign-1"
        assert result[1]["_id"] == "assign-2"

        # Verify query
        find_call = mock_db._assignments_collection.find.call_args[0][0]
        assert find_call == {"referee.userId": "ref-123"}

    @pytest.mark.asyncio
    async def test_get_assignments_no_results(self, match_service, mock_db):
        """Test when referee has no assignments"""
        mock_db._assignments_find.to_list = AsyncMock(return_value=[])

        result = await match_service.get_referee_assignments("ref-123")

        assert result == []

    @pytest.mark.asyncio
    async def test_get_assignments_different_referee(self, match_service, mock_db):
        """Test assignments are filtered by referee ID"""
        await match_service.get_referee_assignments("ref-456")

        find_call = mock_db._assignments_collection.find.call_args[0][0]
        assert find_call == {"referee.userId": "ref-456"}
