"""Integration tests for roster API endpoints"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestRosterAPI:
    """Test roster management operations"""

    async def test_add_player_to_roster(self, client: AsyncClient, mongodb,
                                        admin_token):
        """Test adding a player to match roster"""
        from tests.fixtures.data_fixtures import create_test_match, create_test_player
        from bson import ObjectId

        # Setup - Direct DB insertion
        match = create_test_match(status="SCHEDULED")
        player = create_test_player("player-1")
        await mongodb["matches"].insert_one(match)
        await mongodb["players"].insert_one(player)

        # Execute - RosterService handles validation and DB updates
        roster_data = [{
            "player": {
               "playerId": player["_id"],
                "firstName": player["firstName"],
                "lastName": player["lastName"],
                "jerseyNumber": 10
            },
            "playerPosition": {
                "key": "FW",
                "value": "Forward"
            },
            "passNumber": "PASS-1234",
        }]

        response = await client.put(
            f"/matches/{match['_id']}/home/roster",
            json=roster_data,
            headers={"Authorization": f"Bearer {admin_token}"})

        # Assert response
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)
        assert len(data["data"]) == 1
        assert data["data"][0]["player"]["playerId"] == player["_id"]
        assert data["data"][0]["player"]["jerseyNumber"] == 10

        # Verify database persistence
        updated = await mongodb["matches"].find_one({"_id": match["_id"]})
        assert len(updated["home"]["roster"]) == 1
        assert updated["home"]["roster"][0]["player"]["playerId"] == player[
            "_id"]
        assert updated["home"]["roster"][0]["jersey"] == 10

    async def test_add_duplicate_player_fails(self, client: AsyncClient,
                                              mongodb, admin_token):
        """Test adding same player twice fails"""
        from tests.fixtures.data_fixtures import create_test_match, create_test_roster_player

        # Setup - Player already in roster
        match = create_test_match(status="SCHEDULED")
        player = create_test_roster_player("player-1")
        match["home"]["roster"] = [player]
        await mongodb["matches"].insert_one(match)

        # Execute - Try to add again
        response = await client.post(
            f"/matches/{match['_id']}/home/roster",
            json={"player": {
                "playerId": "player-1"
            }},
            headers={"Authorization": f"Bearer {admin_token}"})

        # Assert
        assert response.status_code == 400
        assert "already in roster" in response.json(
        )["error"]["message"].lower()

    async def test_remove_player_from_roster(self, client: AsyncClient,
                                             mongodb, admin_token):
        """Test removing a player from roster"""
        from tests.fixtures.data_fixtures import create_test_match, create_test_roster_player
        from bson import ObjectId

        # Setup
        match = create_test_match(status="SCHEDULED")
        roster_id = str(ObjectId())
        player = create_test_roster_player("player-1")
        player["_id"] = roster_id
        match["home"]["roster"] = [player]
        await mongodb["matches"].insert_one(match)

        # Execute
        response = await client.delete(
            f"/matches/{match['_id']}/home/roster/{roster_id}",
            headers={"Authorization": f"Bearer {admin_token}"})

        # Assert
        assert response.status_code == 204

        # Verify database
        updated = await mongodb["matches"].find_one({"_id": match["_id"]})
        assert len(updated["home"]["roster"]) == 0

    async def test_cannot_remove_player_with_stats(self, client: AsyncClient,
                                                   mongodb, admin_token):
        """Test cannot remove player who has goals/assists/penalties"""
        from tests.fixtures.data_fixtures import create_test_match, create_test_roster_player
        from bson import ObjectId

        # Setup - Player with stats
        match = create_test_match(status="INPROGRESS")
        roster_id = str(ObjectId())
        player = create_test_roster_player("player-1")
        player["_id"] = roster_id
        player["goals"] = 1
        match["home"]["roster"] = [player]
        await mongodb["matches"].insert_one(match)

        # Execute
        response = await client.delete(
            f"/matches/{match['_id']}/home/roster/{roster_id}",
            headers={"Authorization": f"Bearer {admin_token}"})

        # Assert - Should fail
        assert response.status_code == 400

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
        assert len(data) == 2

    async def test_update_roster_propagates_jersey_numbers(
            self, client: AsyncClient, mongodb, admin_token):
        """Test that updating roster jersey numbers propagates to scores and penalties"""
        from tests.fixtures.data_fixtures import create_test_match, create_test_roster_player

        # Setup - Match with roster, scores, and penalties
        match = create_test_match(status="INPROGRESS")
        player1 = create_test_roster_player("player-1")
        player1["jersey"] = 10
        player1["_id"] = "roster-1"
        match["home"]["roster"] = [player1]
        match["home"]["scores"] = [{
            "_id": "s1",
            "goalPlayer": {
                "playerId": "player-1",
                "jersey": 10
            }
        }]
        match["home"]["penalties"] = [{
            "_id": "p1",
            "penaltyPlayer": {
                "playerId": "player-1",
                "jersey": 10
            }
        }]
        await mongodb["matches"].insert_one(match)

        # Execute - Update roster with new jersey number
        updated_roster = [{"player": {"playerId": "player-1"}, "jersey": 99}]

        response = await client.put(
            f"/matches/{match['_id']}/home/roster",
            json=updated_roster,
            headers={"Authorization": f"Bearer {admin_token}"})

        # Assert
        assert response.status_code == 200

        # Verify jersey numbers updated in scores and penalties
        updated = await mongodb["matches"].find_one({"_id": match["_id"]})
        assert updated["home"]["roster"][0]["jersey"] == 99
        assert updated["home"]["scores"][0]["goalPlayer"]["jersey"] == 99
        assert updated["home"]["penalties"][0]["penaltyPlayer"]["jersey"] == 99
