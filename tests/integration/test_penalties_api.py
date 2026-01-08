"""Integration tests for penalties API endpoints"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestPenaltiesAPI:
    """Test penalty creation, update, and deletion"""

    async def test_create_penalty_success(self, client: AsyncClient, mongodb, admin_token):
        """Test creating a penalty during INPROGRESS match"""
        from tests.fixtures.data_fixtures import create_test_match, create_test_roster_player

        # Setup - Match with roster and initial penalty minutes
        match = create_test_match(status="INPROGRESS")
        player = create_test_roster_player("player-1")
        player["penaltyMinutes"] = 0
        match["home"]["roster"] = [player]
        await mongodb["matches"].insert_one(match)

        # Execute - PenaltyService handles incremental penalty minute updates
        penalty_data = {
            "matchTimeStart": "10:30",
            "penaltyPlayer": {
                "playerId": "player-1",
                "firstName": "Test",
                "lastName": "Player",
                "jerseyNumber": 10,
            },
            "penaltyCode": {"key": "2MIN", "label": "2 Minutes"},
            "penaltyMinutes": 2,
            "isGM": False,
            "isMP": False,
        }

        response = await client.post(
            f"/matches/{match['_id']}/home/penalties",
            json=penalty_data,
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        # Assert response
        assert response.status_code == 201
        data = response.json()
        assert data["data"]["matchTimeStart"] == "10:30"
        # assert data["data"]["matchSecondsStart"] == 630
        assert data["data"]["penaltyPlayer"]["playerId"] == "player-1"
        assert data["data"]["penaltyMinutes"] == 2
        assert "_id" in data["data"]

        # Verify database persistence
        updated = await mongodb["matches"].find_one({"_id": match["_id"]})
        assert len(updated["home"]["penalties"]) == 1

        # Verify roster penalty minutes incremented
        roster_player = updated["home"]["roster"][0]
        assert roster_player["penaltyMinutes"] == 2

    async def test_create_game_misconduct_penalty(self, client: AsyncClient, mongodb, admin_token):
        """Test creating a game misconduct penalty"""
        from tests.fixtures.data_fixtures import create_test_match, create_test_roster_player

        # Setup
        match = create_test_match(status="INPROGRESS")
        player = create_test_roster_player("player-1")
        match["home"]["roster"] = [player]
        await mongodb["matches"].insert_one(match)

        # Execute
        penalty_data = {
            "matchTimeStart": "15:00",
            "penaltyPlayer": {
                "playerId": "player-1",
                "firstName": "Test",
                "lastName": "Player",
                "jerseyNumber": 10,
            },
            "penaltyCode": {"key": "GM", "label": "Game Misconduct"},
            "penaltyMinutes": 10,
            "isGM": True,
            "isMP": False,
        }

        response = await client.post(
            f"/matches/{match['_id']}/home/penalties",
            json=penalty_data,
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["data"]["isGM"] is True
        assert data["data"]["penaltyMinutes"] == 10

    async def test_create_penalty_player_not_in_roster(
        self, client: AsyncClient, mongodb, admin_token
    ):
        """Test creating penalty with player not in roster fails"""
        from tests.fixtures.data_fixtures import create_test_match

        match = create_test_match(status="INPROGRESS")
        await mongodb["matches"].insert_one(match)

        penalty_data = {
            "matchTimeStart": "10:30",
            "penaltyPlayer": {
                "playerId": "invalid-player",
                "firstName": "Test",
                "lastName": "Player",
                "jerseyNumber": 10,
            },
            "penaltyCode": {"key": "2MIN", "label": "2 Minutes"},
            "penaltyMinutes": 2,
        }

        response = await client.post(
            f"/matches/{match['_id']}/home/penalties",
            json=penalty_data,
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 400
        assert "not in roster" in response.json()["error"]["message"].lower()

    async def test_create_penalty_wrong_match_status(
        self, client: AsyncClient, mongodb, admin_token
    ):
        """Test creating penalty when match not INPROGRESS fails"""
        from tests.fixtures.data_fixtures import create_test_match

        match = create_test_match(status="SCHEDULED")
        await mongodb["matches"].insert_one(match)

        penalty_data = {
            "matchTimeStart": "10:30",
            "penaltyPlayer": {
                "playerId": "player-1",
                "firstName": "Test",
                "lastName": "Player",
                "jerseyNumber": 10,
            },
            "penaltyCode": {"key": "2MIN", "label": "2 Minutes"},
            "penaltyMinutes": 2,
        }

        response = await client.post(
            f"/matches/{match['_id']}/home/penalties",
            json=penalty_data,
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 400

    async def test_update_penalty(self, client: AsyncClient, mongodb, admin_token):
        """Test updating an existing penalty"""
        from bson import ObjectId

        from tests.fixtures.data_fixtures import create_test_match, create_test_roster_player

        # Setup
        match = create_test_match(status="INPROGRESS")
        penalty_id = str(ObjectId())
        player = create_test_roster_player("player-1")
        match["home"]["roster"] = [player]
        match["home"]["penalties"] = [
            {
                "_id": penalty_id,
                "matchSecondsStart": 300,
                "matchSecondsEnd": None,
                "penaltyPlayer": {
                    "playerId": "player-1",
                    "firstName": "Test",
                    "lastName": "Player",
                    "jerseyNumber": 10,
                },
                "penaltyCode": {"key": "2MIN", "label": "2 Minutes"},
                "penaltyMinutes": 2,
                "isGM": False,
                "isMP": False,
            }
        ]
        await mongodb["matches"].insert_one(match)

        # Execute - Update end time
        response = await client.patch(
            f"/matches/{match['_id']}/home/penalties/{penalty_id}",
            json={"matchTimeEnd": "07:00"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["matchTimeEnd"] == "07:00"
        # assert data["data"]["matchSecondsEnd"] == 420

    async def test_delete_penalty(self, client: AsyncClient, mongodb, admin_token):
        """Test deleting a penalty with decremental penalty minute updates"""
        from bson import ObjectId

        from tests.fixtures.data_fixtures import create_test_match, create_test_roster_player

        # Setup - Match with penalty and penalty minutes
        match = create_test_match(status="INPROGRESS")
        penalty_id = str(ObjectId())
        player = create_test_roster_player("player-1")
        player["penaltyMinutes"] = 2
        match["home"]["roster"] = [player]
        match["home"]["penalties"] = [
            {
                "_id": penalty_id,
                "matchSecondsStart": 300,
                "matchSecondsEnd": None,
                "penaltyPlayer": {
                    "playerId": "player-1",
                    "firstName": "Test",
                    "lastName": "Player",
                    "jerseyNumber": 10,
                },
                "penaltyCode": {"key": "2MIN", "label": "2 Minutes"},
                "penaltyMinutes": 2,
                "isGM": False,
                "isMP": False,
            }
        ]
        await mongodb["matches"].insert_one(match)

        # Execute - PenaltyService handles decremental penalty minute updates
        response = await client.delete(
            f"/matches/{match['_id']}/home/penalties/{penalty_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        # Assert
        assert response.status_code == 204

        # Verify database - penalty removed
        updated = await mongodb["matches"].find_one({"_id": match["_id"]})
        assert len(updated["home"]["penalties"]) == 0

        # Verify roster penalty minutes decremented
        roster_player = updated["home"]["roster"][0]
        assert roster_player["penaltyMinutes"] == 0

    async def test_get_penalty_sheet(self, client: AsyncClient, mongodb):
        """Test retrieving penalty sheet for a team"""
        from bson import ObjectId

        from tests.fixtures.data_fixtures import create_test_match

        # Setup - Create fresh match with exactly 2 penalties
        match = create_test_match(status="INPROGRESS")
        match["home"]["penalties"] = [
            {
                "_id": str(ObjectId()),
                "matchSecondsStart": 300,
                "matchSecondsEnd": None,
                "penaltyPlayer": {
                    "playerId": "player-1",
                    "firstName": "Test",
                    "lastName": "Player",
                    "jerseyNumber": 10,
                },
                "penaltyCode": {"key": "2MIN", "label": "2 Minutes"},
                "penaltyMinutes": 2,
                "isGM": False,
                "isMP": False,
            },
            {
                "_id": str(ObjectId()),
                "matchSecondsStart": 600,
                "matchSecondsEnd": None,
                "penaltyPlayer": {
                    "playerId": "player-2",
                    "firstName": "Test2",
                    "lastName": "Player2",
                    "jerseyNumber": 20,
                },
                "penaltyCode": {"key": "5MIN", "label": "5 Minutes"},
                "penaltyMinutes": 5,
                "isGM": False,
                "isMP": False,
            },
        ]
        await mongodb["matches"].insert_one(match)

        # Execute
        response = await client.get(f"/matches/{match['_id']}/home/penalties")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]) == 2
        assert data["data"][0]["penaltyMinutes"] in [2, 5]
        assert data["data"][1]["penaltyMinutes"] in [2, 5]

    async def test_get_one_penalty(self, client: AsyncClient, mongodb):
        """Test retrieving a single penalty"""
        from bson import ObjectId

        from tests.fixtures.data_fixtures import create_test_match

        # Setup
        match = create_test_match()
        penalty_id = str(ObjectId())
        match["home"]["penalties"] = [
            {
                "_id": penalty_id,
                "matchSecondsStart": 600,
                "matchSecondsEnd": None,
                "penaltyPlayer": {
                    "playerId": "player-1",
                    "firstName": "Test",
                    "lastName": "Player",
                    "jerseyNumber": 10,
                },
                "penaltyCode": {"key": "2MIN", "label": "2 Minutes"},
                "penaltyMinutes": 2,
                "isGM": False,
                "isMP": False,
            }
        ]
        await mongodb["matches"].insert_one(match)

        # Execute
        response = await client.get(f"/matches/{match['_id']}/home/penalties/{penalty_id}")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["_id"] == penalty_id
        assert data["data"]["matchTimeStart"] == "10:00"

    async def test_create_penalty_requires_inprogress_status(
        self, client: AsyncClient, mongodb, admin_token
    ):
        """Test that penalties can only be created during INPROGRESS matches"""
        from tests.fixtures.data_fixtures import create_test_match, create_test_roster_player

        # Setup - FINISHED match
        match = create_test_match(status="FINISHED")
        player = create_test_roster_player("player-1")
        match["home"]["roster"] = [player]
        await mongodb["matches"].insert_one(match)

        # Execute
        penalty_data = {
            "matchTimeStart": "10:30",
            "penaltyPlayer": {
                "playerId": "player-1",
                "firstName": "Test",
                "lastName": "Player",
                "jerseyNumber": 10,
            },
            "penaltyCode": {"key": "2MIN", "label": "2 Minutes"},
            "penaltyMinutes": 2,
        }

        response = await client.post(
            f"/matches/{match['_id']}/home/penalties",
            json=penalty_data,
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        # Assert - Should fail because match is not INPROGRESS
        assert response.status_code == 400
        assert "inprogress" in response.json()["error"]["message"].lower()
