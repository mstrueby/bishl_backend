"""Unit tests for AssignmentService reftool methods"""

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from exceptions import ResourceNotFoundException, ValidationException
from services.assignment_service import AssignmentService


@pytest.fixture
def mock_db():
    """Mock MongoDB database"""
    db = MagicMock()

    mock_assignments_collection = MagicMock()
    mock_assignments_collection.find_one = AsyncMock()
    mock_assignments_collection.count_documents = AsyncMock(return_value=0)

    mock_assignments_find = MagicMock()
    mock_assignments_find.to_list = AsyncMock(return_value=[])
    mock_assignments_collection.find = MagicMock(return_value=mock_assignments_find)

    mock_users_collection = MagicMock()
    mock_users_collection.find_one = AsyncMock()
    mock_users_collection.count_documents = AsyncMock(return_value=0)

    mock_users_find = MagicMock()
    mock_users_find.to_list = AsyncMock(return_value=[])
    mock_users_collection.find = MagicMock(return_value=mock_users_find)

    mock_matches_collection = MagicMock()
    mock_matches_collection.find_one = AsyncMock()

    mock_matches_find = MagicMock()
    mock_matches_find.to_list = AsyncMock(return_value=[])
    mock_matches_collection.find = MagicMock(return_value=mock_matches_find)

    mock_matches_aggregate = MagicMock()
    mock_matches_aggregate.to_list = AsyncMock(return_value=[])
    mock_matches_collection.aggregate = MagicMock(return_value=mock_matches_aggregate)

    db._assignments_collection = mock_assignments_collection
    db._assignments_find = mock_assignments_find
    db._users_collection = mock_users_collection
    db._users_find = mock_users_find
    db._matches_collection = mock_matches_collection
    db._matches_find = mock_matches_find
    db._matches_aggregate = mock_matches_aggregate

    db.__getitem__ = MagicMock(
        side_effect=lambda name: {
            "assignments": mock_assignments_collection,
            "users": mock_users_collection,
            "matches": mock_matches_collection,
        }.get(name)
    )

    return db


@pytest.fixture
def assignment_service(mock_db):
    return AssignmentService(mock_db)


