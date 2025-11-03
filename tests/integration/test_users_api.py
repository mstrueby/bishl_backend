"""Integration tests for users API endpoints"""
import pytest
from httpx import AsyncClient
from datetime import datetime


# Example of using test_isolation for proper cleanup:
# @pytest.mark.asyncio
# async def test_example_with_isolation(client, test_isolation):
#     """Example showing proper test isolation"""
#     # Create test user with unique test_id
#     user_data = {
#         "email": f"test_{test_isolation.id}@example.com",
#         "firstName": "Test",
#         "lastName": "User",
#         "password": "TestPass123!"
#     }
#     
#     response = await client.post("/users/register", json=user_data)
#     assert response.status_code == 201
#     
#     # Test runs...
#     # Cleanup happens automatically via fixture


@pytest.mark.asyncio
class TestUsersAPI:
    """Test user authentication and management"""

    async def test_register_user_success(self, client: AsyncClient, mongodb, admin_token):
        """Test registering a new user as admin"""
        # Execute
        user_data = {
            "email": "newuser@test.com",
            "password": "SecurePass123!",
            "firstName": "New",
            "lastName": "User",
            "roles": ["REFEREE"]
        }

        response = await client.post(
            "/users/register",
            json=user_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Assert response
        assert response.status_code == 201
        data = response.json()
        assert "token" in data
        assert data["user"]["email"] == "newuser@test.com"
        assert "REFEREE" in data["user"]["roles"]

        # Verify database
        user_in_db = await mongodb["users"].find_one({"email": "newuser@test.com"})
        assert user_in_db is not None
        assert user_in_db["firstName"] == "New"

    async def test_register_duplicate_email_fails(self, client: AsyncClient, mongodb, admin_token):
        """Test registering user with existing email fails"""
        from bson import ObjectId

        # Setup - Create existing user
        existing_user = {
            "_id": str(ObjectId()),
            "email": "existing@test.com",
            "password": "hashed",
            "firstName": "Existing",
            "lastName": "User",
            "roles": []
        }
        await mongodb["users"].insert_one(existing_user)

        # Execute - Try to register with same email
        user_data = {
            "email": "existing@test.com",
            "password": "password",
            "firstName": "New",
            "lastName": "User"
        }

        response = await client.post(
            "/users/register",
            json=user_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Assert
        assert response.status_code == 409

    async def test_login_success(self, client: AsyncClient, mongodb):
        """Test successful user login"""
        from authentication import AuthHandler
        from bson import ObjectId

        # Setup - Create user with hashed password
        auth = AuthHandler()
        user = {
            "_id": str(ObjectId()),
            "email": "user@test.com",
            "password": auth.get_password_hash("TestPass123!"),
            "firstName": "Test",
            "lastName": "User",
            "roles": ["REFEREE"]
        }
        await mongodb["users"].insert_one(user)

        # Execute
        response = await client.post(
            "/users/login",
            json={"email": "user@test.com", "password": "TestPass123!"}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["user"]["email"] == "user@test.com"

    async def test_login_wrong_password(self, client: AsyncClient, mongodb):
        """Test login with wrong password fails"""
        from authentication import AuthHandler
        from bson import ObjectId

        # Setup
        auth = AuthHandler()
        user = {
            "_id": str(ObjectId()),
            "email": "user@test.com",
            "password": auth.get_password_hash("CorrectPassword"),
            "firstName": "Test",
            "lastName": "User",
            "roles": []
        }
        await mongodb["users"].insert_one(user)

        # Execute
        response = await client.post(
            "/users/login",
            json={"email": "user@test.com", "password": "WrongPassword"}
        )

        # Assert
        assert response.status_code == 401

    async def test_get_current_user(self, client: AsyncClient, mongodb, admin_token):
        """Test getting current user details"""
        # Execute
        response = await client.get(
            "/users/me",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "email" in data
        assert "_id" in data

    async def test_update_own_profile(self, client: AsyncClient, mongodb, admin_token):
        """Test user updating their own profile"""
        # Setup - Get current user ID from token
        from authentication import AuthHandler
        auth = AuthHandler()
        token_data = auth.decode_token(admin_token)
        user_id = token_data.sub

        # Execute
        response = await client.patch(
            f"/users/{user_id}",
            data={"firstName": "UpdatedName"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["firstName"] == "UpdatedName"

    async def test_update_other_user_as_admin(self, client: AsyncClient, mongodb, admin_token):
        """Test admin updating another user"""
        from bson import ObjectId

        # Setup - Create another user
        other_user = {
            "_id": str(ObjectId()),
            "email": "other@test.com",
            "password": "hashed",
            "firstName": "Other",
            "lastName": "User",
            "roles": ["REFEREE"]
        }
        await mongodb["users"].insert_one(other_user)

        # Execute
        response = await client.patch(
            f"/users/{other_user['_id']}",
            data={"firstName": "Modified"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["firstName"] == "Modified"

    async def test_get_all_referees(self, client: AsyncClient, mongodb, admin_token):
        """Test retrieving all referees"""
        from bson import ObjectId

        # Setup - Create referee users
        referee1 = {
            "_id": str(ObjectId()),
            "email": "ref1@test.com",
            "password": "hashed",
            "firstName": "Ref",
            "lastName": "One",
            "roles": ["REFEREE"]
        }
        referee2 = {
            "_id": str(ObjectId()),
            "email": "ref2@test.com",
            "password": "hashed",
            "firstName": "Ref",
            "lastName": "Two",
            "roles": ["REFEREE"]
        }
        await mongodb["users"].insert_many([referee1, referee2])

        # Execute
        response = await client.get(
            "/users/referees",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["pagination"]["total_items"] >= 2

    async def test_forgot_password(self, client: AsyncClient, mongodb):
        """Test forgot password flow"""
        from bson import ObjectId

        # Setup
        user = {
            "_id": str(ObjectId()),
            "email": "user@test.com",
            "password": "hashed",
            "firstName": "Test",
            "lastName": "User",
            "roles": []
        }
        await mongodb["users"].insert_one(user)

        # Execute
        response = await client.post(
            "/users/forgot-password",
            json={"email": "user@test.com"}
        )

        # Assert
        assert response.status_code == 200
        assert "Password reset instructions sent to your email" in response.json()["message"]

    async def test_unauthorized_register(self, client: AsyncClient):
        """Test registering without admin token fails"""
        user_data = {
            "email": "newuser@test.com",
            "password": "password",
            "firstName": "New",
            "lastName": "User"
        }

        response = await client.post("/users/register", json=user_data)

        assert response.status_code == 403