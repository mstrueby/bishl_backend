
"""Integration tests for players API endpoints"""
import pytest
from httpx import AsyncClient
from datetime import datetime


@pytest.mark.asyncio
class TestPlayersAPI:
    """Test player CRUD operations"""

    async def test_create_player_success(self, client: AsyncClient, mongodb, admin_token):
        """Test creating a new player"""
        # Setup - Create a club and team
        club = {
            "_id": "test-club-id",
            "name": "Test Club",
            "alias": "test-club",
            "teams": [{
                "_id": "team-1",
                "name": "Team A",
                "alias": "team-a",
                "ageGroup": "U15",
                "ishdId": "123"
            }]
        }
        await mongodb["clubs"].insert_one(club)
        
        # Execute - Create player with form data
        player_data = {
            "firstName": "John",
            "lastName": "Doe",
            "birthdate": "2008-05-15",
            "displayFirstName": "John",
            "displayLastName": "Doe",
            "nationality": "deutsch",
            "position": "SKATER",
            "sex": "männlich",
            "fullFaceReq": "false",
            "managedByISHD": "false",
            "source": "BISHL"
        }
        
        response = await client.post(
            "/players",
            data=player_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        # Assert response
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["data"]["firstName"] == "John"
        assert data["data"]["lastName"] == "Doe"
        assert "_id" in data["data"]
        
        # Verify database
        player_in_db = await mongodb["players"].find_one({"_id": data["data"]["_id"]})
        assert player_in_db is not None
        assert player_in_db["firstName"] == "John"

    async def test_get_player_by_id(self, client: AsyncClient, mongodb, admin_token):
        """Test retrieving a player by ID"""
        from tests.fixtures.data_fixtures import create_test_player
        
        # Setup
        player = create_test_player("player-1")
        player["firstName"] = "Jane"
        player["lastName"] = "Smith"
        player["birthdate"] = datetime(2009, 3, 20)
        await mongodb["players"].insert_one(player)
        
        # Execute
        response = await client.get(
            f"/players/{player['_id']}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["_id"] == player["_id"]
        assert data["data"]["firstName"] == "Jane"

    async def test_get_player_not_found(self, client: AsyncClient, admin_token):
        """Test retrieving non-existent player returns 404"""
        from bson import ObjectId
        fake_id = str(ObjectId())
        
        response = await client.get(
            f"/players/{fake_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 404

    async def test_update_player(self, client: AsyncClient, mongodb, admin_token):
        """Test updating player details"""
        from tests.fixtures.data_fixtures import create_test_player
        
        # Setup
        player = create_test_player("player-1")
        player["firstName"] = "Original"
        player["birthdate"] = datetime(2008, 1, 1)
        await mongodb["players"].insert_one(player)
        
        # Execute - Update first name using form data
        response = await client.patch(
            f"/players/{player['_id']}",
            data={"firstName": "Updated"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["firstName"] == "Updated"
        
        # Verify database
        updated = await mongodb["players"].find_one({"_id": player["_id"]})
        assert updated["firstName"] == "Updated"

    async def test_delete_player(self, client: AsyncClient, mongodb, admin_token):
        """Test deleting a player"""
        from tests.fixtures.data_fixtures import create_test_player
        
        # Setup
        player = create_test_player("player-1")
        await mongodb["players"].insert_one(player)
        
        # Execute
        response = await client.delete(
            f"/players/{player['_id']}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        # Assert
        assert response.status_code == 204
        
        # Verify deleted from database
        deleted = await mongodb["players"].find_one({"_id": player["_id"]})
        assert deleted is None

    async def test_get_players_for_club(self, client: AsyncClient, mongodb, admin_token):
        """Test retrieving players for a club"""
        from tests.fixtures.data_fixtures import create_test_player
        
        # Setup
        player1 = create_test_player("player-1")
        player1["assignedTeams"] = [{
            "clubId": "club-1",
            "clubName": "Test Club",
            "clubAlias": "test-club",
            "teams": []
        }]
        player2 = create_test_player("player-2")
        player2["assignedTeams"] = [{
            "clubId": "other-club",
            "clubName": "Other Club",
            "clubAlias": "other-club",
            "teams": []
        }]
        await mongodb["players"].insert_many([player1, player2])
        
        # Execute
        response = await client.get(
            "/players/clubs/test-club",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["pagination"]["total_items"] >= 1

    async def test_get_players_for_team(self, client: AsyncClient, mongodb, admin_token):
        """Test retrieving players for a specific team"""
        from tests.fixtures.data_fixtures import create_test_player
        
        # Setup
        player = create_test_player("player-1")
        player["assignedTeams"] = [{
            "clubId": "club-1",
            "clubName": "Test Club",
            "clubAlias": "test-club",
            "teams": [{
                "teamId": "team-1",
                "teamName": "Team A",
                "teamAlias": "team-a",
                "teamAgeGroup": "U15",
                "passNo": "12345",
                "active": True
            }]
        }]
        await mongodb["players"].insert_one(player)
        
        # Execute
        response = await client.get(
            "/players/clubs/test-club/teams/team-a",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["pagination"]["total_items"] >= 1

    async def test_search_players(self, client: AsyncClient, mongodb, admin_token):
        """Test searching players by name"""
        from tests.fixtures.data_fixtures import create_test_player
        
        # Setup
        player1 = create_test_player("player-1")
        player1["firstName"] = "Michael"
        player1["lastName"] = "Jordan"
        player2 = create_test_player("player-2")
        player2["firstName"] = "LeBron"
        player2["lastName"] = "James"
        await mongodb["players"].insert_many([player1, player2])
        
        # Execute - Search for "Michael"
        response = await client.get(
            "/players?search=Michael",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["pagination"]["total_items"] >= 1
        # Should contain Michael but not LeBron
        items = data["data"]
        assert any(p["firstName"] == "Michael" for p in items)

    async def test_unauthorized_access(self, client: AsyncClient, mongodb):
        """Test accessing players without auth fails"""
        from tests.fixtures.data_fixtures import create_test_player
        
        player = create_test_player("player-1")
        await mongodb["players"].insert_one(player)
        
        response = await client.get(f"/players/{player['_id']}")
        
        assert response.status_code == 401
