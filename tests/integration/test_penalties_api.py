
"""Integration tests for penalties API endpoints"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestPenaltiesAPI:
    """Test penalty creation, update, and deletion"""

    async def test_create_penalty_success(self, client: AsyncClient, mongodb, admin_token):
        """Test creating a penalty during INPROGRESS match"""
        from tests.fixtures.data_fixtures import create_test_match, create_test_roster_player
        
        # Setup - Match with roster
        match = create_test_match(status="INPROGRESS")
        player = create_test_roster_player("player-1")
        match["home"]["roster"] = [player]
        await mongodb["matches"].insert_one(match)
        
        # Execute
        penalty_data = {
            "matchTimeStart": "10:30",
            "penaltyPlayer": {"playerId": "player-1"},
            "penaltyCode": {"key": "2MIN", "label": "2 Minutes"},
            "penaltyMinutes": 2,
            "isGM": False,
            "isMP": False
        }
        
        response = await client.post(
            f"/matches/{match['_id']}/home/penalties",
            json=penalty_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        # Assert response
        assert response.status_code == 201
        data = response.json()
        assert data["matchTimeStart"] == "10:30"
        assert data["penaltyPlayer"]["playerId"] == "player-1"
        assert data["penaltyMinutes"] == 2
        assert "_id" in data
        
        # Verify database
        updated = await mongodb["matches"].find_one({"_id": match["_id"]})
        assert len(updated["home"]["penalties"]) == 1
        
        # Verify roster penalty minutes updated
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
            "penaltyPlayer": {"playerId": "player-1"},
            "penaltyCode": {"key": "GM", "label": "Game Misconduct"},
            "penaltyMinutes": 10,
            "isGM": True,
            "isMP": False
        }
        
        response = await client.post(
            f"/matches/{match['_id']}/home/penalties",
            json=penalty_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["isGM"] is True
        assert data["penaltyMinutes"] == 10

    async def test_create_penalty_player_not_in_roster(self, client: AsyncClient, mongodb, admin_token):
        """Test creating penalty with player not in roster fails"""
        from tests.fixtures.data_fixtures import create_test_match
        
        match = create_test_match(status="INPROGRESS")
        await mongodb["matches"].insert_one(match)
        
        penalty_data = {
            "matchTimeStart": "10:30",
            "penaltyPlayer": {"playerId": "invalid-player"},
            "penaltyCode": {"key": "2MIN", "label": "2 Minutes"},
            "penaltyMinutes": 2
        }
        
        response = await client.post(
            f"/matches/{match['_id']}/home/penalties",
            json=penalty_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 400
        assert "not in roster" in response.json()["error"]["message"].lower()

    async def test_create_penalty_wrong_match_status(self, client: AsyncClient, mongodb, admin_token):
        """Test creating penalty when match not INPROGRESS fails"""
        from tests.fixtures.data_fixtures import create_test_match
        
        match = create_test_match(status="SCHEDULED")
        await mongodb["matches"].insert_one(match)
        
        penalty_data = {
            "matchTimeStart": "10:30",
            "penaltyCode": {"key": "2MIN", "label": "2 Minutes"},
            "penaltyMinutes": 2
        }
        
        response = await client.post(
            f"/matches/{match['_id']}/home/penalties",
            json=penalty_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 400

    async def test_update_penalty(self, client: AsyncClient, mongodb, admin_token):
        """Test updating an existing penalty"""
        from tests.fixtures.data_fixtures import create_test_match, create_test_roster_player
        
        # Setup
        match = create_test_match(status="INPROGRESS")
        player = create_test_roster_player("player-1")
        match["home"]["roster"] = [player]
        match["home"]["penalties"] = [{
            "_id": "penalty-1",
            "matchTimeStart": "05:00",
            "penaltyPlayer": {"playerId": "player-1"},
            "penaltyCode": {"key": "2MIN", "label": "2 Minutes"},
            "penaltyMinutes": 2
        }]
        await mongodb["matches"].insert_one(match)
        
        # Execute - Update end time
        response = await client.patch(
            f"/matches/{match['_id']}/home/penalties/penalty-1",
            json={"matchTimeEnd": "07:00"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["matchTimeEnd"] == "07:00"

    async def test_delete_penalty(self, client: AsyncClient, mongodb, admin_token):
        """Test deleting a penalty"""
        from tests.fixtures.data_fixtures import create_test_match, create_test_roster_player
        
        # Setup
        match = create_test_match(status="INPROGRESS")
        player = create_test_roster_player("player-1")
        player["penaltyMinutes"] = 2
        match["home"]["roster"] = [player]
        match["home"]["penalties"] = [{
            "_id": "penalty-1",
            "penaltyPlayer": {"playerId": "player-1"},
            "penaltyMinutes": 2
        }]
        await mongodb["matches"].insert_one(match)
        
        # Execute
        response = await client.delete(
            f"/matches/{match['_id']}/home/penalties/penalty-1",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        # Assert
        assert response.status_code == 204
        
        # Verify database
        updated = await mongodb["matches"].find_one({"_id": match["_id"]})
        assert len(updated["home"]["penalties"]) == 0
        
        # Verify roster penalty minutes decremented
        roster_player = updated["home"]["roster"][0]
        assert roster_player["penaltyMinutes"] == 0

    async def test_get_penalty_sheet(self, client: AsyncClient, mongodb):
        """Test retrieving penalty sheet for a team"""
        from tests.fixtures.data_fixtures import create_test_match
        
        # Setup
        match = create_test_match(status="INPROGRESS")
        match["home"]["penalties"] = [
            {"_id": "p1", "penaltyMinutes": 2},
            {"_id": "p2", "penaltyMinutes": 5}
        ]
        await mongodb["matches"].insert_one(match)
        
        # Execute
        response = await client.get(f"/matches/{match['_id']}/home/penalties")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    async def test_get_one_penalty(self, client: AsyncClient, mongodb):
        """Test retrieving a single penalty"""
        from tests.fixtures.data_fixtures import create_test_match
        
        # Setup
        match = create_test_match()
        match["home"]["penalties"] = [{
            "_id": "penalty-1",
            "matchTimeStart": "10:00",
            "penaltyMinutes": 2
        }]
        await mongodb["matches"].insert_one(match)
        
        # Execute
        response = await client.get(
            f"/matches/{match['_id']}/home/penalties/penalty-1"
        )
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["_id"] == "penalty-1"
        assert data["matchTimeStart"] == "10:00"
