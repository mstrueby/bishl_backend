
"""Integration tests for users API endpoints"""
import pytest
from httpx import AsyncClient
from datetime import datetime


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
        # Setup - Create existing user via API
        existing_user_data = {
            "email": "existing@test.com",
            "password": "SecurePass123!",
            "firstName": "Existing",
            "lastName": "User",
            "roles": []
        }
        await client.post(
            "/users/register",
            json=existing_user_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Execute - Try to register with same email
        duplicate_user_data = {
            "email": "existing@test.com",
            "password": "DifferentPass123!",
            "firstName": "New",
            "lastName": "User"
        }

        response = await client.post(
            "/users/register",
            json=duplicate_user_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Assert
        assert response.status_code == 409

    async def test_login_success(self, client: AsyncClient, admin_token):
        """Test successful user login"""
        # Setup - Create user via API
        user_data = {
            "email": "loginuser@test.com",
            "password": "TestPass123!",
            "firstName": "Test",
            "lastName": "User",
            "roles": ["REFEREE"]
        }
        await client.post(
            "/users/register",
            json=user_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Execute
        response = await client.post(
            "/users/login",
            json={"email": "loginuser@test.com", "password": "TestPass123!"}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["user"]["email"] == "loginuser@test.com"

    async def test_login_wrong_password(self, client: AsyncClient, admin_token):
        """Test login with wrong password fails"""
        # Setup - Create user via API
        user_data = {
            "email": "wrongpwuser@test.com",
            "password": "CorrectPassword123!",
            "firstName": "Test",
            "lastName": "User",
            "roles": []
        }
        await client.post(
            "/users/register",
            json=user_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Execute
        response = await client.post(
            "/users/login",
            json={"email": "wrongpwuser@test.com", "password": "WrongPassword"}
        )

        # Assert
        assert response.status_code == 401

    async def test_get_current_user(self, client: AsyncClient, admin_token):
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
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["firstName"] == "UpdatedName"

    async def test_update_other_user_as_admin(self, client: AsyncClient, admin_token):
        """Test admin updating another user"""
        # Setup - Create another user via API
        other_user_data = {
            "email": "otheruser@test.com",
            "password": "SecurePass123!",
            "firstName": "Other",
            "lastName": "User",
            "roles": ["REFEREE"]
        }
        create_response = await client.post(
            "/users/register",
            json=other_user_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        other_user_id = create_response.json()["user"]["_id"]

        # Execute
        response = await client.patch(
            f"/users/{other_user_id}",
            data={"firstName": "Modified"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["firstName"] == "Modified"

    async def test_get_all_referees(self, client: AsyncClient, mongodb, admin_token):
        """Test retrieving all referees"""
        # Clean up any existing test referees
        await mongodb["users"].delete_many({
            "email": {"$in": ["ref1@test.com", "ref2@test.com"]}
        })
        
        # Setup - Create referee users via API
        referee1_data = {
            "email": "ref1@test.com",
            "password": "SecurePass123!",
            "firstName": "Ref",
            "lastName": "One",
            "roles": ["REFEREE"]
        }
        referee2_data = {
            "email": "ref2@test.com",
            "password": "SecurePass123!",
            "firstName": "Ref",
            "lastName": "Two",
            "roles": ["REFEREE"]
        }
        await client.post(
            "/users/register",
            json=referee1_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        await client.post(
            "/users/register",
            json=referee2_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Execute
        response = await client.get(
            "/users/referees",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["pagination"]["total_items"] >= 2

    async def test_forgot_password(self, client: AsyncClient, admin_token):
        """Test forgot password flow"""
        # Setup - Create user via API
        user_data = {
            "email": "forgotpw@test.com",
            "password": "SecurePass123!",
            "firstName": "Test",
            "lastName": "User",
            "roles": []
        }
        await client.post(
            "/users/register",
            json=user_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Execute
        response = await client.post(
            "/users/forgot-password",
            json={"email": "forgotpw@test.com"}
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
