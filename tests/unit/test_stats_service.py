"""Unit tests for StatsService"""

from unittest.mock import AsyncMock, MagicMock

import pytest

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
    db.__getitem__ = MagicMock(
        side_effect=lambda name: {
            "matches": mock_matches_collection,
            "players": mock_players_collection,
        }.get(name)
    )

    return db


@pytest.fixture
def stats_service(mock_db):
    """StatsService instance with mocked database"""
    return StatsService(mock_db)


class TestCalculateMatchStats:
    """Test match statistics calculations"""

    def test_regular_time_win(self, stats_service):
        """Test stats for regular time win"""
        result = stats_service.calculate_match_stats(
            match_status="FINISHED",
            finish_type="REGULAR",
            standings_setting={
                "pointsWinReg": 3,
                "pointsLossReg": 0,
                "pointsDrawReg": 1,
                "pointsWinOvertime": 2,
                "pointsLossOvertime": 1,
                "pointsWinShootout": 2,
                "pointsLossShootout": 1,
            },
            home_score=5,
            away_score=3,
        )

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
        result = stats_service.calculate_match_stats(
            match_status="FINISHED",
            finish_type="OVERTIME",
            standings_setting={
                "pointsWinReg": 3,
                "pointsLossReg": 0,
                "pointsDrawReg": 1,
                "pointsWinOvertime": 2,
                "pointsLossOvertime": 1,
                "pointsWinShootout": 2,
                "pointsLossShootout": 1,
            },
            home_score=4,
            away_score=3,
        )

        assert result["home"]["points"] == 2
        assert result["home"]["otWin"] == 1
        assert result["away"]["points"] == 1
        assert result["away"]["otLoss"] == 1

    def test_shootout_win(self, stats_service):
        """Test stats for shootout win"""
        result = stats_service.calculate_match_stats(
            match_status="FINISHED",
            finish_type="SHOOTOUT",
            standings_setting={
                "pointsWinReg": 3,
                "pointsLossReg": 0,
                "pointsDrawReg": 1,
                "pointsWinOvertime": 2,
                "pointsLossOvertime": 1,
                "pointsWinShootout": 2,
                "pointsLossShootout": 1,
            },
            home_score=3,
            away_score=2,
        )

        assert result["home"]["points"] == 2
        assert result["home"]["soWin"] == 1
        assert result["away"]["points"] == 1
        assert result["away"]["soLoss"] == 1

    def test_tie_game(self, stats_service):
        """Test stats for tie game"""
        result = stats_service.calculate_match_stats(
            match_status="FINISHED",
            finish_type="REGULAR",
            standings_setting={
                "pointsWinReg": 3,
                "pointsLossReg": 0,
                "pointsDrawReg": 1,
                "pointsWinOvertime": 2,
                "pointsLossOvertime": 1,
                "pointsWinShootout": 2,
                "pointsLossShootout": 1,
            },
            home_score=3,
            away_score=3,
        )

        assert result["home"]["points"] == 1
        assert result["home"]["draw"] == 1
        assert result["away"]["points"] == 1
        assert result["away"]["draw"] == 1

    def test_incomplete_match_returns_zeros(self, stats_service):
        """Test that incomplete match returns zero stats"""
        result = stats_service.calculate_match_stats(
            match_status="SCHEDULED",
            finish_type=None,
            standings_setting={
                "pointsWinReg": 3,
                "pointsLossReg": 0,
                "pointsDrawReg": 1,
                "pointsWinOvertime": 2,
                "pointsLossOvertime": 1,
                "pointsWinShootout": 2,
                "pointsLossShootout": 1,
            },
            home_score=0,
            away_score=0,
        )

        assert result["home"]["points"] == 0
        assert result["home"]["draw"] == 0
        assert result["away"]["points"] == 0
        assert result["away"]["draw"] == 0

    def test_match_in_progress_returns_zeros(self, stats_service):
        """Test that match in progress returns zero stats"""
        result = stats_service.calculate_match_stats(
            match_status="INPROGRESS",
            finish_type=None,
            standings_setting={
                "pointsWinReg": 3,
                "pointsLossReg": 0,
                "pointsDrawReg": 1,
                "pointsWinOvertime": 2,
                "pointsLossOvertime": 1,
                "pointsWinShootout": 2,
                "pointsLossShootout": 1,
            },
            home_score=1,
            away_score=0,
        )
        assert result["home"]["points"] == 0
        assert result["home"]["win"] == 0
        assert result["away"]["points"] == 0
        assert result["away"]["loss"] == 0


