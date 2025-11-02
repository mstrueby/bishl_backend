
"""Integration tests for scores API endpoints"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestScoresAPI:
    """Test score creation, update, and deletion"""

    async def test_create_score_success(self, client: AsyncClient, mongodb, admin_token):
        """Test creating a score during INPROGRESS match"""
        from tests.fixtures.data_fixtures import create_test_match, create_test_roster_player
        
        # Setup - Match with roster
        match = create_test_match(status="INPROGRESS")
        player = create_test_roster_player("player-1")
        match["home"]["roster"] = [player]
        await mongodb["matches"].insert_one(match)
        
        # Execute
        score_data = {
            "matchTime": "10:30",
            "goalPlayer": {"playerId": "player-1"}
        }
        
        response = await client.post(
            f"/matches/{match['_id']}/home/scores",
            json=score_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        # Assert response
        assert response.status_code == 201
        data = response.json()
        assert data["matchTime"] == "10:30"
        assert data["goalPlayer"]["playerId"] == "player-1"
        assert "_id" in data
        
        # Verify database
        updated = await mongodb["matches"].find_one({"_id": match["_id"]})
        assert len(updated["home"]["scores"]) == 1
        assert updated["home"]["stats"]["goalsFor"] == 1

    async def test_create_score_with_assist(self, client: AsyncClient, mongodb, admin_token):
        """Test creating a score with assist player"""
        from tests.fixtures.data_fixtures import create_test_match, create_test_roster_player
        
        # Setup
        match = create_test_match(status="INPROGRESS")
        player1 = create_test_roster_player("player-1")
        player2 = create_test_roster_player("player-2")
        match["home"]["roster"] = [player1, player2]
        await mongodb["matches"].insert_one(match)
        
        # Execute
        score_data = {
            "matchTime": "05:15",
            "goalPlayer": {"playerId": "player-1"},
            "assistPlayer": {"playerId": "player-2"}
        }
        
        response = await client.post(
            f"/matches/{match['_id']}/home/scores",
            json=score_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["assistPlayer"]["playerId"] == "player-2"

    async def test_create_score_player_not_in_roster(self, client: AsyncClient, mongodb, admin_token):
        """Test creating score with player not in roster fails"""
        from tests.fixtures.data_fixtures import create_test_match
        
        match = create_test_match(status="INPROGRESS")
        await mongodb["matches"].insert_one(match)
        
        score_data = {
            "matchTime": "10:30",
            "goalPlayer": {"playerId": "invalid-player"}
        }
        
        response = await client.post(
            f"/matches/{match['_id']}/home/scores",
            json=score_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 400
        assert "not in roster" in response.json()["error"]["message"].lower()

    async def test_create_score_wrong_match_status(self, client: AsyncClient, mongodb, admin_token):
        """Test creating score when match not INPROGRESS fails"""
        from tests.fixtures.data_fixtures import create_test_match
        
        match = create_test_match(status="SCHEDULED")
        await mongodb["matches"].insert_one(match)
        
        score_data = {"matchTime": "10:30"}
        
        response = await client.post(
            f"/matches/{match['_id']}/home/scores",
            json=score_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 400

    async def test_update_score(self, client: AsyncClient, mongodb, admin_token):
        """Test updating an existing score"""
        from tests.fixtures.data_fixtures import create_test_match, create_test_roster_player
        
        # Setup
        match = create_test_match(status="INPROGRESS")
        player = create_test_roster_player("player-1")
        match["home"]["roster"] = [player]
        match["home"]["scores"] = [{
            "_id": "score-1",
            "matchTime": "05:00",
            "goalPlayer": {"playerId": "player-1"}
        }]
        await mongodb["matches"].insert_one(match)
        
        # Execute - Update match time
        response = await client.patch(
            f"/matches/{match['_id']}/home/scores/score-1",
            json={"matchTime": "06:30"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["matchTime"] == "06:30"

    async def test_delete_score(self, client: AsyncClient, mongodb, admin_token):
        """Test deleting a score"""
        from tests.fixtures.data_fixtures import create_test_match
        
        # Setup
        match = create_test_match(status="INPROGRESS")
        match["home"]["scores"] = [{"_id": "score-1"}]
        match["home"]["stats"] = {"goalsFor": 1}
        await mongodb["matches"].insert_one(match)
        
        # Execute
        response = await client.delete(
            f"/matches/{match['_id']}/home/scores/score-1",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        # Assert
        assert response.status_code == 204
        
        # Verify database
        updated = await mongodb["matches"].find_one({"_id": match["_id"]})
        assert len(updated["home"]["scores"]) == 0
        assert updated["home"]["stats"]["goalsFor"] == 0

    async def test_unauthorized_create_score(self, client: AsyncClient, mongodb):
        """Test creating score without auth fails"""
        from tests.fixtures.data_fixtures import create_test_match
        
        match = create_test_match(status="INPROGRESS")
        await mongodb["matches"].insert_one(match)
        
        response = await client.post(
            f"/matches/{match['_id']}/home/scores",
            json={"matchTime": "10:30"}
        )
        
        assert response.status_code == 401
