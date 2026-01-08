"""Integration tests for users API endpoints"""

import pytest
from httpx import AsyncClient

from tests.fixtures.data_fixtures import create_test_user


@pytest.mark.asyncio
class TestUsersAPI:
    """Test user authentication and management"""

    async def test_register_user_success(self, client: AsyncClient, mongodb, admin_token):
        """Test registering a new user as admin"""
        # Execute
        user_data = {
            "email": "newuser@bishl.de",
            "password": "SecurePass123!",
            "firstName": "New",
            "lastName": "User",
            "roles": ["REFEREE"],
        }

        response = await client.post(
            "/users/register", json=user_data, headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Assert response
        assert response.status_code == 201
        data = response.json()
        assert "token" in data
        assert data["data"]["email"] == "newuser@bishl.de"
        assert "REFEREE" in data["data"]["roles"]

        # Verify database
        user_in_db = await mongodb["users"].find_one({"email": "newuser@bishl.de"})
        assert user_in_db is not None
        assert user_in_db["firstName"] == "New"

    async def test_register_duplicate_email_fails(self, client: AsyncClient, mongodb, admin_token):
        """Test registering user with existing email fails"""
        # Setup - Create existing user directly in DB
        existing_user = create_test_user(
            email="existing@bishl.de",
            password="SecurePass123!",
            firstName="Existing",
            lastName="User",
            roles=[],
        )
        await mongodb["users"].insert_one(existing_user)

        # Execute - Try to register with same email
        duplicate_user_data = {
            "email": "existing@bishl.de",
            "password": "DifferentPass123!",
            "firstName": "New",
            "lastName": "User",
            "roles": [],
        }

        response = await client.post(
            "/users/register",
            json=duplicate_user_data,
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        # Assert
        assert response.status_code == 409

    async def test_login_success(self, client: AsyncClient, mongodb):
        """Test successful user login"""
        # Setup - Create user directly in DB
        user = create_test_user(
            email="loginuser@bishl.de",
            password="TestPass123!",
            roles=["REFEREE"],
            firstName="Test",
            lastName="User",
        )
        await mongodb["users"].insert_one(user)

        # Execute - Test login endpoint
        response = await client.post(
            "/users/login", json={"email": "loginuser@bishl.de", "password": "TestPass123!"}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["data"]["email"] == "loginuser@bishl.de"

    async def test_login_wrong_password(self, client: AsyncClient, mongodb):
        """Test login with wrong password fails"""
        # Setup - Create user directly in DB
        user = create_test_user(
            email="wrongpwuser@bishl.de",
            password="CorrectPassword123!",
            roles=[],
            firstName="Test",
            lastName="User",
        )
        await mongodb["users"].insert_one(user)

        # Execute - Test login with wrong password
        response = await client.post(
            "/users/login", json={"email": "wrongpwuser@bishl.de", "password": "WrongPassword"}
        )

        # Assert
        assert response.status_code == 401

    async def test_get_current_user(self, client: AsyncClient, admin_token):
        """Test getting current user details"""
        # Execute
        response = await client.get("/users/me", headers={"Authorization": f"Bearer {admin_token}"})

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "email" in data["data"]
        assert "_id" in data["data"]

    async def test_update_own_profile(self, client: AsyncClient, admin_token):
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
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["firstName"] == "UpdatedName"

    async def test_update_other_user_as_admin(self, client: AsyncClient, mongodb, admin_token):
        """Test admin updating another user"""
        # Setup - Create another user directly in DB
        other_user = create_test_user(
            email="otheruser@bishl.de",
            password="SecurePass123!",
            firstName="Other",
            lastName="User",
            roles=["REFEREE"],
        )
        await mongodb["users"].insert_one(other_user)
        other_user_id = other_user["_id"]

        # Execute
        response = await client.patch(
            f"/users/{other_user_id}",
            data={"firstName": "Modified"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["firstName"] == "Modified"

    async def test_get_all_referees(self, client: AsyncClient, mongodb, admin_token):
        """Test retrieving all referees"""
        # Clean up any existing test referees
        await mongodb["users"].delete_many({"email": {"$in": ["ref1@bishl.de", "ref2@bishl.de"]}})

        # Setup - Create referee users directly in DB
        ref1 = create_test_user(
            email="ref1@bishl.de",
            password="SecurePass123!",
            firstName="Ref",
            lastName="One",
            roles=["REFEREE"],
        )
        ref2 = create_test_user(
            email="ref2@bishl.de",
            password="SecurePass123!",
            firstName="Ref",
            lastName="Two",
            roles=["REFEREE"],
        )
        await mongodb["users"].insert_many([ref1, ref2])

        # Execute
        response = await client.get(
            "/users/referees", headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["pagination"]["total_items"] >= 2

    async def test_forgot_password(self, client: AsyncClient, mongodb, admin_token):
        """Test forgot password flow"""
        # Setup - Create user directly in DB
        user = create_test_user(
            email="forgotpw@bishl.de",
            password="SecurePass123!",
            firstName="Test",
            lastName="User",
            roles=[],
        )
        await mongodb["users"].insert_one(user)

        # Execute
        response = await client.post("/users/forgot-password", json={"email": "forgotpw@bishl.de"})

        # Assert
        assert response.status_code == 200
        # Check for message snippet that works in test environment
        assert "sent" in response.json()["message"]

    async def test_unauthorized_register(self, client: AsyncClient):
        """Test registering without admin token fails"""
        user_data = {
            "email": "newuser@bishl.de",
            "password": "password",
            "firstName": "New",
            "lastName": "User",
            "roles": [],
        }

        response = await client.post("/users/register", json=user_data)

        assert response.status_code == 403