class TestCalculateRosterStats:
    """Test roster statistics calculations"""

    @pytest.mark.asyncio
    async def test_calculate_goals_and_assists(self, stats_service, mock_db):
        """Test calculation of goals and assists from scores"""
        match_id = "test-match-id"

        # Create test match data in mock DB
        test_match = {
            "_id": match_id,
            "home": {
                "roster": {
                    "players": [
                        {
                            "_id": "r1",
                            "player": {"playerId": "player-1"},
                            "goals": 0,
                            "assists": 0,
                            "points": 0,
                            "penaltyMinutes": 0,
                        },
                        {
                            "_id": "r2",
                            "player": {"playerId": "player-2"},
                            "goals": 0,
                            "assists": 0,
                            "points": 0,
                            "penaltyMinutes": 0,
                        },
                    ]
                },
                "scores": [
                    {
                        "goalPlayer": {"playerId": "player-1"},
                        "assistPlayer": {"playerId": "player-2"},
                    },
                    {"goalPlayer": {"playerId": "player-1"}, "assistPlayer": None},
                ],
                "penalties": [],
            },
        }

        # Mock the find_one to return test match
        mock_db._matches_collection.find_one = AsyncMock(return_value=test_match)

        # Now always uses direct DB access
        await stats_service.calculate_roster_stats(match_id, "home")

        # Verify update was called with correct stats
        update_call = mock_db._matches_collection.update_one.call_args
        update_document = update_call[0][1]  # Second positional argument
        updated_players = update_document["$set"]["home.roster.players"]

        roster_by_id = {r["player"]["playerId"]: r for r in updated_players}
        assert roster_by_id["player-1"]["goals"] == 2
        assert roster_by_id["player-1"]["assists"] == 0
        assert roster_by_id["player-1"]["points"] == 2
        assert roster_by_id["player-2"]["goals"] == 0
        assert roster_by_id["player-2"]["assists"] == 1
        assert roster_by_id["player-2"]["points"] == 1

    @pytest.mark.asyncio
    async def test_calculate_penalties(self, stats_service, mock_db):
        """Test calculation of penalty minutes"""
        match_id = "test-match-id"

        # Create test match data in mock DB
        test_match = {
            "_id": match_id,
            "home": {
                "roster": {
                    "players": [
                        {
                            "_id": "r1",
                            "player": {"playerId": "player-1"},
                            "goals": 0,
                            "assists": 0,
                            "points": 0,
                            "penaltyMinutes": 0,
                        },
                        {
                            "_id": "r2",
                            "player": {"playerId": "player-2"},
                            "goals": 0,
                            "assists": 0,
                            "points": 0,
                            "penaltyMinutes": 0,
                        },
                    ]
                },
                "scores": [],
                "penalties": [
                    {"penaltyPlayer": {"playerId": "player-1"}, "penaltyMinutes": 2},
                    {"penaltyPlayer": {"playerId": "player-1"}, "penaltyMinutes": 2},
                    {"penaltyPlayer": {"playerId": "player-2"}, "penaltyMinutes": 5},
                ],
            },
        }

        # Mock the find_one to return test match
        mock_db._matches_collection.find_one = AsyncMock(return_value=test_match)

        # Now always uses direct DB access
        await stats_service.calculate_roster_stats(match_id, "home")

        # Verify update was called with correct stats
        update_call = mock_db._matches_collection.update_one.call_args
        update_document = update_call[0][1]  # Second positional argument
        updated_players = update_document["$set"]["home.roster.players"]

        roster_by_id = {r["player"]["playerId"]: r for r in updated_players}
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
                        "soLoss": 0,
                    },
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
                        "soLoss": 0,
                    },
                },
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

    async def test_standings_tie_breaker_goal_diff(self, stats_service):
        """Test tie breaker by goal difference"""
        # Create mock matches where both teams have same points but different goal diff
        matches = [
            {
                "home": {
                    "fullName": "Team A",
                    "shortName": "TMA",
                    "tinyName": "A",
                    "logo": "http://example.com/a.png",
                    "stats": {
                        "gamePlayed": 1,
                        "goalsFor": 5,
                        "goalsAgainst": 0,
                        "points": 3,
                        "win": 1,
                        "loss": 0,
                        "draw": 0,
                        "otWin": 0,
                        "otLoss": 0,
                        "soWin": 0,
                        "soLoss": 0,
                    },
                },
                "away": {
                    "fullName": "Team B",
                    "shortName": "TMB",
                    "tinyName": "B",
                    "logo": "http://example.com/b.png",
                    "stats": {
                        "gamePlayed": 1,
                        "goalsFor": 0,
                        "goalsAgainst": 5,
                        "points": 0,
                        "win": 0,
                        "loss": 1,
                        "draw": 0,
                        "otWin": 0,
                        "otLoss": 0,
                        "soWin": 0,
                        "soLoss": 0,
                    },
                },
            },
            {
                "home": {
                    "fullName": "Team B",
                    "shortName": "TMB",
                    "tinyName": "B",
                    "logo": "http://example.com/b.png",
                    "stats": {
                        "gamePlayed": 1,
                        "goalsFor": 3,
                        "goalsAgainst": 0,
                        "points": 3,
                        "win": 1,
                        "loss": 0,
                        "draw": 0,
                        "otWin": 0,
                        "otLoss": 0,
                        "soWin": 0,
                        "soLoss": 0,
                    },
                },
                "away": {
                    "fullName": "Team A",
                    "shortName": "TMA",
                    "tinyName": "A",
                    "logo": "http://example.com/a.png",
                    "stats": {
                        "gamePlayed": 1,
                        "goalsFor": 0,
                        "goalsAgainst": 3,
                        "points": 0,
                        "win": 0,
                        "loss": 1,
                        "draw": 0,
                        "otWin": 0,
                        "otLoss": 0,
                        "soWin": 0,
                        "soLoss": 0,
                    },
                },
            },
        ]

        # Call the private method directly for unit testing
        standings = stats_service._calculate_standings(matches)

        # Both teams have 3 points (1 win, 1 loss each)
        # Team A: 5-3 = +2 goal diff
        # Team B: 3-5 = -2 goal diff
        # Team A should be first due to better goal difference
        teams_list = list(standings.keys())
        assert teams_list[0] == "Team A"
        assert standings["Team A"]["points"] == 3
        assert standings["Team A"]["goalsFor"] - standings["Team A"]["goalsAgainst"] == 2

        assert teams_list[1] == "Team B"
        assert standings["Team B"]["points"] == 3
        assert standings["Team B"]["goalsFor"] - standings["Team B"]["goalsAgainst"] == -2


