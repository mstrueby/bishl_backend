"""Integration tests for StatsService with real database"""

import pytest
from bson import ObjectId
from httpx import AsyncClient

from services.stats_service import StatsService


@pytest.mark.asyncio
class TestStatsServiceIntegration:
    """Integration tests for StatsService with real MongoDB"""

    async def test_get_standings_settings_from_database(self, mongodb):
        """Test fetching standings settings directly from database"""
        from tests.fixtures.data_fixtures import create_test_tournament

        # Setup - Create tournament with standings settings
        tournament = create_test_tournament()
        tournament["seasons"][0]["standingsSettings"] = {
            "pointsWinReg": 3,
            "pointsLossReg": 0,
            "pointsDrawReg": 1,
            "pointsWinOvertime": 2,
            "pointsLossOvertime": 1,
            "pointsWinShootout": 2,
            "pointsLossShootout": 1,
        }
        await mongodb["tournaments"].insert_one(tournament)

        # Execute
        stats_service = StatsService(mongodb)
        settings = await stats_service.get_standings_settings(
            tournament["alias"], tournament["seasons"][0]["alias"]
        )

        # Assert
        assert settings is not None
        assert settings["pointsWinReg"] == 3
        assert settings["pointsWinOvertime"] == 2

    async def test_calculate_roster_stats_with_database(self, mongodb):
        """Test roster stats calculation with real database operations"""
        from tests.fixtures.data_fixtures import create_test_match, create_test_roster_player

        # Setup - Create match with roster and scores
        match = create_test_match(status="FINISHED")
        player1 = create_test_roster_player("player-1")
        player2 = create_test_roster_player("player-2")
        match["home"]["roster"] = {"players": [player1, player2], "status": "SUBMITTED"}
        match["home"]["scores"] = [
            {
                "_id": str(ObjectId()),
                "matchTime": "10:30",
                "matchSeconds": 630,
                "goalPlayer": {"playerId": "player-1", "firstName": "Test", "lastName": "Player"},
                "assistPlayer": {
                    "playerId": "player-2",
                    "firstName": "Assist",
                    "lastName": "Player",
                },
                "isPPG": False,
                "isSHG": False,
                "isGWG": False,
            },
            {
                "_id": str(ObjectId()),
                "matchTime": "15:20",
                "matchSeconds": 920,
                "goalPlayer": {"playerId": "player-1", "firstName": "Test", "lastName": "Player"},
                "assistPlayer": None,
                "isPPG": False,
                "isSHG": False,
                "isGWG": False,
            },
        ]
        match["home"]["penalties"] = [
            {
                "_id": str(ObjectId()),
                "matchTime": "05:00",
                "matchSeconds": 300,
                "penaltyPlayer": {
                    "playerId": "player-1",
                    "firstName": "Test",
                    "lastName": "Player",
                },
                "penaltyMinutes": 2,
                "penaltyReason": "Hooking",
            }
        ]
        await mongodb["matches"].insert_one(match)

        # Execute
        stats_service = StatsService(mongodb)
        await stats_service.calculate_roster_stats(match["_id"], "home")

        # Assert - Verify database was updated
        updated_match = await mongodb["matches"].find_one({"_id": match["_id"]})
        roster_players = updated_match["home"]["roster"]["players"]

        # Player 1: 2 goals, 0 assists, 2 points, 2 PIM
        player1_stats = next(p for p in roster_players if p["player"]["playerId"] == "player-1")
        assert player1_stats["goals"] == 2
        assert player1_stats["assists"] == 0
        assert player1_stats["points"] == 2
        assert player1_stats["penaltyMinutes"] == 2

        # Player 2: 0 goals, 1 assist, 1 point, 0 PIM
        player2_stats = next(p for p in roster_players if p["player"]["playerId"] == "player-2")
        assert player2_stats["goals"] == 0
        assert player2_stats["assists"] == 1
        assert player2_stats["points"] == 1
        assert player2_stats["penaltyMinutes"] == 0

    async def test_aggregate_round_standings_with_database(self, mongodb):
        """Test round standings aggregation with real database"""
        from tests.fixtures.data_fixtures import create_test_match, create_test_tournament

        # Setup - Create tournament with round
        tournament = create_test_tournament()
        tournament["seasons"][0]["rounds"][0]["createStandings"] = True
        tournament["seasons"][0]["standingsSettings"] = {
            "pointsWinReg": 3,
            "pointsLossReg": 0,
            "pointsDrawReg": 1,
            "pointsWinOvertime": 2,
            "pointsLossOvertime": 1,
            "pointsWinShootout": 2,
            "pointsLossShootout": 1,
        }
        await mongodb["tournaments"].insert_one(tournament)

        # Create finished matches
        match1 = create_test_match(status="FINISHED")
        match1["tournament"] = {"alias": tournament["alias"], "name": tournament["name"]}
        match1["season"] = {
            "alias": tournament["seasons"][0]["alias"],
            "name": tournament["seasons"][0]["name"],
        }
        match1["round"] = {
            "alias": tournament["seasons"][0]["rounds"][0]["alias"],
            "name": tournament["seasons"][0]["rounds"][0]["name"],
        }
        match1["finishType"] = {"key": "REGULAR", "value": "Regulär"}
        match1["home"]["stats"] = {
            "gamePlayed": 1,
            "goalsFor": 5,
            "goalsAgainst": 2,
            "points": 3,
            "win": 1,
            "loss": 0,
            "draw": 0,
            "otWin": 0,
            "otLoss": 0,
            "soWin": 0,
            "soLoss": 0,
        }
        match1["away"]["stats"] = {
            "gamePlayed": 1,
            "goalsFor": 2,
            "goalsAgainst": 5,
            "points": 0,
            "win": 0,
            "loss": 1,
            "draw": 0,
            "otWin": 0,
            "otLoss": 0,
            "soWin": 0,
            "soLoss": 0,
        }
        await mongodb["matches"].insert_one(match1)

        # Execute
        stats_service = StatsService(mongodb)
        await stats_service.aggregate_round_standings(
            tournament["alias"],
            tournament["seasons"][0]["alias"],
            tournament["seasons"][0]["rounds"][0]["alias"],
        )

        # Assert - Verify standings in tournament document
        updated_tournament = await mongodb["tournaments"].find_one({"_id": tournament["_id"]})
        standings = updated_tournament["seasons"][0]["rounds"][0]["standings"]

        assert len(standings) == 2
        teams = list(standings.keys())
        # Winner should be first
        assert standings[teams[0]]["points"] == 3
        assert standings[teams[0]]["wins"] == 1
        assert standings[teams[1]]["points"] == 0
        assert standings[teams[1]]["losses"] == 1

    async def test_aggregate_matchday_standings_with_database(self, mongodb):
        """Test matchday standings aggregation with real database"""
        from tests.fixtures.data_fixtures import create_test_match, create_test_tournament

        # Setup
        tournament = create_test_tournament()
        tournament["seasons"][0]["rounds"][0]["matchdays"][0]["createStandings"] = True
        tournament["seasons"][0]["standingsSettings"] = {
            "pointsWinReg": 3,
            "pointsLossReg": 0,
            "pointsDrawReg": 1,
            "pointsWinOvertime": 2,
            "pointsLossOvertime": 1,
            "pointsWinShootout": 2,
            "pointsLossShootout": 1,
        }
        await mongodb["tournaments"].insert_one(tournament)

        match = create_test_match(status="FINISHED")
        match["tournament"] = {"alias": tournament["alias"], "name": tournament["name"]}
        match["season"] = {
            "alias": tournament["seasons"][0]["alias"],
            "name": tournament["seasons"][0]["name"],
        }
        match["round"] = {
            "alias": tournament["seasons"][0]["rounds"][0]["alias"],
            "name": tournament["seasons"][0]["rounds"][0]["name"],
        }
        match["matchday"] = {
            "alias": tournament["seasons"][0]["rounds"][0]["matchdays"][0]["alias"],
            "name": tournament["seasons"][0]["rounds"][0]["matchdays"][0]["name"],
        }
        match["finishType"] = {"key": "OVERTIME", "value": "Verlängerung"}
        match["home"]["stats"] = {
            "gamePlayed": 1,
            "goalsFor": 4,
            "goalsAgainst": 3,
            "points": 2,
            "win": 0,
            "loss": 0,
            "draw": 0,
            "otWin": 1,
            "otLoss": 0,
            "soWin": 0,
            "soLoss": 0,
        }
        match["away"]["stats"] = {
            "gamePlayed": 1,
            "goalsFor": 3,
            "goalsAgainst": 4,
            "points": 1,
            "win": 0,
            "loss": 0,
            "draw": 0,
            "otWin": 0,
            "otLoss": 1,
            "soWin": 0,
            "soLoss": 0,
        }
        await mongodb["matches"].insert_one(match)

        # Execute
        stats_service = StatsService(mongodb)
        await stats_service.aggregate_matchday_standings(
            tournament["alias"],
            tournament["seasons"][0]["alias"],
            tournament["seasons"][0]["rounds"][0]["alias"],
            tournament["seasons"][0]["rounds"][0]["matchdays"][0]["alias"],
        )

        # Assert
        updated_tournament = await mongodb["tournaments"].find_one({"_id": tournament["_id"]})
        standings = updated_tournament["seasons"][0]["rounds"][0]["matchdays"][0]["standings"]

        assert len(standings) == 2
        teams = list(standings.keys())
        # OT winner gets 2 points
        assert standings[teams[0]]["points"] == 2
        assert standings[teams[0]]["otWins"] == 1
        # OT loser gets 1 point
        assert standings[teams[1]]["points"] == 1
        assert standings[teams[1]]["otLosses"] == 1

    async def test_calculate_player_card_stats_with_database(self, mongodb):
        """Test player card stats calculation with real database"""
        from tests.fixtures.data_fixtures import (
            create_test_match,
            create_test_player,
            create_test_roster_player,
            create_test_tournament,
        )

        # Setup - Create tournament with stats enabled
        tournament = create_test_tournament()
        tournament["seasons"][0]["rounds"][0]["createStats"] = True
        tournament["seasons"][0]["rounds"][0]["matchdays"][0]["createStats"] = True
        await mongodb["tournaments"].insert_one(tournament)

        # Create player
        player = create_test_player("player-1")
        player["_id"] = "player-1"  # Override _id to match roster player ID
        player["stats"] = []
        await mongodb["players"].insert_one(player)

        # Create match with player in roster
        match = create_test_match(status="FINISHED")
        match["tournament"] = {"alias": tournament["alias"], "name": tournament["name"]}
        match["season"] = {
            "alias": tournament["seasons"][0]["alias"],
            "name": tournament["seasons"][0]["name"],
        }
        match["round"] = {
            "alias": tournament["seasons"][0]["rounds"][0]["alias"],
            "name": tournament["seasons"][0]["rounds"][0]["name"],
        }
        match["matchday"] = {
            "alias": tournament["seasons"][0]["rounds"][0]["matchdays"][0]["alias"],
            "name": tournament["seasons"][0]["rounds"][0]["matchdays"][0]["name"],
        }

        roster_player = create_test_roster_player("player-1")
        roster_player["goals"] = 2
        roster_player["assists"] = 1
        roster_player["points"] = 3
        roster_player["penaltyMinutes"] = 4
        roster_player["called"] = False
        match["home"]["roster"] = {"players": [roster_player], "status": "SUBMITTED"}
        await mongodb["matches"].insert_one(match)

        # Execute
        stats_service = StatsService(mongodb)
        await stats_service.calculate_player_card_stats(
            ["player-1"],
            tournament["alias"],
            tournament["seasons"][0]["alias"],
            tournament["seasons"][0]["rounds"][0]["alias"],
            tournament["seasons"][0]["rounds"][0]["matchdays"][0]["alias"],
            token_payload=None,  # Skip called teams logic
        )

        # Assert - Check player stats were saved
        updated_player = await mongodb["players"].find_one({"_id": "player-1"})
        assert "stats" in updated_player
        assert len(updated_player["stats"]) > 0

        # Find the round stat
        round_stat = next(
            (
                s
                for s in updated_player["stats"]
                if s.get("round", {}).get("alias") == tournament["seasons"][0]["rounds"][0]["alias"]
                and s.get("matchday") is None
            ),
            None,
        )
        assert round_stat is not None
        assert round_stat["gamesPlayed"] == 1
        assert round_stat["goals"] == 2
        assert round_stat["assists"] == 1
        assert round_stat["points"] == 3
        assert round_stat["penaltyMinutes"] == 4

    async def test_called_teams_assignment_logic(self, mongodb, client: AsyncClient, admin_token):
        """Test that players with 5+ called matches get team assignments and playUpTrackings persisted in DB"""
        from tests.fixtures.data_fixtures import (
            create_test_match,
            create_test_player,
            create_test_roster_player,
            create_test_tournament,
        )

        await mongodb["players"].delete_many({"_id": "player-called-1"})

        tournament = create_test_tournament()
        tournament["seasons"][0]["rounds"][0]["createStats"] = True
        await mongodb["tournaments"].insert_one(tournament)

        player = create_test_player("player-called-1")
        player["_id"] = "player-called-1"
        player["stats"] = [
            {
                "tournament": {"alias": tournament["alias"], "name": tournament["name"]},
                "season": {
                    "alias": tournament["seasons"][0]["alias"],
                    "name": tournament["seasons"][0]["name"],
                },
                "round": {
                    "alias": tournament["seasons"][0]["rounds"][0]["alias"],
                    "name": tournament["seasons"][0]["rounds"][0]["name"],
                },
                "team": {
                    "name": "Test Team",
                    "fullName": "Test Team",
                    "shortName": "TT",
                    "tinyName": "TT",
                },
                "gamesPlayed": 5,
                "goals": 5,
                "assists": 0,
                "points": 5,
                "penaltyMinutes": 0,
                "calledMatches": 5,
            }
        ]
        player["assignedTeams"] = []
        player["playUpTrackings"] = []
        await mongodb["players"].insert_one(player)

        for _i in range(5):
            match = create_test_match(status="FINISHED")
            match["tournament"] = {"alias": tournament["alias"], "name": tournament["name"]}
            match["season"] = {
                "alias": tournament["seasons"][0]["alias"],
                "name": tournament["seasons"][0]["name"],
            }
            match["round"] = {
                "alias": tournament["seasons"][0]["rounds"][0]["alias"],
                "name": tournament["seasons"][0]["rounds"][0]["name"],
            }
            match["matchday"] = {
                "alias": tournament["seasons"][0]["rounds"][0]["matchdays"][0]["alias"],
                "name": tournament["seasons"][0]["rounds"][0]["matchdays"][0]["name"],
            }
            match["matchStatus"] = {"key": "FINISHED", "value": "Beendet"}
            match["home"]["teamId"] = "test-team-id"
            match["home"]["name"] = "Test Team"
            match["home"]["teamAlias"] = "test-team"
            match["home"]["ageGroup"] = "U20"
            match["home"]["ishdId"] = "123"
            match["home"]["clubId"] = "test-club-id"
            match["home"]["clubName"] = "Test Club"
            match["home"]["clubAlias"] = "test-club"
            match["home"]["clubIshdId"] = "456"

            roster_player = create_test_roster_player("player-called-1")
            roster_player["called"] = True
            roster_player["calledFromTeam"] = {
                "teamId": "origin-team-id",
                "teamName": "Origin Team",
                "teamAlias": "origin-team",
            }
            roster_player["goals"] = 1
            match["home"]["roster"] = {"players": [roster_player], "status": "SUBMITTED"}
            await mongodb["matches"].insert_one(match)

        from types import SimpleNamespace

        token_payload = SimpleNamespace(
            sub="user-1",
            roles=["ADMIN"],
            firstName="Test",
            lastName="User",
            clubId=None,
            clubName=None,
        )

        stats_service = StatsService(mongodb)
        await stats_service.calculate_player_card_stats(
            ["player-called-1"],
            tournament["alias"],
            tournament["seasons"][0]["alias"],
            tournament["seasons"][0]["rounds"][0]["alias"],
            tournament["seasons"][0]["rounds"][0]["matchdays"][0]["alias"],
            token_payload=token_payload,
        )

        updated_player = await mongodb["players"].find_one({"_id": "player-called-1"})

        playup_trackings = updated_player.get("playUpTrackings", [])
        assert len(playup_trackings) >= 1, (
            f"playUpTrackings should have at least one entry. Got: {playup_trackings}"
        )
        tracking = playup_trackings[0]
        assert tracking["fromTeamId"] == "origin-team-id", "fromTeamId should match calledFromTeam"
        assert tracking["toTeamId"] == "test-team-id", "toTeamId should match match team"
        assert "occurrences" in tracking, "tracking should have occurrences"
        assert len(tracking["occurrences"]) == 5, (
            f"Should have 5 occurrences (one per match). Got: {len(tracking['occurrences'])}"
        )

        assigned_teams = updated_player.get("assignedTeams", [])
        team_found = False
        for club in assigned_teams:
            for team in club.get("teams", []):
                if team.get("teamId") == "test-team-id":
                    team_found = True
                    assert team.get("source") == "CALLED", "source should be CALLED"
        assert team_found, (
            f"Team 'test-team-id' should be in assignedTeams. Got: {assigned_teams}"
        )


