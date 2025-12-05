
"""Integration tests for clubs API endpoints"""
import pytest
from httpx import AsyncClient
from bson import ObjectId


@pytest.mark.asyncio
class TestClubsAPI:
    """Test clubs CRUD operations"""

    async def test_create_club_success(self, client: AsyncClient, mongodb, admin_token):
        """Test creating a new club"""
        # Execute
        club_data = {
            "name": "Test Hockey Club",
            "alias": "test-hockey-club",
            "country": "Deutschland",
            "city": "Berlin",
            "active": True
        }

        response = await client.post(
            "/clubs",
            data=club_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Assert response
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["data"]["name"] == "Test Hockey Club"
        assert data["data"]["alias"] == "test-hockey-club"
        assert "created successfully" in data["message"]

        # Verify database
        club_in_db = await mongodb["clubs"].find_one({"alias": "test-hockey-club"})
        assert club_in_db is not None
        assert club_in_db["name"] == "Test Hockey Club"

    async def test_create_club_duplicate_alias_fails(self, client: AsyncClient, mongodb, admin_token):
        """Test creating club with existing alias fails"""
        # Setup - Create existing club
        existing_club = {
            "name": "Existing Club",
            "alias": "existing-club",
            "country": "Deutschland",
            "active": True
        }
        await mongodb["clubs"].insert_one(existing_club)

        # Execute - Try to create with same alias
        duplicate_club_data = {
            "name": "Different Club",
            "alias": "existing-club",
            "country": "Deutschland"
        }

        response = await client.post(
            "/clubs",
            data=duplicate_club_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Assert
        assert response.status_code == 500
        assert "error" in response.json()

    async def test_get_club_by_alias(self, client: AsyncClient, mongodb):
        """Test retrieving a club by alias"""
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

        # Execute
        response = await client.get(f"/clubs/{club['alias']}")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["alias"] == "test-club"
        assert data["data"]["name"] == "Test Club"
        assert "retrieved successfully" in data["message"]

    async def test_get_club_not_found(self, client: AsyncClient):
        """Test retrieving non-existent club returns 404"""
        response = await client.get("/clubs/non-existent-club")

        assert response.status_code == 404
        assert "not found" in response.json()["error"]["message"].lower()

    async def test_list_clubs_pagination(self, client: AsyncClient, mongodb):
        """Test listing clubs with pagination"""
        # Setup - Insert multiple clubs
        clubs = [
            {
                "_id": str(ObjectId()),
                "name": f"Club {i}",
                "alias": f"club-{i}",
                "country": "Deutschland",
                "active": True,
                "teams": []
            }
            for i in range(5)
        ]
        await mongodb["clubs"].insert_many(clubs)

        # Execute - Get first page
        response = await client.get("/clubs?page=1&page_size=3")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]) == 3
        assert data["pagination"]["page"] == 1
        assert data["pagination"]["total_items"] >= 5
        assert data["pagination"]["has_next"] is True

    async def test_list_clubs_filter_active(self, client: AsyncClient, mongodb):
        """Test filtering clubs by active status"""
        # Setup - Create active and inactive clubs
        await mongodb["clubs"].delete_many({})  # Clean slate
        active_club = {
            "_id": str(ObjectId()),
            "name": "Active Club",
            "alias": "active-club",
            "country": "Deutschland",
            "active": True,
            "teams": []
        }
        inactive_club = {
            "_id": str(ObjectId()),
            "name": "Inactive Club",
            "alias": "inactive-club",
            "country": "Deutschland",
            "active": False,
            "teams": []
        }
        await mongodb["clubs"].insert_many([active_club, inactive_club])

        # Execute
        response = await client.get("/clubs?active=true")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert all(club["active"] is True for club in data["data"])

    async def test_update_club(self, client: AsyncClient, mongodb, admin_token):
        """Test updating a club"""
        # Setup
        club = {
            "_id": str(ObjectId()),
            "name": "Original Name",
            "alias": "test-club",
            "country": "Deutschland",
            "active": True,
            "teams": []
        }
        await mongodb["clubs"].insert_one(club)

        # Execute
        response = await client.patch(
            f"/clubs/{club['_id']}",
            data={"name": "Updated Name"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["name"] == "Updated Name"
        assert "updated successfully" in data["message"]

        # Verify in database
        updated = await mongodb["clubs"].find_one({"_id": club["_id"]})
        assert updated["name"] == "Updated Name"

    async def test_update_club_no_changes(self, client: AsyncClient, mongodb, admin_token):
        """Test updating club with no changes returns 200"""
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

        # Execute - Update with same values
        response = await client.patch(
            f"/clubs/{club['_id']}",
            data={"name": "Test Club"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Assert - Should return 200, not 304
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "No changes detected" in data["message"]

    async def test_delete_club(self, client: AsyncClient, mongodb, admin_token):
        """Test deleting a club"""
        # Setup
        club = {
            "_id": str(ObjectId()),
            "name": "Club to Delete",
            "alias": "delete-club",
            "country": "Deutschland",
            "active": True,
            "teams": []
        }
        await mongodb["clubs"].insert_one(club)

        # Execute
        response = await client.delete(
            f"/clubs/{club['_id']}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Assert
        assert response.status_code == 204

        # Verify deleted from database
        deleted = await mongodb["clubs"].find_one({"_id": club["_id"]})
        assert deleted is None

    async def test_create_club_unauthorized(self, client: AsyncClient):
        """Test creating club without admin token fails"""
        club_data = {
            "name": "Test Club",
            "alias": "test-club",
            "country": "Deutschland"
        }

        response = await client.post("/clubs", data=club_data)

        assert response.status_code == 403