class TestTeamStandingsHelpers:
    """Test helper methods for standings management"""

    def test_init_team_standings(self, stats_service):
        """Test team standings initialization"""
        team_data = {
            "fullName": "Test Team",
            "shortName": "TT",
            "tinyName": "T",
            "logo": "http://example.com/logo.png",
        }

        standings = stats_service._init_team_standings(team_data)

        assert standings["fullName"] == "Test Team"
        assert standings["shortName"] == "TT"
        assert standings["tinyName"] == "T"
        assert standings["logo"] == "http://example.com/logo.png"
        assert standings["gamesPlayed"] == 0
        assert standings["goalsFor"] == 0
        assert standings["goalsAgainst"] == 0
        assert standings["points"] == 0
        assert standings["wins"] == 0
        assert standings["losses"] == 0
        assert standings["draws"] == 0
        assert standings["otWins"] == 0
        assert standings["otLosses"] == 0
        assert standings["soWins"] == 0
        assert standings["soLosses"] == 0
        assert standings["streak"] == []

    def test_update_streak_win(self, stats_service):
        """Test streak update for win"""
        team_standings = {"streak": []}
        match_stats = {"win": 1}

        stats_service._update_streak(team_standings, match_stats)

        assert team_standings["streak"] == ["W"]

    def test_update_streak_loss(self, stats_service):
        """Test streak update for loss"""
        team_standings = {"streak": []}
        match_stats = {"loss": 1}

        stats_service._update_streak(team_standings, match_stats)

        assert team_standings["streak"] == ["L"]

    def test_update_streak_draw(self, stats_service):
        """Test streak update for draw"""
        team_standings = {"streak": []}
        match_stats = {"draw": 1}

        stats_service._update_streak(team_standings, match_stats)

        assert team_standings["streak"] == ["D"]

    def test_update_streak_overtime_win(self, stats_service):
        """Test streak update for overtime win"""
        team_standings = {"streak": []}
        match_stats = {"otWin": 1}

        stats_service._update_streak(team_standings, match_stats)

        assert team_standings["streak"] == ["OTW"]

    def test_update_streak_shootout_loss(self, stats_service):
        """Test streak update for shootout loss"""
        team_standings = {"streak": []}
        match_stats = {"soLoss": 1}

        stats_service._update_streak(team_standings, match_stats)

        assert team_standings["streak"] == ["SOL"]

    def test_update_streak_max_length(self, stats_service):
        """Test that streak maintains max length of 5"""
        team_standings = {"streak": ["W", "W", "L", "W", "W"]}
        match_stats = {"win": 1}

        stats_service._update_streak(team_standings, match_stats)

        assert len(team_standings["streak"]) == 5
        assert team_standings["streak"] == ["W", "L", "W", "W", "W"]

    def test_update_streak_no_result(self, stats_service):
        """Test streak with no valid result"""
        team_standings = {"streak": ["W"]}
        match_stats = {}

        stats_service._update_streak(team_standings, match_stats)

        # Streak should not change when no valid result
        assert team_standings["streak"] == ["W"]