@pytest.mark.asyncio
class TestStatsServiceEdgeCases:
    """Test edge cases and error handling"""

    async def test_standings_with_no_matches(self, mongodb):
        """Test standings calculation when no matches exist"""
        from tests.fixtures.data_fixtures import create_test_tournament

        tournament = create_test_tournament()
        tournament["seasons"][0]["rounds"][0]["createStandings"] = True
        await mongodb["tournaments"].insert_one(tournament)

        stats_service = StatsService(mongodb)
        await stats_service.aggregate_round_standings(
            tournament["alias"],
            tournament["seasons"][0]["alias"],
            tournament["seasons"][0]["rounds"][0]["alias"],
        )

        # Should create empty standings
        updated = await mongodb["tournaments"].find_one({"_id": tournament["_id"]})
        assert updated["seasons"][0]["rounds"][0]["standings"] == {}

    async def test_roster_stats_with_missing_match(self, mongodb):
        """Test roster stats calculation with non-existent match"""
        from exceptions.custom_exceptions import ResourceNotFoundException

        stats_service = StatsService(mongodb)

        with pytest.raises(ResourceNotFoundException):
            await stats_service.calculate_roster_stats("non-existent-id", "home")

    async def test_standings_settings_missing_tournament(self, mongodb):
        """Test fetching standings settings for non-existent tournament"""
        from exceptions.custom_exceptions import ResourceNotFoundException

        stats_service = StatsService(mongodb)

        with pytest.raises(ResourceNotFoundException):
            await stats_service.get_standings_settings("fake-tournament", "fake-season")
