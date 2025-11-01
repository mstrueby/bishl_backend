"""Unit tests for StatsService"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from services.stats_service import StatsService


@pytest.fixture
def mock_db():
    """Mock MongoDB database"""
    db = MagicMock()

    # Create mock collections with proper async methods
    mock_matches_collection = MagicMock()
    mock_matches_collection.update_one = AsyncMock(return_value=MagicMock(acknowledged=True))
    mock_matches_collection.find_one = AsyncMock()
    mock_matches_collection.find = MagicMock()

    mock_players_collection = MagicMock()
    mock_players_collection.find_one = AsyncMock()
    mock_players_collection.update_one = AsyncMock(return_value=MagicMock(acknowledged=True))

    # Store collections as attributes for easier access in tests
    db._matches_collection = mock_matches_collection
    db._players_collection = mock_players_collection

    # Attach collections to db
    db.__getitem__ = MagicMock(side_effect=lambda name: {
        'matches': mock_matches_collection,
        'players': mock_players_collection
    }.get(name))

    return db


@pytest.fixture
def stats_service(mock_db):
    """StatsService instance with mocked database"""
    return StatsService(mock_db)


class TestCalculateMatchStats:
    """Test match statistics calculations"""

    def test_regular_time_win(self, stats_service):
        """Test stats for regular time win"""
        result = stats_service.calculate_match_stats(match_status="FINISHED",
                                                     finish_type="REGULAR",
                                                     standings_setting={
                                                         "pointsWinReg": 3,
                                                         "pointsLossReg": 0,
                                                         "pointsDrawReg": 1,
                                                         "pointsWinOvertime":
                                                         2,
                                                         "pointsLossOvertime":
                                                         1,
                                                         "pointsWinShootout":
                                                         2,
                                                         "pointsLossShootout":
                                                         1
                                                     },
                                                     home_score=5,
                                                     away_score=3)

        assert result["home"]["points"] == 3
        assert result["home"]["win"] == 1
        assert result["home"]["loss"] == 0
        assert result["home"]["goalsFor"] == 5
        assert result["home"]["goalsAgainst"] == 3

        assert result["away"]["points"] == 0
        assert result["away"]["win"] == 0
        assert result["away"]["loss"] == 1
        assert result["away"]["goalsFor"] == 3
        assert result["away"]["goalsAgainst"] == 5

    def test_overtime_win(self, stats_service):
        """Test stats for overtime win"""
        result = stats_service.calculate_match_stats(match_status="FINISHED",
                                                     finish_type="OVERTIME",
                                                     standings_setting={
                                                         "pointsWinReg": 3,
                                                         "pointsLossReg": 0,
                                                         "pointsDrawReg": 1,
                                                         "pointsWinOvertime":
                                                         2,
                                                         "pointsLossOvertime":
                                                         1,
                                                         "pointsWinShootout":
                                                         2,
                                                         "pointsLossShootout":
                                                         1
                                                     },
                                                     home_score=4,
                                                     away_score=3)

        assert result["home"]["points"] == 2
        assert result["home"]["otWin"] == 1
        assert result["away"]["points"] == 1
        assert result["away"]["otLoss"] == 1

    def test_shootout_win(self, stats_service):
        """Test stats for shootout win"""
        result = stats_service.calculate_match_stats(match_status="FINISHED",
                                                     finish_type="SHOOTOUT",
                                                     standings_setting={
                                                         "pointsWinReg": 3,
                                                         "pointsLossReg": 0,
                                                         "pointsDrawReg": 1,
                                                         "pointsWinOvertime":
                                                         2,
                                                         "pointsLossOvertime":
                                                         1,
                                                         "pointsWinShootout":
                                                         2,
                                                         "pointsLossShootout":
                                                         1
                                                     },
                                                     home_score=3,
                                                     away_score=2)

        assert result["home"]["points"] == 2
        assert result["home"]["soWin"] == 1
        assert result["away"]["points"] == 1
        assert result["away"]["soLoss"] == 1

    def test_tie_game(self, stats_service):
        """Test stats for tie game"""
        result = stats_service.calculate_match_stats(match_status="FINISHED",
                                                     finish_type="REGULAR",
                                                     standings_setting={
                                                         "pointsWinReg": 3,
                                                         "pointsLossReg": 0,
                                                         "pointsDrawReg": 1,
                                                         "pointsWinOvertime":
                                                         2,
                                                         "pointsLossOvertime":
                                                         1,
                                                         "pointsWinShootout":
                                                         2,
                                                         "pointsLossShootout":
                                                         1
                                                     },
                                                     home_score=3,
                                                     away_score=3)

        assert result["home"]["points"] == 1
        assert result["home"]["draw"] == 1
        assert result["away"]["points"] == 1
        assert result["away"]["draw"] == 1

    def test_incomplete_match_returns_zeros(self, stats_service):
        """Test that incomplete match returns zero stats"""
        result = stats_service.calculate_match_stats(match_status="SCHEDULED",
                                                     finish_type=None,
                                                     standings_setting={
                                                         "pointsWinReg": 3,
                                                         "pointsLossReg": 0,
                                                         "pointsDrawReg": 1,
                                                         "pointsWinOvertime":
                                                         2,
                                                         "pointsLossOvertime":
                                                         1,
                                                         "pointsWinShootout":
                                                         2,
                                                         "pointsLossShootout":
                                                         1
                                                     },
                                                     home_score=0,
                                                     away_score=0)

        assert result["home"]["points"] == 0
        assert result["home"]["draw"] == 0
        assert result["away"]["points"] == 0
        assert result["away"]["draw"] == 0


    def test_match_in_progress_returns_zeros(self, stats_service):
        """Test that match in progress returns zero stats"""
        result = stats_service.calculate_match_stats(match_status="INPROGRESS",
                                                     finish_type=None,
                                                     standings_setting={
                                                         "pointsWinReg": 3,
                                                         "pointsLossReg": 0,
                                                         "pointsDrawReg": 1,
                                                         "pointsWinOvertime":
                                                         2,
                                                         "pointsLossOvertime":
                                                         1,
                                                         "pointsWinShootout":
                                                         2,
                                                         "pointsLossShootout":
                                                         1
                                                     },
                                                     home_score=1,
                                                     away_score=0)
        assert result["home"]["points"] == 0
        assert result["home"]["win"] == 0
        assert result["away"]["points"] == 0
        assert result["away"]["loss"] == 0


class TestCalculateRosterStats:
    """Test roster statistics calculations"""

    @pytest.mark.asyncio
    async def test_calculate_goals_and_assists(self, stats_service, mock_db):
        """Test calculation of goals and assists from scores"""
        from unittest.mock import patch

        match_id = "test-match-id"

        # Mock roster data
        mock_roster = [{
            "_id": "r1",
            "player": {
                "playerId": "player-1"
            },
            "goals": 0,
            "assists": 0,
            "points": 0,
            "penaltyMinutes": 0
        }, {
            "_id": "r2",
            "player": {
                "playerId": "player-2"
            },
            "goals": 0,
            "assists": 0,
            "points": 0,
            "penaltyMinutes": 0
        }]

        # Mock scoreboard data
        mock_scores = [{
            "goalPlayer": {
                "playerId": "player-1"
            },
            "assistPlayer": {
                "playerId": "player-2"
            }
        }, {
            "goalPlayer": {
                "playerId": "player-1"
            },
            "assistPlayer": None
        }]

        # Mock penalties data
        mock_penalties = []

        # Mock the HTTP API calls
        with patch('services.stats_service.httpx.AsyncClient') as mock_client:
            mock_context = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_context

            # Create mock responses
            async def mock_get(url):
                mock_response = MagicMock()
                if 'roster' in url:
                    mock_response.status_code = 200
                    mock_response.json = MagicMock(return_value=mock_roster)
                elif 'scores' in url:
                    mock_response.status_code = 200
                    mock_response.json = MagicMock(return_value=mock_scores)
                elif 'penalties' in url:
                    mock_response.status_code = 200
                    mock_response.json = MagicMock(return_value=mock_penalties)
                return mock_response

            mock_context.get = mock_get

            await stats_service.calculate_roster_stats(match_id, "home", use_db_direct=False)

            # Verify update was called with correct stats
            # Access the mock collection directly from the fixture
            # update_one is called as: update_one(filter, update_doc)
            # call_args gives us (args, kwargs), so args[1] is the update document
            update_call = mock_db._matches_collection.update_one.call_args
            update_document = update_call[0][1]  # Second positional argument
            updated_roster = update_document["$set"]["home.roster"]

            roster_by_id = {r["player"]["playerId"]: r for r in updated_roster}
            assert roster_by_id["player-1"]["goals"] == 2
            assert roster_by_id["player-1"]["assists"] == 0
            assert roster_by_id["player-1"]["points"] == 2
            assert roster_by_id["player-2"]["goals"] == 0
            assert roster_by_id["player-2"]["assists"] == 1
            assert roster_by_id["player-2"]["points"] == 1

    @pytest.mark.asyncio
    async def test_calculate_penalties(self, stats_service, mock_db):
        """Test calculation of penalty minutes"""
        from unittest.mock import patch

        match_id = "test-match-id"

        # Mock roster data
        mock_roster = [{
            "_id": "r1",
            "player": {
                "playerId": "player-1"
            },
            "goals": 0,
            "assists": 0,
            "points": 0,
            "penaltyMinutes": 0
        }, {
            "_id": "r2",
            "player": {
                "playerId": "player-2"
            },
            "goals": 0,
            "assists": 0,
            "points": 0,
            "penaltyMinutes": 0
        }]

        # Mock penalties data
        mock_penalties = [{
            "penaltyPlayer": {
                "playerId": "player-1"
            },
            "penaltyMinutes": 2
        }, {
            "penaltyPlayer": {
                "playerId": "player-1"
            },
            "penaltyMinutes": 2
        }, {
            "penaltyPlayer": {
                "playerId": "player-2"
            },
            "penaltyMinutes": 5
        }]

        # Mock the HTTP API calls
        with patch('services.stats_service.httpx.AsyncClient') as mock_client:
            mock_context = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_context

            # Create mock responses
            async def mock_get(url):
                mock_response = MagicMock()
                if 'roster' in url:
                    mock_response.status_code = 200
                    mock_response.json = MagicMock(return_value=mock_roster)
                elif 'scores' in url:
                    mock_response.status_code = 200
                    mock_response.json = MagicMock(return_value=[])
                elif 'penalties' in url:
                    mock_response.status_code = 200
                    mock_response.json = MagicMock(return_value=mock_penalties)
                return mock_response

            mock_context.get = mock_get

            await stats_service.calculate_roster_stats(match_id, "home", use_db_direct=False)

            # Access the mock collection directly from the fixture
            # update_one is called as: update_one(filter, update_doc)
            # call_args gives us (args, kwargs), so args[1] is the update document
            update_call = mock_db._matches_collection.update_one.call_args
            update_document = update_call[0][1]  # Second positional argument
            updated_roster = update_document["$set"]["home.roster"]

            roster_by_id = {r["player"]["playerId"]: r for r in updated_roster}
            assert roster_by_id["player-1"]["penaltyMinutes"] == 4
            assert roster_by_id["player-2"]["penaltyMinutes"] == 5


@pytest.mark.asyncio
class TestCalculateStandings:
    """Test standings calculations"""

    async def test_standings_sorting_by_points(self, stats_service, mock_db):
        """Test standings are sorted by points"""
        # Create mock matches with team stats
        matches = [
            {
                "home": {
                    "fullName": "Team A",
                    "shortName": "TMA",
                    "tinyName": "A",
                    "logo": "http://example.com/a.png",
                    "stats": {
                        "gamePlayed": 1,
                        "goalsFor": 3,
                        "goalsAgainst": 1,
                        "points": 3,
                        "win": 1,
                        "loss": 0,
                        "draw": 0,
                        "otWin": 0,
                        "otLoss": 0,
                        "soWin": 0,
                        "soLoss": 0
                    }
                },
                "away": {
                    "fullName": "Team B",
                    "shortName": "TMB",
                    "tinyName": "B",
                    "logo": "http://example.com/b.png",
                    "stats": {
                        "gamePlayed": 1,
                        "goalsFor": 1,
                        "goalsAgainst": 3,
                        "points": 0,
                        "win": 0,
                        "loss": 1,
                        "draw": 0,
                        "otWin": 0,
                        "otLoss": 0,
                        "soWin": 0,
                        "soLoss": 0
                    }
                }
            }
        ]

        # Call the private method directly for unit testing
        standings = stats_service._calculate_standings(matches)

        # Verify standings structure and sorting
        assert len(standings) == 2
        teams_list = list(standings.keys())

        # Team A should be first (3 points from win)
        assert teams_list[0] == "Team A"
        assert standings["Team A"]["points"] == 3
        assert standings["Team A"]["wins"] == 1

        # Team B should be second (0 points from loss)
        assert teams_list[1] == "Team B"
        assert standings["Team B"]["points"] == 0
        assert standings["Team B"]["losses"] == 1


    async def test_standings_tie_breaker_goal_diff(self, stats_service,
                                                   mock_db):
        """Test tie breaker by goal difference"""
        teams = [{
            "_id": "team-1",
            "stats": {
                "points": 10,
                "goalsFor": 20,
                "goalsAgainst": 15
            }
        }, {
            "_id": "team-2",
            "stats": {
                "points": 10,
                "goalsFor": 18,
                "goalsAgainst": 10
            }
        }]

        mock_db.teams.find.return_value.to_list = AsyncMock(return_value=teams)

        standings = await stats_service.calculate_standings(
            "tournament", "season", "round")

        # team-2 has better goal diff (+8 vs +5)
        assert standings[0]["_id"] == "team-2"
        assert standings[1]["_id"] == "team-1"


class TestValidateRosterPlayer:
    """Test roster player validation"""

    def test_player_in_roster_returns_true(self, stats_service):
        """Test validation passes when player in roster"""
        roster = [{
            "player": {
                "playerId": "player-1"
            }
        }, {
            "player": {
                "playerId": "player-2"
            }
        }]

        assert stats_service.validate_roster_player("player-1", roster) is True

    def test_player_not_in_roster_returns_false(self, stats_service):
        """Test validation fails when player not in roster"""
        roster = [{
            "player": {
                "playerId": "player-1"
            }
        }, {
            "player": {
                "playerId": "player-2"
            }
        }]

        assert stats_service.validate_roster_player("player-3",
                                                    roster) is False

    def test_empty_roster_returns_false(self, stats_service):
        """Test validation fails for empty roster"""
        assert stats_service.validate_roster_player("player-1", []) is False