class TestGetMatchesByDayRange:
    """
    Tests for get_matches_by_day_range.

    The service uses a MongoDB aggregation pipeline which is mocked at the
    aggregate cursor level. The mock returns pre-computed refSummary objects
    as MongoDB would. The service then groups results by date and adds
    tournamentSummary per day group.
    """

    @pytest.mark.asyncio
    async def test_returns_grouped_days_with_matches_and_tournament_summary(
        self, assignment_service, mock_db
    ):
        """Normal result: returns per-day groups with matches and tournamentSummary"""
        start = date(2026, 3, 1)
        end = date(2026, 3, 7)

        match_dt = datetime(2026, 3, 3, 15, 0)
        pipeline_result = [
            {
                "_id": "match-1",
                "startDate": match_dt,
                "tournament": {"name": "Test League", "alias": "test-league"},
                "refSummary": {
                    "assignedCount": 1,
                    "requestedCount": 1,
                    "availableCount": 8,
                    "requestsByLevel": {"S1": 1},
                },
            }
        ]
        mock_db._matches_aggregate.to_list = AsyncMock(return_value=pipeline_result)
        mock_db._users_collection.count_documents = AsyncMock(return_value=10)

        result = await assignment_service.get_matches_by_day_range(start, end)

        assert len(result) == 1
        day = result[0]
        assert day["date"] == "2026-03-03"
        assert len(day["matches"]) == 1
        assert day["matches"][0]["_id"] == "match-1"
        ref_summary = day["matches"][0]["refSummary"]
        assert ref_summary["assignedCount"] == 1
        assert ref_summary["requestedCount"] == 1
        assert ref_summary["availableCount"] == 8
        assert ref_summary["requestsByLevel"] == {"S1": 1}
        mock_db._matches_collection.aggregate.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_date_range_returns_empty_list(self, assignment_service, mock_db):
        """No matches in range: returns empty list"""
        mock_db._matches_aggregate.to_list = AsyncMock(return_value=[])
        mock_db._users_collection.count_documents = AsyncMock(return_value=5)

        result = await assignment_service.get_matches_by_day_range(
            date(2026, 1, 1), date(2026, 1, 7)
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_zero_counts_when_no_assignments(self, assignment_service, mock_db):
        """All refSummary counts are zero when aggregate returns zero-count refSummary"""
        match_dt = datetime(2026, 3, 5, 10, 0)
        pipeline_result = [
            {
                "_id": "match-2",
                "startDate": match_dt,
                "tournament": {"name": "Test League", "alias": "test-league"},
                "refSummary": {
                    "assignedCount": 0,
                    "requestedCount": 0,
                    "availableCount": 5,
                    "requestsByLevel": {},
                },
            }
        ]
        mock_db._matches_aggregate.to_list = AsyncMock(return_value=pipeline_result)
        mock_db._users_collection.count_documents = AsyncMock(return_value=5)

        result = await assignment_service.get_matches_by_day_range(
            date(2026, 3, 1), date(2026, 3, 7)
        )

        assert len(result) == 1
        summary = result[0]["matches"][0]["refSummary"]
        assert summary["assignedCount"] == 0
        assert summary["requestedCount"] == 0
        assert summary["availableCount"] == 5
        assert summary["requestsByLevel"] == {}

    @pytest.mark.asyncio
    async def test_requests_by_level_grouping(self, assignment_service, mock_db):
        """requestsByLevel grouping is preserved from aggregate output"""
        match_dt = datetime(2026, 3, 5, 10, 0)
        pipeline_result = [
            {
                "_id": "match-3",
                "startDate": match_dt,
                "tournament": {"name": "Test League", "alias": "test-league"},
                "refSummary": {
                    "assignedCount": 0,
                    "requestedCount": 3,
                    "availableCount": 17,
                    "requestsByLevel": {"S2": 2, "S1": 1},
                },
            }
        ]
        mock_db._matches_aggregate.to_list = AsyncMock(return_value=pipeline_result)
        mock_db._users_collection.count_documents = AsyncMock(return_value=20)

        result = await assignment_service.get_matches_by_day_range(
            date(2026, 3, 1), date(2026, 3, 7)
        )

        summary = result[0]["matches"][0]["refSummary"]
        assert summary["requestsByLevel"] == {"S2": 2, "S1": 1}

    @pytest.mark.asyncio
    async def test_accepted_status_counts_as_assigned(self, assignment_service, mock_db):
        """ACCEPTED status is counted in assignedCount (verified via aggregate result)"""
        match_dt = datetime(2026, 3, 5, 10, 0)
        pipeline_result = [
            {
                "_id": "match-4",
                "startDate": match_dt,
                "tournament": {"name": "Test League", "alias": "test-league"},
                "refSummary": {
                    "assignedCount": 1,
                    "requestedCount": 0,
                    "availableCount": 4,
                    "requestsByLevel": {},
                },
            }
        ]
        mock_db._matches_aggregate.to_list = AsyncMock(return_value=pipeline_result)
        mock_db._users_collection.count_documents = AsyncMock(return_value=5)

        result = await assignment_service.get_matches_by_day_range(
            date(2026, 3, 1), date(2026, 3, 7)
        )

        assert result[0]["matches"][0]["refSummary"]["assignedCount"] == 1

    @pytest.mark.asyncio
    async def test_date_range_exceeds_30_days_raises_validation_error(
        self, assignment_service, mock_db
    ):
        """Date range >= 30 days raises ValidationException at service layer"""
        with pytest.raises(ValidationException) as exc_info:
            await assignment_service.get_matches_by_day_range(date(2026, 1, 1), date(2026, 1, 31))

        assert "30 days" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_aggregate_pipeline_called_with_date_filter(self, assignment_service, mock_db):
        """Aggregate is called with a $match stage covering the date range"""
        mock_db._matches_aggregate.to_list = AsyncMock(return_value=[])
        mock_db._users_collection.count_documents = AsyncMock(return_value=0)

        await assignment_service.get_matches_by_day_range(date(2026, 3, 1), date(2026, 3, 7))

        mock_db._matches_collection.aggregate.assert_called_once()
        pipeline = mock_db._matches_collection.aggregate.call_args[0][0]
        assert pipeline[0]["$match"]["startDate"]["$gte"].date() == date(2026, 3, 1)
        assert pipeline[0]["$match"]["startDate"]["$lte"].date() == date(2026, 3, 7)

    @pytest.mark.asyncio
    async def test_tournament_summary_counts_per_tournament(self, assignment_service, mock_db):
        """tournamentSummary counts fullyAssigned/partiallyAssigned/unassigned per tournament alias"""
        match_dt = datetime(2026, 3, 3, 10, 0)
        pipeline_result = [
            {
                "_id": "m1",
                "startDate": match_dt,
                "tournament": {"name": "League A", "alias": "league-a"},
                "refSummary": {
                    "assignedCount": 2,
                    "requestedCount": 0,
                    "availableCount": 3,
                    "requestsByLevel": {},
                },
            },
            {
                "_id": "m2",
                "startDate": match_dt,
                "tournament": {"name": "League A", "alias": "league-a"},
                "refSummary": {
                    "assignedCount": 1,
                    "requestedCount": 0,
                    "availableCount": 3,
                    "requestsByLevel": {},
                },
            },
            {
                "_id": "m3",
                "startDate": match_dt,
                "tournament": {"name": "League B", "alias": "league-b"},
                "refSummary": {
                    "assignedCount": 0,
                    "requestedCount": 0,
                    "availableCount": 5,
                    "requestsByLevel": {},
                },
            },
        ]
        mock_db._matches_aggregate.to_list = AsyncMock(return_value=pipeline_result)
        mock_db._users_collection.count_documents = AsyncMock(return_value=5)

        result = await assignment_service.get_matches_by_day_range(
            date(2026, 3, 1), date(2026, 3, 7)
        )

        assert len(result) == 1
        day = result[0]
        assert day["date"] == "2026-03-03"
        assert len(day["matches"]) == 3

        ts = {entry["tournamentAlias"]: entry["counts"] for entry in day["tournamentSummary"]}
        assert set(ts.keys()) == {"league-a", "league-b"}

        assert ts["league-a"]["totalMatches"] == 2
        assert ts["league-a"]["fullyAssigned"] == 1
        assert ts["league-a"]["partiallyAssigned"] == 1
        assert ts["league-a"]["unassigned"] == 0

        assert ts["league-b"]["totalMatches"] == 1
        assert ts["league-b"]["fullyAssigned"] == 0
        assert ts["league-b"]["partiallyAssigned"] == 0
        assert ts["league-b"]["unassigned"] == 1

    @pytest.mark.asyncio
    async def test_tournament_summary_only_includes_tournaments_with_matches(
        self, assignment_service, mock_db
    ):
        """tournamentSummary contains only tournaments present on that day"""
        match_dt = datetime(2026, 3, 3, 10, 0)
        pipeline_result = [
            {
                "_id": "m1",
                "startDate": match_dt,
                "tournament": {"name": "Only League", "alias": "only-league"},
                "refSummary": {
                    "assignedCount": 2,
                    "requestedCount": 0,
                    "availableCount": 3,
                    "requestsByLevel": {},
                },
            },
        ]
        mock_db._matches_aggregate.to_list = AsyncMock(return_value=pipeline_result)
        mock_db._users_collection.count_documents = AsyncMock(return_value=5)

        result = await assignment_service.get_matches_by_day_range(
            date(2026, 3, 1), date(2026, 3, 7)
        )

        day = result[0]
        assert len(day["tournamentSummary"]) == 1
        assert day["tournamentSummary"][0]["tournamentAlias"] == "only-league"

    @pytest.mark.asyncio
    async def test_matches_grouped_by_day_across_multiple_days(self, assignment_service, mock_db):
        """Matches on different days produce separate day entries, each with tournamentSummary"""
        pipeline_result = [
            {
                "_id": "m1",
                "startDate": datetime(2026, 3, 1, 10, 0),
                "tournament": {"name": "League A", "alias": "league-a"},
                "refSummary": {
                    "assignedCount": 0,
                    "requestedCount": 0,
                    "availableCount": 5,
                    "requestsByLevel": {},
                },
            },
            {
                "_id": "m2",
                "startDate": datetime(2026, 3, 3, 14, 0),
                "tournament": {"name": "League A", "alias": "league-a"},
                "refSummary": {
                    "assignedCount": 2,
                    "requestedCount": 0,
                    "availableCount": 3,
                    "requestsByLevel": {},
                },
            },
        ]
        mock_db._matches_aggregate.to_list = AsyncMock(return_value=pipeline_result)
        mock_db._users_collection.count_documents = AsyncMock(return_value=5)

        result = await assignment_service.get_matches_by_day_range(
            date(2026, 3, 1), date(2026, 3, 7)
        )

        assert len(result) == 2
        assert result[0]["date"] == "2026-03-01"
        assert result[1]["date"] == "2026-03-03"
        assert result[0]["tournamentSummary"][0]["counts"]["unassigned"] == 1
        assert result[1]["tournamentSummary"][0]["counts"]["fullyAssigned"] == 1


class TestGetRefereeOptionsForMatch:

    @pytest.mark.asyncio
    async def test_returns_assigned_requested_available_lists(self, assignment_service, mock_db):
        """Normal result with all three lists populated"""
        test_match = {"_id": "match-1", "startDate": datetime(2026, 3, 5)}
        mock_db._matches_collection.find_one = AsyncMock(return_value=test_match)

        mock_db._assignments_find.to_list = AsyncMock(
            return_value=[
                {
                    "_id": "a1",
                    "matchId": "match-1",
                    "status": "ASSIGNED",
                    "position": 1,
                    "referee": {
                        "userId": "ref-1",
                        "firstName": "Alice",
                        "lastName": "A",
                        "clubId": None,
                        "clubName": None,
                        "logoUrl": None,
                        "level": "S2",
                    },
                },
                {
                    "_id": "a2",
                    "matchId": "match-1",
                    "status": "REQUESTED",
                    "position": None,
                    "referee": {
                        "userId": "ref-2",
                        "firstName": "Bob",
                        "lastName": "B",
                        "clubId": None,
                        "clubName": None,
                        "logoUrl": None,
                        "level": "S1",
                    },
                },
                {
                    "_id": "a3",
                    "matchId": "match-1",
                    "status": "UNAVAILABLE",
                    "position": None,
                    "referee": {
                        "userId": "ref-4",
                        "firstName": "David",
                        "lastName": "D",
                        "clubId": None,
                        "clubName": None,
                        "logoUrl": None,
                        "level": "S1",
                    },
                },
            ]
        )

        mock_db._users_find.to_list = AsyncMock(
            return_value=[
                {
                    "_id": "ref-1",
                    "firstName": "Alice",
                    "lastName": "A",
                    "roles": ["REFEREE"],
                    "referee": {"active": True, "level": "S2"},
                },
                {
                    "_id": "ref-2",
                    "firstName": "Bob",
                    "lastName": "B",
                    "roles": ["REFEREE"],
                    "referee": {"active": True, "level": "S1"},
                },
                {
                    "_id": "ref-3",
                    "firstName": "Carol",
                    "lastName": "C",
                    "roles": ["REFEREE"],
                    "referee": {"active": True, "level": "S2"},
                },
                {
                    "_id": "ref-4",
                    "firstName": "David",
                    "lastName": "D",
                    "roles": ["REFEREE"],
                    "referee": {"active": True, "level": "S1"},
                },
            ]
        )

        result = await assignment_service.get_referee_options_for_match("match-1")

        assert result.id == "match-1"
        assert len(result.assigned) == 1
        assert result.assigned[0].userId == "ref-1"
        assert len(result.requested) == 1
        assert result.requested[0].userId == "ref-2"
        assert len(result.available) == 1
        assert result.available[0].userId == "ref-3"
        assert len(result.unavailable) == 1
        assert result.unavailable[0].userId == "ref-4"
        assert result.unavailable[0].status == "UNAVAILABLE"

    @pytest.mark.asyncio
    async def test_match_not_found_raises_exception(self, assignment_service, mock_db):
        """Missing match raises ResourceNotFoundException"""
        mock_db._matches_collection.find_one = AsyncMock(return_value=None)

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await assignment_service.get_referee_options_for_match("nonexistent-id")

        assert "Match" in str(exc_info.value)
        assert "nonexistent-id" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_level_filter_applied(self, assignment_service, mock_db):
        """levelFilter is passed to user query"""
        test_match = {"_id": "match-1", "startDate": datetime(2026, 3, 5)}
        mock_db._matches_collection.find_one = AsyncMock(return_value=test_match)
        mock_db._assignments_find.to_list = AsyncMock(return_value=[])
        mock_db._users_find.to_list = AsyncMock(return_value=[])

        await assignment_service.get_referee_options_for_match("match-1", level_filter="S2")

        find_call_args = mock_db._users_collection.find.call_args[0][0]
        assert find_call_args.get("referee.level") == "S2"

    @pytest.mark.asyncio
    async def test_scope_filter_applied(self, assignment_service, mock_db):
        """scope is passed to user query as referee.club.clubId"""
        test_match = {"_id": "match-1", "startDate": datetime(2026, 3, 5)}
        mock_db._matches_collection.find_one = AsyncMock(return_value=test_match)
        mock_db._assignments_find.to_list = AsyncMock(return_value=[])
        mock_db._users_find.to_list = AsyncMock(return_value=[])

        await assignment_service.get_referee_options_for_match("match-1", scope="club-abc")

        find_call_args = mock_db._users_collection.find.call_args[0][0]
        assert find_call_args.get("referee.club.clubId") == "club-abc"

    @pytest.mark.asyncio
    async def test_scope_and_level_filter_combined(self, assignment_service, mock_db):
        """scope and levelFilter can be combined"""
        test_match = {"_id": "match-1", "startDate": datetime(2026, 3, 5)}
        mock_db._matches_collection.find_one = AsyncMock(return_value=test_match)
        mock_db._assignments_find.to_list = AsyncMock(return_value=[])
        mock_db._users_find.to_list = AsyncMock(return_value=[])

        await assignment_service.get_referee_options_for_match(
            "match-1", scope="club-xyz", level_filter="S1"
        )

        find_call_args = mock_db._users_collection.find.call_args[0][0]
        assert find_call_args.get("referee.club.clubId") == "club-xyz"
        assert find_call_args.get("referee.level") == "S1"

    @pytest.mark.asyncio
    async def test_empty_result_when_no_referees(self, assignment_service, mock_db):
        """Empty lists returned when no active referees exist"""
        test_match = {"_id": "match-1", "startDate": datetime(2026, 3, 5)}
        mock_db._matches_collection.find_one = AsyncMock(return_value=test_match)
        mock_db._assignments_find.to_list = AsyncMock(return_value=[])
        mock_db._users_find.to_list = AsyncMock(return_value=[])

        result = await assignment_service.get_referee_options_for_match("match-1")

        assert result.assigned == []
        assert result.requested == []
        assert result.available == []


class TestGetDaySummaries:

    @pytest.mark.asyncio
    async def test_returns_per_day_totals(self, assignment_service, mock_db):
        """Normal result: per-day summaries covering requested range"""
        mock_db._matches_find.to_list = AsyncMock(
            return_value=[
                {
                    "_id": "m1",
                    "startDate": datetime(2026, 3, 1, 10, 0),
                    "referee1": {"userId": "ref-1"},
                    "referee2": {"userId": "ref-2"},
                },
                {
                    "_id": "m2",
                    "startDate": datetime(2026, 3, 2, 14, 0),
                    "referee1": {"userId": "ref-1"},
                    "referee2": None,
                },
                {
                    "_id": "m3",
                    "startDate": datetime(2026, 3, 3, 14, 0),
                    "referee1": None,
                    "referee2": None,
                },
            ]
        )

        result = await assignment_service.get_day_summaries(year=2026, month=3)

        assert len(result) == 3

        day1 = next(d for d in result if d["date"] == "2026-03-01")
        assert day1["totalMatches"] == 1
        assert day1["fullyAssigned"] == 1
        assert day1["partiallyAssigned"] == 0
        assert day1["unassigned"] == 0

        day2 = next(d for d in result if d["date"] == "2026-03-02")
        assert day2["totalMatches"] == 1
        assert day2["partiallyAssigned"] == 1

        day3 = next(d for d in result if d["date"] == "2026-03-03")
        assert day3["totalMatches"] == 1
        assert day3["unassigned"] == 1

    @pytest.mark.asyncio
    async def test_days_with_no_matches_have_zero_counts(self, assignment_service, mock_db):
        """Days with no matches are not included in results"""
        mock_db._matches_find.to_list = AsyncMock(return_value=[])

        result = await assignment_service.get_day_summaries(year=2026, month=3)

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_single_day_summary(self, assignment_service, mock_db):
        """Single day with match works correctly"""
        mock_db._matches_find.to_list = AsyncMock(
            return_value=[
                {
                    "_id": "m1",
                    "startDate": datetime(2026, 5, 15, 10, 0),
                    "referee1": None,
                    "referee2": None,
                }
            ]
        )

        result = await assignment_service.get_day_summaries(year=2026, month=5)

        assert len(result) == 1
        assert result[0]["date"] == "2026-05-15"
        assert result[0]["totalMatches"] == 1
        assert result[0]["unassigned"] == 1
