"""Integration tests for players API endpoints"""

from datetime import datetime

import pytest
from httpx import AsyncClient


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
            "teams": [
                {
                    "_id": "team-1",
                    "name": "Team A",
                    "alias": "team-a",
                    "ageGroup": "U15",
                    "ishdId": "123",
                }
            ],
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
            "sex": "männlich",
            "fullFaceReq": "false",
            "managedByISHD": "false",
            "source": "BISHL",
        }

        response = await client.post(
            "/players", data=player_data, headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Assert response
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["data"]["firstName"] == "John"
        assert data["data"]["lastName"] == "Doe"
        assert "_id" in data["data"]
        assert data["data"]["suspensions"] == []
        assert data["data"]["playUpTrackings"] == []

        # Verify database
        player_in_db = await mongodb["players"].find_one({"_id": data["data"]["_id"]})
        assert player_in_db is not None
        assert player_in_db["firstName"] == "John"

        # Birthdate must be stored as a native datetime (not a string) with no time/tz component
        bd = player_in_db["birthdate"]
        assert isinstance(bd, datetime), f"birthdate must be datetime, got {type(bd)}"
        assert bd == datetime(2008, 5, 15, 0, 0, 0)
        assert bd.tzinfo is None, "birthdate must be timezone-naive"

    async def test_create_player_duplicate_rejected(
        self, client: AsyncClient, mongodb, admin_token
    ):
        """Test that creating a player with the same name and birthdate is rejected"""
        player_data = {
            "firstName": "Duplicate",
            "lastName": "Player",
            "birthdate": "2005-03-10",
            "displayFirstName": "Duplicate",
            "displayLastName": "Player",
            "sex": "männlich",
            "managedByISHD": "false",
            "source": "BISHL",
        }

        # First creation should succeed
        response = await client.post(
            "/players", data=player_data, headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 201

        # Second creation with identical data should be rejected with 422
        response = await client.post(
            "/players", data=player_data, headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 400

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
            f"/players/{player['_id']}", headers={"Authorization": f"Bearer {admin_token}"}
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
            f"/players/{fake_id}", headers={"Authorization": f"Bearer {admin_token}"}
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
            headers={"Authorization": f"Bearer {admin_token}"},
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
            f"/players/{player['_id']}", headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Assert
        assert response.status_code == 204

        # Verify deleted from database
        deleted = await mongodb["players"].find_one({"_id": player["_id"]})
        assert deleted is None

    async def test_get_players_for_club(self, client: AsyncClient, mongodb, admin_token):
        """Test retrieving players for a club"""
        from tests.fixtures.data_fixtures import create_test_player

        # Setup - Create club first
        club = {
            "_id": "club-1",
            "name": "Test Club",
            "alias": "test-club",
            "active": True,
            "teams": [],
        }
        await mongodb["clubs"].insert_one(club)

        # Setup players
        player1 = create_test_player("player-1")
        player1["assignedTeams"] = [
            {"clubId": "club-1", "clubName": "Test Club", "clubAlias": "test-club", "teams": []}
        ]
        player2 = create_test_player("player-2")
        player2["assignedTeams"] = [
            {
                "clubId": "other-club",
                "clubName": "Other Club",
                "clubAlias": "other-club",
                "teams": [],
            }
        ]
        await mongodb["players"].insert_many([player1, player2])

        # Execute
        response = await client.get(
            "/players/clubs/test-club", headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["pagination"]["total_items"] >= 1

    async def test_get_players_for_team(self, client: AsyncClient, mongodb, admin_token):
        """Test retrieving players for a specific team"""

        # Setup - Create club with team first
        club = {
            "_id": "club-1",
            "name": "Test Club",
            "alias": "test-club",
            "active": True,
            "teams": [{"_id": "team-1", "name": "Team A", "alias": "team-a", "ageGroup": "U15"}],
        }
        await mongodb["clubs"].insert_one(club)

    async def test_create_player_with_suspensions(self, client: AsyncClient, mongodb, admin_token):
        """Test creating a player with suspensions"""
        import json
        from datetime import datetime, timedelta

        # Setup - Create a club and team
        club = {
            "_id": "test-club-id",
            "name": "Test Club",
            "alias": "test-club",
            "teams": [
                {
                    "_id": "team-1",
                    "name": "Team A",
                    "alias": "team-a",
                    "ageGroup": "U15",
                    "ishdId": "123",
                }
            ],
        }
        await mongodb["clubs"].insert_one(club)

        # Prepare suspension data
        suspensions = [
            {
                "startDate": (datetime.now() - timedelta(days=7)).isoformat(),
                "endDate": (datetime.now() + timedelta(days=7)).isoformat(),
                "reason": "Unsportsmanlike conduct",
                "teamIds": ["team-1"],
            }
        ]

        # Execute - Create player with suspensions
        player_data = {
            "firstName": "Suspended",
            "lastName": "Player",
            "birthdate": "2008-05-15",
            "displayFirstName": "Suspended",
            "displayLastName": "Player",
            "nationality": "deutsch",
            "sex": "männlich",
            "suspensions": json.dumps(suspensions),
            "source": "BISHL",
        }

        response = await client.post(
            "/players", data=player_data, headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Assert response
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]["suspensions"]) == 1
        assert data["data"]["suspensions"][0]["reason"] == "Unsportsmanlike conduct"
        assert data["data"]["suspensions"][0]["teamIds"] == ["team-1"]

    async def test_update_player_suspensions(self, client: AsyncClient, mongodb, admin_token):
        """Test updating player suspensions"""
        import json
        from datetime import datetime, timedelta

        from tests.fixtures.data_fixtures import create_test_player

        # Setup
        player = create_test_player("player-1")
        player["firstName"] = "Test"
        player["lastName"] = "Player"
        player["birthdate"] = datetime(2008, 1, 1)
        player["suspensions"] = []
        await mongodb["players"].insert_one(player)

        # Prepare new suspension
        new_suspensions = [
            {
                "startDate": (datetime.now()).isoformat(),
                "endDate": (datetime.now() + timedelta(days=14)).isoformat(),
                "reason": "Game misconduct",
                "teamIds": ["team-1", "team-2"],
            }
        ]

        # Execute - Update suspensions
        response = await client.patch(
            f"/players/{player['_id']}",
            data={"suspensions": json.dumps(new_suspensions)},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]["suspensions"]) == 1
        assert data["data"]["suspensions"][0]["reason"] == "Game misconduct"

        # Verify database
        updated = await mongodb["players"].find_one({"_id": player["_id"]})
        assert len(updated["suspensions"]) == 1
        assert updated["suspensions"][0]["reason"] == "Game misconduct"

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
            "/players?search=Michael", headers={"Authorization": f"Bearer {admin_token}"}
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

        assert response.status_code == 403


class TestPlayerPoolAPI:
    """Tests for the merged player pool endpoint."""

    def _make_assigned_teams(self, club_alias: str, team_alias: str) -> list[dict]:
        return [{"clubAlias": club_alias, "teams": [{"teamAlias": team_alias, "active": True}]}]

    def _make_player(self, pid: str, first: str, club_alias: str, team_alias: str) -> dict:
        return {
            "_id": pid,
            "firstName": first,
            "lastName": "Pooltest",
            "displayFirstName": first,
            "displayLastName": "Pooltest",
            "birthdate": datetime(2005, 1, 1),
            "nationality": "deutsch",
            "position": "Skater",
            "sex": "männlich",
            "fullFaceReq": False,
            "managedByISHD": False,
            "source": "BISHL",
            "published": True,
            "assignedTeams": self._make_assigned_teams(club_alias, team_alias),
            "stats": [],
            "createdAt": datetime(2024, 1, 1),
            "updatedAt": datetime(2024, 1, 1),
        }

    @pytest.mark.asyncio
    async def test_pool_primary_only(self, client: AsyncClient, mongodb, admin_token):
        """Pool with no partnership returns only primary team players."""
        club = {
            "_id": "pool-club-1",
            "name": "Pool Club 1",
            "alias": "pool-club-1",
            "teams": [
                {
                    "_id": "pool-team-a",
                    "name": "Team A",
                    "alias": "team-a",
                    "ageGroup": "HERREN",
                    "teamPartnership": [],
                }
            ],
        }
        await mongodb["clubs"].insert_one(club)

        p1 = self._make_player("pool-p1", "Alice", "pool-club-1", "team-a")
        p2 = self._make_player("pool-p2", "Bob", "pool-club-1", "team-a")
        await mongodb["players"].insert_many([p1, p2])

        response = await client.get(
            "/players/clubs/pool-club-1/teams/team-a/pool",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]) == 2
        for entry in data["data"]:
            assert entry["sourceClubAlias"] == "pool-club-1"
            assert entry["sourceTeamAlias"] == "team-a"

    @pytest.mark.asyncio
    async def test_pool_with_partnership_merges_and_deduplicates(
        self, client: AsyncClient, mongodb, admin_token
    ):
        """Pool merges players from partnership teams and deduplicates shared players."""
        club_a = {
            "_id": "ptn-club-a",
            "name": "Club A",
            "alias": "ptn-club-a",
            "teams": [
                {
                    "_id": "ptn-team-1",
                    "name": "Team 1",
                    "alias": "ptn-team-1",
                    "ageGroup": "HERREN",
                    "teamPartnership": [
                        {"clubAlias": "ptn-club-b", "teamAlias": "ptn-team-2"}
                    ],
                }
            ],
        }
        club_b = {
            "_id": "ptn-club-b",
            "name": "Club B",
            "alias": "ptn-club-b",
            "teams": [
                {
                    "_id": "ptn-team-2",
                    "name": "Team 2",
                    "alias": "ptn-team-2",
                    "ageGroup": "HERREN",
                    "teamPartnership": [],
                }
            ],
        }
        await mongodb["clubs"].insert_many([club_a, club_b])

        # primary player only on team-1
        primary = self._make_player("ptn-p1", "Primary", "ptn-club-a", "ptn-team-1")
        # partnership player only on team-2
        partner = self._make_player("ptn-p2", "Partner", "ptn-club-b", "ptn-team-2")
        # player assigned to BOTH teams (should appear only once)
        shared = {
            **self._make_player("ptn-p3", "Shared", "ptn-club-a", "ptn-team-1"),
            "assignedTeams": [
                {"clubAlias": "ptn-club-a", "teams": [{"teamAlias": "ptn-team-1", "active": True}]},
                {"clubAlias": "ptn-club-b", "teams": [{"teamAlias": "ptn-team-2", "active": True}]},
            ],
        }
        await mongodb["players"].insert_many([primary, partner, shared])

        response = await client.get(
            "/players/clubs/ptn-club-a/teams/ptn-team-1/pool",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        pool_ids = [e["_id"] for e in data["data"]]
        # All three players must appear exactly once
        assert set(pool_ids) == {"ptn-p1", "ptn-p2", "ptn-p3"}
        assert len(pool_ids) == len(set(pool_ids)), "Duplicate players in pool"

        # Each entry carries source annotation
        for entry in data["data"]:
            assert "sourceClubAlias" in entry
            assert "sourceTeamAlias" in entry

    @pytest.mark.asyncio
    async def test_pool_404_unknown_club(self, client: AsyncClient, mongodb, admin_token):
        """Returns 404 when the club does not exist."""
        response = await client.get(
            "/players/clubs/no-such-club/teams/no-such-team/pool",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_pool_404_unknown_team(self, client: AsyncClient, mongodb, admin_token):
        """Returns 404 when the team does not exist within the club."""
        club = {
            "_id": "pool-404-club",
            "name": "Pool 404 Club",
            "alias": "pool-404-club",
            "teams": [],
        }
        await mongodb["clubs"].insert_one(club)

        response = await client.get(
            "/players/clubs/pool-404-club/teams/ghost-team/pool",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_pool_requires_auth(self, client: AsyncClient, mongodb):
        """Pool endpoint requires authentication."""
        response = await client.get("/players/clubs/any-club/teams/any-team/pool")
        assert response.status_code == 403
