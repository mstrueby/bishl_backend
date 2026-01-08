"""End-to-end tests for referee assignment workflow"""

import pytest
from bson import ObjectId
from httpx import AsyncClient


@pytest.mark.asyncio
class TestRefereeAssignmentWorkflow:
    """Test complete referee assignment workflow"""

    async def test_complete_assignment_workflow(self, client: AsyncClient, mongodb, admin_token):
        """
        Test complete assignment flow:
        1. Referee requests assignment
        2. Ref admin assigns referee to match
        3. Referee accepts assignment
        4. Match updates with referee information
        """
        from authentication import AuthHandler
        from tests.fixtures.data_fixtures import create_test_match, create_test_tournament

        # 1. Setup: Create tournament, match, and referee user
        tournament = create_test_tournament()
        tournament["seasons"][0]["standingsSettings"] = {
            "pointsWinReg": 3,
            "pointsLossReg": 0,
        }
        await mongodb["tournaments"].insert_one(tournament)

        match = create_test_match(status="SCHEDULED")
        await mongodb["matches"].insert_one(match)
        match_id = match["_id"]

        # Create referee user with complete structure
        auth = AuthHandler()
        referee_id = str(ObjectId())
        referee = {
            "_id": referee_id,
            "email": "referee@test.com",
            "password": auth.get_password_hash("password123"),
            "firstName": "John",
            "lastName": "Referee",
            "roles": ["REFEREE"],
            "referee": {
                "level": "S2",
                "points": 0,
                "club": {
                    "clubId": "club-123",
                    "clubName": "Test Referee Club",
                    "logoUrl": "http://logo.url",
                },
            },
        }
        await mongodb["users"].insert_one(referee)

        # Get referee token
        referee_token = auth.encode_token(referee)

        # 2. Referee requests assignment
        request_data = {
            "matchId": match_id,
            "status": "REQUESTED",
            "refAdmin": False,
        }

        response = await client.post(
            "/assignments",
            json=request_data,
            headers={"Authorization": f"Bearer {referee_token}"},
        )
        assert response.status_code == 201
        assignment_data = response.json()
        assert assignment_data["data"]["status"] == "REQUESTED"
        assert assignment_data["data"]["referee"]["userId"] == referee_id
        assignment_id = assignment_data["data"]["_id"]

        # Verify assignment in database
        assignment = await mongodb["assignments"].find_one({"_id": assignment_id})
        assert assignment is not None
        assert assignment["status"] == "REQUESTED"
        assert len(assignment["statusHistory"]) == 1
        assert assignment["statusHistory"][0]["status"] == "REQUESTED"

        # 3. Ref admin assigns referee to position 1
        assign_data = {
            "status": "ASSIGNED",
            "position": 1,
            "refAdmin": True,
        }

        response = await client.patch(
            f"/assignments/{assignment_id}",
            json=assign_data,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        assignment_data = response.json()
        assert assignment_data["data"]["status"] == "ASSIGNED"
        assert assignment_data["data"]["position"] == 1

        # Verify match updated with referee
        match_doc = await mongodb["matches"].find_one({"_id": match_id})
        assert match_doc["referee1"] is not None
        assert match_doc["referee1"]["userId"] == referee_id
        assert match_doc["referee1"]["firstName"] == "John"
        assert match_doc["referee1"]["lastName"] == "Referee"
        assert match_doc["referee1"]["clubId"] == "club-123"

        # Verify status history updated
        assignment = await mongodb["assignments"].find_one({"_id": assignment_id})
        assert len(assignment["statusHistory"]) == 2
        assert assignment["statusHistory"][1]["status"] == "ASSIGNED"

        # 4. Referee accepts assignment
        accept_data = {
            "status": "ACCEPTED",
            "refAdmin": False,
        }

        response = await client.patch(
            f"/assignments/{assignment_id}",
            json=accept_data,
            headers={"Authorization": f"Bearer {referee_token}"},
        )
        assert response.status_code == 200
        assignment_data = response.json()
        assert assignment_data["data"]["status"] == "ACCEPTED"

        # Verify final state
        assignment = await mongodb["assignments"].find_one({"_id": assignment_id})
        assert assignment["status"] == "ACCEPTED"
        assert len(assignment["statusHistory"]) == 3
        assert assignment["statusHistory"][2]["status"] == "ACCEPTED"

    async def test_dual_referee_assignment_workflow(
        self, client: AsyncClient, mongodb, admin_token
    ):
        """Test assigning two referees to same match"""
        from authentication import AuthHandler
        from tests.fixtures.data_fixtures import create_test_match, create_test_tournament

        # Setup
        tournament = create_test_tournament()
        await mongodb["tournaments"].insert_one(tournament)

        match = create_test_match(status="SCHEDULED")
        await mongodb["matches"].insert_one(match)
        match_id = match["_id"]

        # Create two referee users
        auth = AuthHandler()
        ref1_id = str(ObjectId())
        ref2_id = str(ObjectId())

        referee1 = {
            "_id": ref1_id,
            "email": "ref1@test.com",
            "password": auth.get_password_hash("pass"),
            "firstName": "First",
            "lastName": "Referee",
            "roles": ["REFEREE"],
            "referee": {
                "level": "S2",
                "points": 100,
                "club": {
                    "clubId": "club-1",
                    "clubName": "Club One",
                    "logoUrl": None,
                },
            },
        }

        referee2 = {
            "_id": ref2_id,
            "email": "ref2@test.com",
            "password": auth.get_password_hash("pass"),
            "firstName": "Second",
            "lastName": "Referee",
            "roles": ["REFEREE"],
            "referee": {
                "level": "S1",
                "points": 200,
                "club": {
                    "clubId": "club-2",
                    "clubName": "Club Two",
                    "logoUrl": None,
                },
            },
        }

        await mongodb["users"].insert_many([referee1, referee2])

        # Ref admin assigns first referee to position 1
        assign1_data = {
            "matchId": match_id,
            "userId": ref1_id,
            "status": "ASSIGNED",
            "position": 1,
            "refAdmin": True,
        }

        response = await client.post(
            "/assignments",
            json=assign1_data,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 201

        # Ref admin assigns second referee to position 2
        assign2_data = {
            "matchId": match_id,
            "userId": ref2_id,
            "status": "ASSIGNED",
            "position": 2,
            "refAdmin": True,
        }

        response = await client.post(
            "/assignments",
            json=assign2_data,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 201

        # Verify both referees in match
        match_doc = await mongodb["matches"].find_one({"_id": match_id})
        assert match_doc["referee1"]["userId"] == ref1_id
        assert match_doc["referee2"]["userId"] == ref2_id

        # Verify both assignments exist
        assignments = await mongodb["assignments"].find({"matchId": match_id}).to_list(None)
        assert len(assignments) == 2

    async def test_referee_unavailable_workflow(self, client: AsyncClient, mongodb):
        """Test referee marking themselves as unavailable"""
        from authentication import AuthHandler
        from tests.fixtures.data_fixtures import create_test_match, create_test_tournament

        # Setup
        tournament = create_test_tournament()
        await mongodb["tournaments"].insert_one(tournament)

        match = create_test_match(status="SCHEDULED")
        await mongodb["matches"].insert_one(match)
        match_id = match["_id"]

        # Create referee
        auth = AuthHandler()
        referee_id = str(ObjectId())
        referee = {
            "_id": referee_id,
            "email": "ref@test.com",
            "password": auth.get_password_hash("pass"),
            "firstName": "Unavail",
            "lastName": "Referee",
            "roles": ["REFEREE"],
            "referee": {
                "level": "S2",
                "points": 0,
                "club": {"clubId": None, "clubName": None, "logoUrl": None},
            },
        }
        await mongodb["users"].insert_one(referee)
        referee_token = auth.encode_token(referee)

        # Referee marks as unavailable
        unavail_data = {
            "matchId": match_id,
            "status": "UNAVAILABLE",
            "refAdmin": False,
        }

        response = await client.post(
            "/assignments",
            json=unavail_data,
            headers={"Authorization": f"Bearer {referee_token}"},
        )
        assert response.status_code == 201
        assignment_data = response.json()
        assert assignment_data["data"]["status"] == "UNAVAILABLE"

        # Verify no position assigned
        assert assignment_data["data"]["position"] is None

        # Verify match has no referee
        match_doc = await mongodb["matches"].find_one({"_id": match_id})
        assert match_doc["referee1"] is None
        assert match_doc["referee2"] is None

    async def test_assignment_deletion_workflow(self, client: AsyncClient, mongodb, admin_token):
        """Test deleting assignment removes referee from match"""
        from tests.fixtures.data_fixtures import create_test_match, create_test_tournament

        # Setup
        tournament = create_test_tournament()
        await mongodb["tournaments"].insert_one(tournament)

        match = create_test_match(status="SCHEDULED")
        await mongodb["matches"].insert_one(match)
        match_id = match["_id"]

        # Create referee user
        referee_id = str(ObjectId())
        referee_user = {
            "_id": referee_id,
            "firstName": "Delete",
            "lastName": "Test",
            "roles": ["REFEREE"],
            "referee": {
                "level": "S2",
                "club": {"clubId": None, "clubName": None, "logoUrl": None},
            },
        }
        await mongodb["users"].insert_one(referee_user)

        # Create assignment with referee in match
        assignment_id = str(ObjectId())
        assignment = {
            "_id": assignment_id,
            "matchId": match_id,
            "referee": {
                "userId": referee_id,
                "firstName": "Delete",
                "lastName": "Test",
                "clubId": None,
                "clubName": None,
                "logoUrl": None,
                "points": 0,
                "level": "S2",
            },
            "status": "ASSIGNED",
            "position": 1,
            "statusHistory": [],
        }
        await mongodb["assignments"].insert_one(assignment)

        # Set referee in match
        await mongodb["matches"].update_one(
            {"_id": match_id},
            {"$set": {"referee1": assignment["referee"]}},
        )

        # Delete assignment
        response = await client.delete(
            f"/assignments/{assignment_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 204

        # Verify assignment deleted
        deleted_assignment = await mongodb["assignments"].find_one({"_id": assignment_id})
        assert deleted_assignment is None

        # Verify referee removed from match
        match_doc = await mongodb["matches"].find_one({"_id": match_id})
        assert match_doc["referee1"] is None

    async def test_get_assignments_for_match(self, client: AsyncClient, mongodb, admin_token):
        """Test retrieving all assignments for a match"""
        from tests.fixtures.data_fixtures import create_test_match, create_test_tournament

        # Setup
        tournament = create_test_tournament()
        await mongodb["tournaments"].insert_one(tournament)

        match = create_test_match(status="SCHEDULED")
        await mongodb["matches"].insert_one(match)
        match_id = match["_id"]

        # Create referees
        ref1_id = str(ObjectId())
        ref2_id = str(ObjectId())
        ref3_id = str(ObjectId())

        referees = [
            {
                "_id": ref1_id,
                "firstName": "Ref",
                "lastName": "One",
                "roles": ["REFEREE"],
                "referee": {
                    "level": "S2",
                    "club": {"clubId": None, "clubName": None, "logoUrl": None},
                },
            },
            {
                "_id": ref2_id,
                "firstName": "Ref",
                "lastName": "Two",
                "roles": ["REFEREE"],
                "referee": {
                    "level": "S1",
                    "club": {"clubId": None, "clubName": None, "logoUrl": None},
                },
            },
            {
                "_id": ref3_id,
                "firstName": "Ref",
                "lastName": "Three",
                "roles": ["REFEREE"],
                "referee": {
                    "level": "S2",
                    "club": {"clubId": None, "clubName": None, "logoUrl": None},
                },
            },
        ]
        await mongodb["users"].insert_many(referees)

        # Create assignments
        assignments = [
            {
                "_id": str(ObjectId()),
                "matchId": match_id,
                "referee": {
                    "userId": ref1_id,
                    "firstName": "Ref",
                    "lastName": "One",
                    "clubId": None,
                    "clubName": None,
                    "logoUrl": None,
                    "points": 0,
                    "level": "S2",
                },
                "status": "REQUESTED",
                "statusHistory": [],
            },
            {
                "_id": str(ObjectId()),
                "matchId": match_id,
                "referee": {
                    "userId": ref2_id,
                    "firstName": "Ref",
                    "lastName": "Two",
                    "clubId": None,
                    "clubName": None,
                    "logoUrl": None,
                    "points": 0,
                    "level": "S1",
                },
                "status": "UNAVAILABLE",
                "statusHistory": [],
            },
        ]
        await mongodb["assignments"].insert_many(assignments)

        # Get assignments for match
        response = await client.get(
            f"/assignments/matches/{match_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()

        # Should include all referees (with and without assignments)
        assert len(data) >= 2