class TestRosterStatsHelpers:
    """Test helper methods for roster stats"""

    def test_initialize_roster_player_stats(self, stats_service):
        """Test initialization of player stats from roster"""
        roster = [
            {"player": {"playerId": "player-1"}, "goals": 0, "assists": 0},
            {"player": {"playerId": "player-2"}, "goals": 0, "assists": 0},
        ]

        player_stats = stats_service._initialize_roster_player_stats(roster)

        assert "player-1" in player_stats
        assert "player-2" in player_stats
        assert player_stats["player-1"] == {
            "goals": 0,
            "assists": 0,
            "points": 0,
            "penaltyMinutes": 0,
        }

    def test_initialize_roster_player_stats_empty_roster(self, stats_service):
        """Test initialization with empty roster"""
        roster = []

        player_stats = stats_service._initialize_roster_player_stats(roster)

        assert player_stats == {}

    def test_calculate_scoring_stats_creates_missing_player(self, stats_service):
        """Test that scoring stats creates entry for player not in initial roster"""
        scoreboard = [
            {"goalPlayer": {"playerId": "player-3"}, "assistPlayer": {"playerId": "player-4"}}
        ]
        player_stats = {}

        stats_service._calculate_scoring_stats(scoreboard, player_stats)

        assert "player-3" in player_stats
        assert "player-4" in player_stats
        assert player_stats["player-3"]["goals"] == 1
        assert player_stats["player-4"]["assists"] == 1

    def test_calculate_scoring_stats_no_assist(self, stats_service):
        """Test scoring stats when there's no assist player"""
        scoreboard = [{"goalPlayer": {"playerId": "player-1"}, "assistPlayer": None}]
        player_stats = {}

        stats_service._calculate_scoring_stats(scoreboard, player_stats)

        assert player_stats["player-1"]["goals"] == 1
        assert player_stats["player-1"]["assists"] == 0

    def test_apply_stats_to_roster(self, stats_service):
        """Test applying calculated stats to roster"""
        roster = [
            {
                "player": {"playerId": "player-1"},
                "goals": 0,
                "assists": 0,
                "points": 0,
                "penaltyMinutes": 0,
            }
        ]
        player_stats = {"player-1": {"goals": 2, "assists": 1, "points": 3, "penaltyMinutes": 4}}

        updated_roster = stats_service._apply_stats_to_roster(roster, player_stats)

        assert updated_roster[0]["goals"] == 2
        assert updated_roster[0]["assists"] == 1
        assert updated_roster[0]["points"] == 3
        assert updated_roster[0]["penaltyMinutes"] == 4


