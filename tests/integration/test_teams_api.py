
"""Integration tests for teams API endpoints"""
import pytest
from httpx import AsyncClient
from bson import ObjectId


@pytest.mark.asyncio
class TestTeamsAPI:
    """Test teams CRUD operations"""

    async def test_create_team_success(self, client: AsyncClient, mongodb, admin_token):
        """Test creating a new team for a club"""
        # Setup - Create parent club
        club = {
            "_id": str(ObjectId()),
            "name": "Test Club",
            "alias": "test-club",
            "country": "Deutschland",
            "active": True,
            "teams": []
        }
        await mongodb["clubs"].insert_one(club)

        # Execute
        team_data = {
            "name": "1. Herren",
            "alias": "1-herren",
            "fullName": "Test Club 1. Herren",
            "shortName": "TC 1H",
            "tinyName": "TC1H",
            "ageGroup": "HERREN",
            "teamNumber": 1,
            "active": True,
            "external": False
        }

        response = await client.post(
            f"/clubs/{club['alias']}/teams",
            data=team_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Assert response
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["data"]["name"] == "1. Herren"
        assert data["data"]["alias"] == "1-herren"
        assert "created successfully" in data["message"]

        # Verify database - team added to club's teams array
        club_in_db = await mongodb["clubs"].find_one({"alias": "test-club"})
        assert len(club_in_db["teams"]) == 1
        assert club_in_db["teams"][0]["name"] == "1. Herren"

    async def test_create_team_duplicate_alias_fails(self, client: AsyncClient, mongodb, admin_token):
        """Test creating team with existing alias fails"""
        # Setup - Create club with existing team
        club = {
            "_id": str(ObjectId()),
            "name": "Test Club",
            "alias": "test-club",
            "country": "Deutschland",
            "active": True,
            "teams": [
                {
                    "_id": str(ObjectId()),
                    "name": "1. Herren",
                    "alias": "1-herren",
                    "fullName": "Test Club 1. Herren",
                    "shortName": "TC 1H",
                    "tinyName": "TC1H",
                    "ageGroup": "HERREN",
                    "teamNumber": 1,
                    "active": True,
                    "external": False,
                    "teamPartnership": []
                }
            ]
        }
        await mongodb["clubs"].insert_one(club)

        # Execute - Try to create team with same alias
        duplicate_team_data = {
            "name": "Different Team",
            "alias": "1-herren",  # Same alias
            "fullName": "Test Club Different Team",
            "shortName": "TC DT",
            "tinyName": "TCDT",
            "ageGroup": "HERREN",
            "teamNumber": 2,
            "active": True,
            "external": False
        }

        response = await client.post(
            f"/clubs/{club['alias']}/teams",
            data=duplicate_team_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Assert
        assert response.status_code == 409

    async def test_get_team_by_alias(self, client: AsyncClient, mongodb):
        """Test retrieving a team by alias"""
        # Setup
        team_id = str(ObjectId())
        club = {
            "_id": str(ObjectId()),
            "name": "Test Club",
            "alias": "test-club",
            "country": "Deutschland",
            "active": True,
            "teams": [
                {
                    "_id": team_id,
                    "name": "1. Herren",
                    "alias": "1-herren",
                    "fullName": "Test Club 1. Herren",
                    "shortName": "TC 1H",
                    "tinyName": "TC1H",
                    "ageGroup": "HERREN",
                    "teamNumber": 1,
                    "active": True,
                    "external": False,
                    "teamPartnership": []
                }
            ]
        }
        await mongodb["clubs"].insert_one(club)

        # Execute
        response = await client.get(f"/clubs/test-club/teams/1-herren")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["alias"] == "1-herren"
        assert data["data"]["name"] == "1. Herren"
        assert "retrieved successfully" in data["message"]

    async def test_get_team_not_found(self, client: AsyncClient, mongodb):
        """Test retrieving non-existent team returns 404"""
        # Setup - Create club without teams
        club = {
            "_id": str(ObjectId()),
            "name": "Test Club",
            "alias": "test-club",
            "country": "Deutschland",
            "active": True,
            "teams": []
        }
        await mongodb["clubs"].insert_one(club)

        # Execute
        response = await client.get("/clubs/test-club/teams/non-existent-team")

        # Assert
        assert response.status_code == 404
        assert "not found" in response.json()["error"]["message"].lower()

    async def test_list_teams_pagination(self, client: AsyncClient, mongodb):
        """Test listing teams with pagination"""
        # Setup - Create club with multiple teams
        teams = [
            {
                "_id": str(ObjectId()),
                "name": f"{i}. Herren",
                "alias": f"{i}-herren",
                "fullName": f"Test Club {i}. Herren",
                "shortName": f"TC {i}H",
                "tinyName": f"TC{i}H",
                "ageGroup": "HERREN",
                "teamNumber": i,
                "active": True,
                "external": False,
                "teamPartnership": []
            }
            for i in range(1, 6)
        ]
        club = {
            "_id": str(ObjectId()),
            "name": "Test Club",
            "alias": "test-club",
            "country": "Deutschland",
            "active": True,
            "teams": teams
        }
        await mongodb["clubs"].insert_one(club)

        # Execute - Get first page
        response = await client.get("/clubs/test-club/teams?page=1&page_size=3")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]) == 3
        assert data["pagination"]["page"] == 1
        assert data["pagination"]["total_items"] == 5
        assert data["pagination"]["has_next"] is True

    async def test_update_team(self, client: AsyncClient, mongodb, admin_token):
        """Test updating a team"""
        # Setup
        team_id = str(ObjectId())
        club = {
            "_id": str(ObjectId()),
            "name": "Test Club",
            "alias": "test-club",
            "country": "Deutschland",
            "active": True,
            "teams": [
                {
                    "_id": team_id,
                    "name": "1. Herren",
                    "alias": "1-herren",
                    "fullName": "Test Club 1. Herren",
                    "shortName": "TC 1H",
                    "tinyName": "TC1H",
                    "ageGroup": "HERREN",
                    "teamNumber": 1,
                    "active": True,
                    "external": False,
                    "teamPartnership": []
                }
            ]
        }
        await mongodb["clubs"].insert_one(club)

        # Execute
        response = await client.patch(
            f"/clubs/test-club/teams/{team_id}",
            data={"name": "1. Herren Updated"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["name"] == "1. Herren Updated"

        # Verify in database
        updated_club = await mongodb["clubs"].find_one({"alias": "test-club"})
        assert updated_club["teams"][0]["name"] == "1. Herren Updated"

    async def test_update_team_no_changes(self, client: AsyncClient, mongodb, admin_token):
        """Test updating team with no changes returns 200"""
        # Setup
        team_id = str(ObjectId())
        club = {
            "_id": str(ObjectId()),
            "name": "Test Club",
            "alias": "test-club",
            "country": "Deutschland",
            "active": True,
            "teams": [
                {
                    "_id": team_id,
                    "name": "1. Herren",
                    "alias": "1-herren",
                    "fullName": "Test Club 1. Herren",
                    "shortName": "TC 1H",
                    "tinyName": "TC1H",
                    "ageGroup": "HERREN",
                    "teamNumber": 1,
                    "active": True,
                    "external": False,
                    "teamPartnership": []
                }
            ]
        }
        await mongodb["clubs"].insert_one(club)

        # Execute - Update with same values
        response = await client.patch(
            f"/clubs/test-club/teams/{team_id}",
            data={"name": "1. Herren"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Assert - Should return 200, not 304
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "No changes detected" in data["message"]

    async def test_delete_team(self, client: AsyncClient, mongodb, admin_token):
        """Test deleting a team"""
        # Setup
        team_id = str(ObjectId())
        club = {
            "_id": str(ObjectId()),
            "name": "Test Club",
            "alias": "test-club",
            "country": "Deutschland",
            "active": True,
            "teams": [
                {
                    "_id": team_id,
                    "name": "1. Herren",
                    "alias": "1-herren",
                    "fullName": "Test Club 1. Herren",
                    "shortName": "TC 1H",
                    "tinyName": "TC1H",
                    "ageGroup": "HERREN",
                    "teamNumber": 1,
                    "active": True,
                    "external": False,
                    "teamPartnership": []
                }
            ]
        }
        await mongodb["clubs"].insert_one(club)

        # Execute
        response = await client.delete(
            f"/clubs/test-club/teams/{team_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Assert
        assert response.status_code == 204

        # Verify deleted from database
        updated_club = await mongodb["clubs"].find_one({"alias": "test-club"})
        assert len(updated_club["teams"]) == 0

    async def test_create_team_unauthorized(self, client: AsyncClient, mongodb):
        """Test creating team without admin token fails"""
        # Setup
        club = {
            "_id": str(ObjectId()),
            "name": "Test Club",
            "alias": "test-club",
            "country": "Deutschland",
            "active": True,
            "teams": []
        }
        await mongodb["clubs"].insert_one(club)

        team_data = {
            "name": "1. Herren",
            "alias": "1-herren",
            "fullName": "Test Club 1. Herren",
            "shortName": "TC 1H",
            "tinyName": "TC1H",
            "ageGroup": "HERREN",
            "teamNumber": 1
        }

        response = await client.post(
            f"/clubs/test-club/teams",
            data=team_data
        )

        assert response.status_code == 403
