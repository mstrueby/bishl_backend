"""Integration tests for assignments API endpoints"""
import pytest
from httpx import AsyncClient
from bson import ObjectId
from tests.fixtures.data_fixtures import get_test_assignment_data, create_test_match
from authentication import AuthHandler


class TestAssignmentsAPI:
    """Test referee assignment operations"""

    @pytest.mark.asyncio
    async def test_create_assignment_as_referee(self, client: AsyncClient, mongodb):
        """Test referee requesting assignment"""
        # Setup - Create referee user and match
        auth = AuthHandler()
        referee = {
            "_id": "ref-user-1",
            "email": "ref@test.com",
            "password": auth.get_password_hash("password"),
            "firstName": "John",
            "lastName": "Referee",
            "roles": ["REFEREE"],
            "referee": {"level": "S2", "points": 0}
        }
        await mongodb["users"].insert_one(referee)

        match = create_test_match()
        await mongodb["matches"].insert_one(match)

        # Get referee token
        ref_token = auth.encode_token(referee)

        # Execute
        assignment_data = {
            "matchId": match["_id"],
            "status": "REQUESTED",
            "refAdmin": False
        }

        response = await client.post(
            "/assignments",
            json=assignment_data,
            headers={"Authorization": f"Bearer {ref_token}"}
        )

        # Assert response
        assert response.status_code == 201
        data = response.json()
        assert data["data"]["matchId"] == match["_id"]
        assert data["data"]["status"] == "REQUESTED"
        assert data["data"]["referee"]["userId"] == referee["_id"]

        # Verify database
        assignment = await mongodb["assignments"].find_one({"matchId": match["_id"]})
        assert assignment is not None

    @pytest.mark.asyncio
    async def test_create_assignment_as_ref_admin(self, client: AsyncClient, mongodb, admin_token):
        """Test ref admin assigning referee to match"""
        # Setup - Create referee and match
        referee = {
            "_id": "ref-user-1",
            "email": "ref@test.com",
            "password": "hashed",
            "firstName": "John",
            "lastName": "Referee",
            "roles": ["REFEREE"],
            "referee": {"level": "S2", "points": 0}
        }
        await mongodb["users"].insert_one(referee)

        match = create_test_match(status="SCHEDULED")
        await mongodb["matches"].insert_one(match)

        # Execute
        assignment_data = {
            "matchId": match["_id"],
            "userId": referee["_id"],
            "status": "ASSIGNED",
            "position": 1,
            "refAdmin": True
        }

        response = await client.post(
            "/assignments",
            json=assignment_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Assert response
        assert response.status_code == 201
        data = response.json()
        assert data["data"]["status"] == "ASSIGNED"
        assert data["data"]["position"] == 1

        # Verify match updated with referee
        updated_match = await mongodb["matches"].find_one({"_id": match["_id"]})
        assert updated_match["referee1"]["userId"] == referee["_id"]

    @pytest.mark.asyncio
    async def test_get_assignments_for_match(self, client: AsyncClient, mongodb, admin_token):
        """Test retrieving all assignments for a match"""
        # Setup
        match = create_test_match()
        await mongodb["matches"].insert_one(match)

        # Create multiple referees
        referee1 = {
            "_id": "ref-1",
            "firstName": "Ref",
            "lastName": "One",
            "roles": ["REFEREE"],
            "referee": {"level": "S2"}
        }
        referee2 = {
            "_id": "ref-2",
            "firstName": "Ref",
            "lastName": "Two",
            "roles": ["REFEREE"],
            "referee": {"level": "S1"}
        }
        await mongodb["users"].insert_many([referee1, referee2])

        # Create assignment
        assignment = {
            "_id": str(ObjectId()),
            "matchId": match["_id"],
            "referee": {
                "userId": "ref-1",
                "firstName": "Ref",
                "lastName": "One",
                "clubId": None,
                "clubName": None,
                "logoUrl": None,
                "points": 0,
                "level": "S2"
            },
            "status": "REQUESTED",
            "statusHistory": []
        }
        await mongodb["assignments"].insert_one(assignment)

        # Execute
        response = await client.get(
            f"/assignments/matches/{match['_id']}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 2  # All referees listed

    @pytest.mark.asyncio
    async def test_get_assignments_for_user(self, client, admin_token, mongodb):
        """Test getting assignments for a specific user."""
        # Create a test assignment with proper ObjectIds
        assignment_data = get_test_assignment_data()

        # Create matching referee user
        referee_id = ObjectId(assignment_data["refereeId"])
        await mongodb["users"].insert_one({
            "_id": str(referee_id),
            "email": "referee@test.com",
            "firstName": "Test",
            "lastName": "Referee",
            "roles": ["REFEREE"]
        })

        # Create matching match
        match_id = ObjectId(assignment_data["matchId"])
        await mongodb["matches"].insert_one({
            "_id": str(match_id),
            "homeTeam": {"name": "Home Team"},
            "awayTeam": {"name": "Away Team"},
            "status": "scheduled",
            "date": assignment_data["matchDate"]
        })

        await mongodb["assignments"].insert_one(assignment_data)

        # Get assignments for the referee
        response = await client.get(
            f"/assignments/users/{assignment_data['refereeId']}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_update_assignment_status(self, client: AsyncClient, mongodb, admin_token):
        """Test updating assignment status"""
        # Setup
        referee = {
            "_id": "ref-user-1",
            "firstName": "John",
            "lastName": "Referee",
            "roles": ["REFEREE"]
        }
        await mongodb["users"].insert_one(referee)

        match = create_test_match()
        await mongodb["matches"].insert_one(match)

        assignment = {
            "_id": str(ObjectId()),
            "matchId": match["_id"],
            "referee": {
                "userId": referee["_id"],
                "firstName": "John",
                "lastName": "Referee",
                "clubId": None,
                "clubName": None,
                "logoUrl": None,
                "points": 0,
                "level": "S2"
            },
            "status": "REQUESTED",
            "statusHistory": []
        }
        await mongodb["assignments"].insert_one(assignment)

        # Execute - Ref admin assigns referee
        response = await client.patch(
            f"/assignments/{assignment['_id']}",
            json={
                "status": "ASSIGNED",
                "position": 1,
                "refAdmin": True
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["status"] == "ASSIGNED"
        assert data["data"]["position"] == 1

    @pytest.mark.asyncio
    async def test_referee_accept_assignment(self, client: AsyncClient, mongodb):
        """Test referee accepting their assignment"""
        # Setup
        auth = AuthHandler()
        referee = {
            "_id": "ref-user-1",
            "email": "ref@test.com",
            "password": auth.get_password_hash("password"),
            "firstName": "John",
            "lastName": "Referee",
            "roles": ["REFEREE"]
        }
        await mongodb["users"].insert_one(referee)

        match = create_test_match()
        await mongodb["matches"].insert_one(match)

        assignment = {
            "_id": str(ObjectId()),
            "matchId": match["_id"],
            "referee": {
                "userId": referee["_id"],
                "firstName": "John",
                "lastName": "Referee",
                "clubId": None,
                "clubName": None,
                "logoUrl": None,
                "points": 0,
                "level": "S2"
            },
            "status": "ASSIGNED",
            "position": 1,
            "statusHistory": []
        }
        await mongodb["assignments"].insert_one(assignment)

        ref_token = auth.encode_token(referee)

        # Execute
        response = await client.patch(
            f"/assignments/{assignment['_id']}",
            json={"status": "ACCEPTED", "refAdmin": False},
            headers={"Authorization": f"Bearer {ref_token}"}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["status"] == "ACCEPTED"

    @pytest.mark.asyncio
    async def test_delete_assignment(self, client: AsyncClient, mongodb, admin_token):
        """Test deleting an assignment"""
        # Setup
        match = create_test_match()
        match["referee1"] = {
            "userId": "ref-1",
            "firstName": "John",
            "lastName": "Referee"
        }
        await mongodb["matches"].insert_one(match)

        assignment = {
            "_id": str(ObjectId()),
            "matchId": match["_id"],
            "referee": {
                "userId": "ref-1",
                "firstName": "John",
                "lastName": "Referee",
                "clubId": None,
                "clubName": None,
                "logoUrl": None,
                "points": 0,
                "level": "S2"
            },
            "status": "ASSIGNED",
            "position": 1,
            "statusHistory": []
        }
        await mongodb["assignments"].insert_one(assignment)

        # Execute
        response = await client.delete(
            f"/assignments/{assignment['_id']}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Assert
        assert response.status_code == 204

        # Verify deleted from database
        deleted = await mongodb["assignments"].find_one({"_id": assignment["_id"]})
        assert deleted is None

        # Verify match referee cleared
        updated_match = await mongodb["matches"].find_one({"_id": match["_id"]})
        assert updated_match["referee1"] is None

    @pytest.mark.asyncio
    async def test_unauthorized_assignment_creation(self, client: AsyncClient, mongodb):
        """Test creating assignment without auth fails"""
        match = create_test_match()
        await mongodb["matches"].insert_one(match)

        assignment_data = {
            "matchId": match["_id"],
            "status": "REQUESTED"
        }

        response = await client.post("/assignments", json=assignment_data)

        assert response.status_code == 403