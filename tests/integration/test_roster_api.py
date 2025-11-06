
"""Integration tests for roster API endpoints"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestRosterAPI:
    """Test roster management operations"""

    async def test_put_roster_creates_new_roster(self, client: AsyncClient, mongodb, admin_token):
        """Test PUT endpoint creates roster when none exists"""
        from tests.fixtures.data_fixtures import create_test_match, create_test_player

        # Setup - Match with no roster
        match = create_test_match(status="SCHEDULED")
        player1 = create_test_player("player-1")
        player2 = create_test_player("player-2")
        await mongodb["matches"].insert_one(match)
        await mongodb["players"].insert_one(player1)
        await mongodb["players"].insert_one(player2)

        # Execute - PUT entire roster (2 players)
        roster_data = [
            {
                "player": {
                    "playerId": player1["_id"],
                    "firstName": player1["firstName"],
                    "lastName": player1["lastName"],
                    "jerseyNumber": 10
                },
                "playerPosition": {"key": "FW", "value": "Forward"},
                "passNumber": "PASS-1234",
            },
            {
                "player": {
                    "playerId": player2["_id"],
                    "firstName": player2["firstName"],
                    "lastName": player2["lastName"],
                    "jerseyNumber": 20
                },
                "playerPosition": {"key": "DF", "value": "Defense"},
                "passNumber": "PASS-5678",
            }
        ]

        response = await client.put(
            f"/matches/{match['_id']}/home/roster",
            json=roster_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Assert response
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)
        assert len(data["data"]) == 2
        assert data["data"][0]["player"]["playerId"] == player1["_id"]
        assert data["data"][0]["player"]["jerseyNumber"] == 10
        assert data["data"][1]["player"]["playerId"] == player2["_id"]
        assert data["data"][1]["player"]["jerseyNumber"] == 20

        # Verify database persistence
        updated = await mongodb["matches"].find_one({"_id": match["_id"]})
        assert len(updated["home"]["roster"]) == 2
        assert updated["home"]["roster"][0]["player"]["playerId"] == player1["_id"]
        assert updated["home"]["roster"][1]["player"]["playerId"] == player2["_id"]

    async def test_put_roster_replaces_existing_roster(self, client: AsyncClient, mongodb, admin_token):
        """Test PUT endpoint replaces entire existing roster"""
        from tests.fixtures.data_fixtures import create_test_match, create_test_player, create_test_roster_player

        # Setup - Match with existing roster
        match = create_test_match(status="SCHEDULED")
        old_player = create_test_roster_player("old-player-1")
        match["home"]["roster"] = [old_player]
        
        new_player1 = create_test_player("new-player-1")
        new_player2 = create_test_player("new-player-2")
        await mongodb["matches"].insert_one(match)
        await mongodb["players"].insert_one(new_player1)
        await mongodb["players"].insert_one(new_player2)

        # Execute - PUT completely new roster
        roster_data = [
            {
                "player": {
                    "playerId": new_player1["_id"],
                    "firstName": new_player1["firstName"],
                    "lastName": new_player1["lastName"],
                    "jerseyNumber": 99
                },
                "playerPosition": {"key": "GK", "value": "Goalkeeper"},
                "passNumber": "PASS-9999",
            },
            {
                "player": {
                    "playerId": new_player2["_id"],
                    "firstName": new_player2["firstName"],
                    "lastName": new_player2["lastName"],
                    "jerseyNumber": 88
                },
                "playerPosition": {"key": "FW", "value": "Forward"},
                "passNumber": "PASS-8888",
            }
        ]

        response = await client.put(
            f"/matches/{match['_id']}/home/roster",
            json=roster_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Assert response
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]) == 2

        # Verify old player is gone, new players are present
        updated = await mongodb["matches"].find_one({"_id": match["_id"]})
        assert len(updated["home"]["roster"]) == 2
        player_ids = [p["player"]["playerId"] for p in updated["home"]["roster"]]
        assert "old-player-1" not in player_ids
        assert new_player1["_id"] in player_ids
        assert new_player2["_id"] in player_ids

    async def test_put_roster_with_duplicate_player_fails(self, client: AsyncClient, mongodb, admin_token):
        """Test PUT fails when same player appears twice in roster"""
        from tests.fixtures.data_fixtures import create_test_match, create_test_player

        # Setup
        match = create_test_match(status="SCHEDULED")
        player = create_test_player("player-1")
        await mongodb["matches"].insert_one(match)
        await mongodb["players"].insert_one(player)

        # Execute - Try to PUT roster with duplicate player
        roster_data = [
            {
                "player": {
                    "playerId": player["_id"],
                    "firstName": player["firstName"],
                    "lastName": player["lastName"],
                    "jerseyNumber": 10
                },
                "playerPosition": {"key": "FW", "value": "Forward"},
                "passNumber": "PASS-1234",
            },
            {
                "player": {
                    "playerId": player["_id"],  # Same player again
                    "firstName": player["firstName"],
                    "lastName": player["lastName"],
                    "jerseyNumber": 20
                },
                "playerPosition": {"key": "DF", "value": "Defense"},
                "passNumber": "PASS-5678",
            }
        ]

        response = await client.put(
            f"/matches/{match['_id']}/home/roster",
            json=roster_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Assert - Should fail validation
        assert response.status_code == 400

    async def test_put_roster_unchanged_returns_200(self, client: AsyncClient, mongodb, admin_token):
        """Test PUT with identical roster returns 200 with unchanged message"""
        from tests.fixtures.data_fixtures import create_test_match, create_test_player

        # Setup - Match with existing roster
        match = create_test_match(status="SCHEDULED")
        player = create_test_player("player-1")
        await mongodb["matches"].insert_one(match)
        await mongodb["players"].insert_one(player)

        roster_data = [
            {
                "player": {
                    "playerId": player["_id"],
                    "firstName": player["firstName"],
                    "lastName": player["lastName"],
                    "jerseyNumber": 10
                },
                "playerPosition": {"key": "FW", "value": "Forward"},
                "passNumber": "PASS-1234",
            }
        ]

        # First PUT to create roster
        await client.put(
            f"/matches/{match['_id']}/home/roster",
            json=roster_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Second PUT with same data
        response = await client.put(
            f"/matches/{match['_id']}/home/roster",
            json=roster_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Assert - Should return 200 (not 304)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "unchanged" in data["message"].lower() or "identical" in data["message"].lower()

    async def test_put_roster_cannot_remove_player_with_stats(self, client: AsyncClient, mongodb, admin_token):
        """Test PUT fails when trying to remove player who has goals/assists/penalties"""
        from tests.fixtures.data_fixtures import create_test_match, create_test_player, create_test_roster_player

        # Setup - Match with player who has stats
        match = create_test_match(status="INPROGRESS")
        player_with_stats = create_test_roster_player("player-1")
        player_with_stats["goals"] = 2
        match["home"]["roster"] = [player_with_stats]
        match["home"]["scores"] = [{
            "_id": "score1",
            "goalPlayer": {
                "playerId": "player-1",
                "firstName": "Test",
                "lastName": "Player",
                "jerseyNumber": 10
            }
        }]
        
        new_player = create_test_player("player-2")
        await mongodb["matches"].insert_one(match)
        await mongodb["players"].insert_one(new_player)

        # Execute - Try to PUT roster without the player who has stats
        roster_data = [
            {
                "player": {
                    "playerId": new_player["_id"],
                    "firstName": new_player["firstName"],
                    "lastName": new_player["lastName"],
                    "jerseyNumber": 20
                },
                "playerPosition": {"key": "FW", "value": "Forward"},
                "passNumber": "PASS-2222",
            }
        ]

        response = await client.put(
            f"/matches/{match['_id']}/home/roster",
            json=roster_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Assert - Should fail because player-1 is in scores but not in new roster
        assert response.status_code == 400
        data = response.json()
        assert "scores" in data["error"]["message"].lower() or "roster" in data["error"]["message"].lower()

    async def test_get_roster_list(self, client: AsyncClient, mongodb):
        """Test retrieving roster for a team"""
        from tests.fixtures.data_fixtures import create_test_match, create_test_roster_player

        # Setup
        match = create_test_match()
        match["home"]["roster"] = [
            create_test_roster_player("player-1"),
            create_test_roster_player("player-2")
        ]
        await mongodb["matches"].insert_one(match)

        # Execute
        response = await client.get(f"/matches/{match['_id']}/home/roster")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)
        assert len(data["data"]) == 2

    async def test_put_roster_propagates_jersey_numbers(self, client: AsyncClient, mongodb, admin_token):
        """Test that updating roster jersey numbers propagates to scores and penalties"""
        from tests.fixtures.data_fixtures import create_test_match, create_test_player

        # Setup - Match with roster, scores, and penalties
        match = create_test_match(status="INPROGRESS")
        player = create_test_player("player-1")
        await mongodb["matches"].insert_one(match)
        await mongodb["players"].insert_one(player)

        # First, create initial roster
        initial_roster = [{
            "player": {
                "playerId": player["_id"],
                "firstName": player["firstName"],
                "lastName": player["lastName"],
                "jerseyNumber": 10
            },
            "playerPosition": {"key": "FW", "value": "Forward"},
            "passNumber": "PASS-1234",
        }]

        await client.put(
            f"/matches/{match['_id']}/home/roster",
            json=initial_roster,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Add score and penalty manually to DB
        await mongodb["matches"].update_one(
            {"_id": match["_id"]},
            {
                "$set": {
                    "home.scores": [{
                        "_id": "s1",
                        "matchTime": "10:00",
                        "goalPlayer": {
                            "playerId": player["_id"],
                            "firstName": player["firstName"],
                            "lastName": player["lastName"],
                            "jerseyNumber": 10
                        }
                    }],
                    "home.penalties": [{
                        "_id": "p1",
                        "matchTimeStart": "15:00",
                        "penaltyPlayer": {
                            "playerId": player["_id"],
                            "firstName": player["firstName"],
                            "lastName": player["lastName"],
                            "jerseyNumber": 10
                        },
                        "penaltyCode": {"key": "MIN2", "value": "2 Minutes"},
                        "penaltyMinutes": 2
                    }]
                }
            }
        )

        # Execute - PUT roster with updated jersey number
        updated_roster = [{
            "player": {
                "playerId": player["_id"],
                "firstName": player["firstName"],
                "lastName": player["lastName"],
                "jerseyNumber": 99  # Changed from 10 to 99
            },
            "playerPosition": {"key": "FW", "value": "Forward"},
            "passNumber": "PASS-1234",
        }]

        response = await client.put(
            f"/matches/{match['_id']}/home/roster",
            json=updated_roster,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Assert
        assert response.status_code == 200

        # Verify jersey numbers updated in scores and penalties
        updated = await mongodb["matches"].find_one({"_id": match["_id"]})
        assert updated["home"]["roster"][0]["player"]["jerseyNumber"] == 99
        assert updated["home"]["scores"][0]["goalPlayer"]["jerseyNumber"] == 99
        assert updated["home"]["penalties"][0]["penaltyPlayer"]["jerseyNumber"] == 99

    async def test_put_roster_requires_authentication(self, client: AsyncClient, mongodb):
        """Test PUT roster requires valid admin token"""
        from tests.fixtures.data_fixtures import create_test_match

        match = create_test_match(status="SCHEDULED")
        await mongodb["matches"].insert_one(match)

        roster_data = [{
            "player": {
                "playerId": "player-1",
                "firstName": "Test",
                "lastName": "Player",
                "jerseyNumber": 10
            },
            "playerPosition": {"key": "FW", "value": "Forward"},
            "passNumber": "PASS-1234",
        }]

        # Execute without token
        response = await client.put(
            f"/matches/{match['_id']}/home/roster",
            json=roster_data
        )

        # Assert - Should fail with 401 or 403
        assert response.status_code in [401, 403]

    async def test_put_empty_roster_clears_roster(self, client: AsyncClient, mongodb, admin_token):
        """Test PUT with empty list clears the roster (if no scores/penalties exist)"""
        from tests.fixtures.data_fixtures import create_test_match, create_test_roster_player

        # Setup - Match with existing roster but no scores/penalties
        match = create_test_match(status="SCHEDULED")
        match["home"]["roster"] = [
            create_test_roster_player("player-1"),
            create_test_roster_player("player-2")
        ]
        await mongodb["matches"].insert_one(match)

        # Execute - PUT empty roster
        response = await client.put(
            f"/matches/{match['_id']}/home/roster",
            json=[],
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]) == 0

        # Verify database
        updated = await mongodb["matches"].find_one({"_id": match["_id"]})
        assert len(updated["home"]["roster"]) == 0