class TestEdgeCases:
    """Test edge cases and error conditions"""

    def test_calculate_match_stats_with_unknown_finish_type(self, stats_service):
        """Test match stats with unknown finish type"""
        result = stats_service.calculate_match_stats(
            match_status="FINISHED",
            finish_type="UNKNOWN_TYPE",
            standings_setting={
                "pointsWinReg": 3,
                "pointsLossReg": 0,
                "pointsDrawReg": 1,
                "pointsWinOvertime": 2,
                "pointsLossOvertime": 1,
                "pointsWinShootout": 2,
                "pointsLossShootout": 1,
            },
            home_score=3,
            away_score=2,
        )

        # Should reset to zeros for unknown finish type
        assert result["home"]["points"] == 0
        assert result["away"]["points"] == 0

    def test_calculate_standings_empty_matches(self, stats_service):
        """Test standings calculation with no matches"""
        matches = []

        standings = stats_service._calculate_standings(matches)

        assert standings == {}

    def test_calculate_standings_multiple_teams(self, stats_service):
        """Test standings with multiple teams"""
        matches = [
            {
                "home": {
                    "fullName": "Team A",
                    "shortName": "TMA",
                    "tinyName": "A",
                    "logo": "http://example.com/a.png",
                    "stats": {
                        "gamePlayed": 1,
                        "goalsFor": 5,
                        "goalsAgainst": 0,
                        "points": 3,
                        "win": 1,
                        "loss": 0,
                        "draw": 0,
                        "otWin": 0,
                        "otLoss": 0,
                        "soWin": 0,
                        "soLoss": 0,
                    },
                },
                "away": {
                    "fullName": "Team B",
                    "shortName": "TMB",
                    "tinyName": "B",
                    "logo": "http://example.com/b.png",
                    "stats": {
                        "gamePlayed": 1,
                        "goalsFor": 0,
                        "goalsAgainst": 5,
                        "points": 0,
                        "win": 0,
                        "loss": 1,
                        "draw": 0,
                        "otWin": 0,
                        "otLoss": 0,
                        "soWin": 0,
                        "soLoss": 0,
                    },
                },
            },
            {
                "home": {
                    "fullName": "Team C",
                    "shortName": "TMC",
                    "tinyName": "C",
                    "logo": "http://example.com/c.png",
                    "stats": {
                        "gamePlayed": 1,
                        "goalsFor": 3,
                        "goalsAgainst": 2,
                        "points": 2,
                        "win": 0,
                        "loss": 0,
                        "draw": 0,
                        "otWin": 1,
                        "otLoss": 0,
                        "soWin": 0,
                        "soLoss": 0,
                    },
                },
                "away": {
                    "fullName": "Team D",
                    "shortName": "TMD",
                    "tinyName": "D",
                    "logo": "http://example.com/d.png",
                    "stats": {
                        "gamePlayed": 1,
                        "goalsFor": 2,
                        "goalsAgainst": 3,
                        "points": 1,
                        "win": 0,
                        "loss": 0,
                        "draw": 0,
                        "otWin": 0,
                        "otLoss": 1,
                        "soWin": 0,
                        "soLoss": 0,
                    },
                },
            },
        ]

        standings = stats_service._calculate_standings(matches)

        teams_list = list(standings.keys())
        # Team A should be first (3 points, +5 goal diff)
        assert teams_list[0] == "Team A"
        # Team C should be second (2 points, +1 goal diff)
        assert teams_list[1] == "Team C"
        # Team D should be third (1 point, -1 goal diff)
        assert teams_list[2] == "Team D"
        # Team B should be last (0 points, -5 goal diff)
        assert teams_list[3] == "Team B"
