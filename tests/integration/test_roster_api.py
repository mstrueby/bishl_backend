"""Integration tests for roster API endpoints"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestRosterAPI:
    """Test roster management operations"""

    async def test_get_roster_returns_full_roster_object(self, client: AsyncClient, mongodb):
        """Test GET endpoint returns complete Roster object with all fields"""
        from tests.fixtures.data_fixtures import create_test_match, create_test_roster_player

        match = create_test_match()
        match["home"]["roster"] = {
            "players": [
                create_test_roster_player("player-1"),
                create_test_roster_player("player-2"),
            ],
            "status": "DRAFT",
            "published": False,
            "eligibilityTimestamp": None,
            "eligibilityValidator": None,
            "coach": {"firstName": "Coach", "lastName": "Test"},
            "staff": [],
        }
        await mongodb["matches"].insert_one(match)

        response = await client.get(f"/matches/{match['_id']}/home/roster")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "players" in data["data"]
        assert "status" in data["data"]
        assert "published" in data["data"]
        assert "coach" in data["data"]
        assert len(data["data"]["players"]) == 2
        assert data["data"]["status"] == "DRAFT"

    async def test_get_roster_players_endpoint(self, client: AsyncClient, mongodb):
        """Test GET /roster/players returns only player list"""
        from tests.fixtures.data_fixtures import create_test_match, create_test_roster_player

        match = create_test_match()
        match["home"]["roster"] = {
            "players": [create_test_roster_player("player-1")],
            "status": "SUBMITTED",
            "published": True,
        }
        await mongodb["matches"].insert_one(match)

        response = await client.get(f"/matches/{match['_id']}/home/roster/players")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)
        assert len(data["data"]) == 1

    async def test_put_roster_updates_players(self, client: AsyncClient, mongodb, admin_token):
        """Test PUT endpoint updates roster players"""
        from tests.fixtures.data_fixtures import create_test_match, create_test_player

        match = create_test_match(status="SCHEDULED")
        match["home"]["roster"] = {"players": [], "status": "DRAFT", "published": False}
        player1 = create_test_player("player-1")
        player2 = create_test_player("player-2")
        await mongodb["matches"].insert_one(match)
        await mongodb["players"].insert_one(player1)
        await mongodb["players"].insert_one(player2)

        roster_update = {
            "players": [
                {
                    "player": {
                        "playerId": player1["_id"],
                        "firstName": player1["firstName"],
                        "lastName": player1["lastName"],
                        "jerseyNumber": 10,
                    },
                    "playerPosition": {"key": "FW", "value": "Forward"},
                    "passNumber": "PASS-1234",
                },
                {
                    "player": {
                        "playerId": player2["_id"],
                        "firstName": player2["firstName"],
                        "lastName": player2["lastName"],
                        "jerseyNumber": 20,
                    },
                    "playerPosition": {"key": "DF", "value": "Defense"},
                    "passNumber": "PASS-5678",
                },
            ]
        }

        response = await client.put(
            f"/matches/{match['_id']}/home/roster",
            json=roster_update,
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]["players"]) == 2
        assert data["data"]["players"][0]["player"]["jerseyNumber"] == 10

        updated = await mongodb["matches"].find_one({"_id": match["_id"]})
        assert len(updated["home"]["roster"]["players"]) == 2

    async def test_put_roster_updates_status(self, client: AsyncClient, mongodb, admin_token):
        """Test PUT endpoint can update roster status"""
        from tests.fixtures.data_fixtures import create_test_match

        match = create_test_match(status="SCHEDULED")
        match["home"]["roster"] = {"players": [], "status": "DRAFT", "published": False}
        await mongodb["matches"].insert_one(match)

        roster_update = {"status": "SUBMITTED"}

        response = await client.put(
            f"/matches/{match['_id']}/home/roster",
            json=roster_update,
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["status"] == "SUBMITTED"

        updated = await mongodb["matches"].find_one({"_id": match["_id"]})
        assert updated["home"]["roster"]["status"] == "SUBMITTED"

    async def test_put_roster_status_invalid_transition_fails(
        self, client: AsyncClient, mongodb, admin_token
    ):
        """Test invalid status transition fails validation"""
        from tests.fixtures.data_fixtures import create_test_match

        match = create_test_match(status="SCHEDULED")
        match["home"]["roster"] = {"players": [], "status": "DRAFT", "published": False}
        await mongodb["matches"].insert_one(match)

        roster_update = {"status": "APPROVED"}

        response = await client.put(
            f"/matches/{match['_id']}/home/roster",
            json=roster_update,
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 400
        data = response.json()
        assert "transition" in data["error"]["message"].lower() or "cannot" in data["error"]["message"].lower()

    async def test_put_roster_with_duplicate_player_fails(
        self, client: AsyncClient, mongodb, admin_token
    ):
        """Test PUT fails when same player appears twice in roster"""
        from tests.fixtures.data_fixtures import create_test_match, create_test_player

        match = create_test_match(status="SCHEDULED")
        match["home"]["roster"] = {"players": [], "status": "DRAFT", "published": False}
        player = create_test_player("player-1")
        await mongodb["matches"].insert_one(match)
        await mongodb["players"].insert_one(player)

        roster_update = {
            "players": [
                {
                    "player": {
                        "playerId": player["_id"],
                        "firstName": player["firstName"],
                        "lastName": player["lastName"],
                        "jerseyNumber": 10,
                    },
                    "playerPosition": {"key": "FW", "value": "Forward"},
                    "passNumber": "PASS-1234",
                },
                {
                    "player": {
                        "playerId": player["_id"],
                        "firstName": player["firstName"],
                        "lastName": player["lastName"],
                        "jerseyNumber": 20,
                    },
                    "playerPosition": {"key": "DF", "value": "Defense"},
                    "passNumber": "PASS-5678",
                },
            ]
        }

        response = await client.put(
            f"/matches/{match['_id']}/home/roster",
            json=roster_update,
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 400

    async def test_put_roster_unchanged_returns_200(
        self, client: AsyncClient, mongodb, admin_token
    ):
        """Test PUT with identical roster returns 200 with unchanged message"""
        from tests.fixtures.data_fixtures import create_test_match

        match = create_test_match(status="SCHEDULED")
        match["home"]["roster"] = {"players": [], "status": "DRAFT", "published": False}
        await mongodb["matches"].insert_one(match)

        roster_update = {"published": False}

        await client.put(
            f"/matches/{match['_id']}/home/roster",
            json=roster_update,
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        response = await client.put(
            f"/matches/{match['_id']}/home/roster",
            json=roster_update,
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "unchanged" in data["message"].lower() or "identical" in data["message"].lower()

    async def test_put_roster_cannot_remove_player_with_stats(
        self, client: AsyncClient, mongodb, admin_token
    ):
        """Test PUT fails when trying to remove player who has goals"""
        from tests.fixtures.data_fixtures import (
            create_test_match,
            create_test_player,
            create_test_roster_player,
        )

        match = create_test_match(status="INPROGRESS")
        player_with_stats = create_test_roster_player("player-1")
        player_with_stats["goals"] = 2
        match["home"]["roster"] = {
            "players": [player_with_stats],
            "status": "DRAFT",
            "published": False,
        }
        match["home"]["scores"] = [
            {
                "_id": "score1",
                "goalPlayer": {
                    "playerId": "player-1",
                    "firstName": "Test",
                    "lastName": "Player",
                    "jerseyNumber": 10,
                },
            }
        ]

        new_player = create_test_player("player-2")
        await mongodb["matches"].insert_one(match)
        await mongodb["players"].insert_one(new_player)

        roster_update = {
            "players": [
                {
                    "player": {
                        "playerId": new_player["_id"],
                        "firstName": new_player["firstName"],
                        "lastName": new_player["lastName"],
                        "jerseyNumber": 20,
                    },
                    "playerPosition": {"key": "FW", "value": "Forward"},
                    "passNumber": "PASS-2222",
                }
            ]
        }

        response = await client.put(
            f"/matches/{match['_id']}/home/roster",
            json=roster_update,
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 400
        data = response.json()
        assert (
            "scores" in data["error"]["message"].lower()
            or "roster" in data["error"]["message"].lower()
        )

    async def test_put_roster_updates_coach_and_staff(
        self, client: AsyncClient, mongodb, admin_token
    ):
        """Test PUT can update coach and staff in single call"""
        from tests.fixtures.data_fixtures import create_test_match

        match = create_test_match(status="SCHEDULED")
        match["home"]["roster"] = {"players": [], "status": "DRAFT", "published": False}
        await mongodb["matches"].insert_one(match)

        roster_update = {
            "coach": {"firstName": "John", "lastName": "Coach", "licence": "COACH-123"},
            "staff": [{"firstName": "Staff", "lastName": "Member", "role": "Assistant"}],
        }

        response = await client.put(
            f"/matches/{match['_id']}/home/roster",
            json=roster_update,
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["coach"]["firstName"] == "John"
        assert len(data["data"]["staff"]) == 1
        assert data["data"]["staff"][0]["role"] == "Assistant"

    async def test_put_roster_atomic_update(self, client: AsyncClient, mongodb, admin_token):
        """Test PUT updates multiple fields atomically"""
        from tests.fixtures.data_fixtures import create_test_match, create_test_player

        match = create_test_match(status="SCHEDULED")
        match["home"]["roster"] = {"players": [], "status": "DRAFT", "published": False}
        player = create_test_player("player-1")
        await mongodb["matches"].insert_one(match)
        await mongodb["players"].insert_one(player)

        roster_update = {
            "players": [
                {
                    "player": {
                        "playerId": player["_id"],
                        "firstName": player["firstName"],
                        "lastName": player["lastName"],
                        "jerseyNumber": 10,
                    },
                    "playerPosition": {"key": "FW", "value": "Forward"},
                    "passNumber": "PASS-1234",
                }
            ],
            "status": "SUBMITTED",
            "published": True,
            "coach": {"firstName": "Coach", "lastName": "Name"},
        }

        response = await client.put(
            f"/matches/{match['_id']}/home/roster",
            json=roster_update,
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]["players"]) == 1
        assert data["data"]["status"] == "SUBMITTED"
        assert data["data"]["published"] is True
        assert data["data"]["coach"]["firstName"] == "Coach"

    async def test_put_roster_propagates_jersey_numbers(
        self, client: AsyncClient, mongodb, admin_token
    ):
        """Test that updating roster jersey numbers propagates to scores and penalties"""
        from tests.fixtures.data_fixtures import create_test_match, create_test_player

        match = create_test_match(status="INPROGRESS")
        player = create_test_player("player-1")
        match["home"]["roster"] = {
            "players": [
                {
                    "player": {
                        "playerId": player["_id"],
                        "firstName": player["firstName"],
                        "lastName": player["lastName"],
                        "jerseyNumber": 10,
                    },
                    "playerPosition": {"key": "FW", "value": "Forward"},
                    "passNumber": "PASS-1234",
                }
            ],
            "status": "DRAFT",
            "published": False,
        }
        match["home"]["scores"] = [
            {
                "_id": "s1",
                "matchTime": "10:00",
                "goalPlayer": {
                    "playerId": player["_id"],
                    "firstName": player["firstName"],
                    "lastName": player["lastName"],
                    "jerseyNumber": 10,
                },
            }
        ]
        match["home"]["penalties"] = [
            {
                "_id": "p1",
                "matchTimeStart": "15:00",
                "penaltyPlayer": {
                    "playerId": player["_id"],
                    "firstName": player["firstName"],
                    "lastName": player["lastName"],
                    "jerseyNumber": 10,
                },
                "penaltyCode": {"key": "MIN2", "value": "2 Minutes"},
                "penaltyMinutes": 2,
            }
        ]
        await mongodb["matches"].insert_one(match)
        await mongodb["players"].insert_one(player)

        roster_update = {
            "players": [
                {
                    "player": {
                        "playerId": player["_id"],
                        "firstName": player["firstName"],
                        "lastName": player["lastName"],
                        "jerseyNumber": 99,
                    },
                    "playerPosition": {"key": "FW", "value": "Forward"},
                    "passNumber": "PASS-1234",
                }
            ]
        }

        response = await client.put(
            f"/matches/{match['_id']}/home/roster",
            json=roster_update,
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200

        updated = await mongodb["matches"].find_one({"_id": match["_id"]})
        assert updated["home"]["roster"]["players"][0]["player"]["jerseyNumber"] == 99
        assert updated["home"]["scores"][0]["goalPlayer"]["jerseyNumber"] == 99
        assert updated["home"]["penalties"][0]["penaltyPlayer"]["jerseyNumber"] == 99

    async def test_put_roster_requires_authentication(self, client: AsyncClient, mongodb):
        """Test PUT roster requires valid admin token"""
        from tests.fixtures.data_fixtures import create_test_match

        match = create_test_match(status="SCHEDULED")
        match["home"]["roster"] = {"players": [], "status": "DRAFT", "published": False}
        await mongodb["matches"].insert_one(match)

        roster_update = {"published": True}

        response = await client.put(f"/matches/{match['_id']}/home/roster", json=roster_update)

        assert response.status_code in [401, 403]

    async def test_put_empty_roster_clears_players(self, client: AsyncClient, mongodb, admin_token):
        """Test PUT with empty players list clears the roster (if no scores/penalties exist)"""
        from tests.fixtures.data_fixtures import create_test_match, create_test_roster_player

        match = create_test_match(status="SCHEDULED")
        match["home"]["roster"] = {
            "players": [
                create_test_roster_player("player-1"),
                create_test_roster_player("player-2"),
            ],
            "status": "DRAFT",
            "published": False,
        }
        await mongodb["matches"].insert_one(match)

        roster_update = {"players": []}

        response = await client.put(
            f"/matches/{match['_id']}/home/roster",
            json=roster_update,
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]["players"]) == 0

        updated = await mongodb["matches"].find_one({"_id": match["_id"]})
        assert len(updated["home"]["roster"]["players"]) == 0

    async def test_legacy_flat_structure_compatibility(self, client: AsyncClient, mongodb):
        """Test GET works with legacy flat roster structure"""
        from tests.fixtures.data_fixtures import create_test_match, create_test_roster_player

        match = create_test_match()
        match["home"]["roster"] = [create_test_roster_player("player-1")]
        match["home"]["rosterStatus"] = "SUBMITTED"
        match["home"]["rosterPublished"] = True
        match["home"]["coach"] = {"firstName": "Old", "lastName": "Coach"}
        await mongodb["matches"].insert_one(match)

        response = await client.get(f"/matches/{match['_id']}/home/roster")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]["players"]) == 1
        assert data["data"]["status"] == "SUBMITTED"
        assert data["data"]["published"] is True
        assert data["data"]["coach"]["firstName"] == "Old"
