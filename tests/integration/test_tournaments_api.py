"""Integration tests for tournaments API endpoints"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestTournamentsAPI:
    """Test tournament CRUD operations"""

    async def test_get_tournaments_list(self, client: AsyncClient, mongodb):
        """Test retrieving list of tournaments"""
        from tests.fixtures.data_fixtures import create_test_tournament

        # Setup - Create tournaments
        tournament1 = create_test_tournament()
        tournament1["name"] = "League A"
        tournament1["alias"] = "league-a"
        tournament2 = create_test_tournament()
        tournament2["name"] = "League B"
        tournament2["alias"] = "league-b"
        await mongodb["tournaments"].insert_many([tournament1, tournament2])

        # Execute
        response = await client.get("/tournaments")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "data" in data
        assert "pagination" in data
        assert len(data["data"]) >= 2
        assert data["pagination"]["total_items"] >= 2

    async def test_get_tournament_by_alias(self, client: AsyncClient, mongodb):
        """Test retrieving a single tournament by alias"""
        from tests.fixtures.data_fixtures import create_test_tournament

        # Setup
        tournament = create_test_tournament()
        await mongodb["tournaments"].insert_one(tournament)

        # Execute
        response = await client.get(f"/tournaments/{tournament['alias']}")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["_id"] == tournament["_id"]
        assert data["data"]["alias"] == tournament["alias"]

    async def test_get_tournament_not_found(self, client: AsyncClient):
        """Test retrieving non-existent tournament returns 404"""
        response = await client.get("/tournaments/non-existent-tournament")

        assert response.status_code == 404
        data = response.json()
        assert "error" in data
        assert "not found" in data["error"]["message"].lower()

    async def test_create_tournament(self, client: AsyncClient, mongodb, admin_token):
        """Test creating a new tournament"""
        tournament_data = {
            "name": "New League",
            "alias": "new-league",
            "tinyName": "NL",
            "ageGroup": {"key": "U18", "value": "U18"},
            "published": True,
            "active": True,
            "seasons": [],
        }

        response = await client.post(
            "/tournaments", json=tournament_data, headers={"Authorization": f"Bearer {admin_token}"}
        )

        assert response.status_code == 201
        data = response.json()
        assert data["data"]["name"] == "New League"
        assert data["data"]["alias"] == "new-league"

        # Verify in database
        tournament_in_db = await mongodb["tournaments"].find_one({"alias": "new-league"})
        assert tournament_in_db is not None

    async def test_create_tournament_unauthorized(self, client: AsyncClient):
        """Test creating tournament without auth fails"""
        tournament_data = {
            "name": "Test League",
            "alias": "test-league",
            "tinyName": "TL",
            "ageGroup": {"key": "U18", "value": "U18"},
        }

        response = await client.post("/tournaments", json=tournament_data)

        assert response.status_code == 403

    async def test_update_tournament(self, client: AsyncClient, mongodb, admin_token):
        """Test updating a tournament"""
        from tests.fixtures.data_fixtures import create_test_tournament

        # Setup
        tournament = create_test_tournament()
        await mongodb["tournaments"].insert_one(tournament)

        # Execute
        response = await client.patch(
            f"/tournaments/{tournament['_id']}",
            json={"name": "Updated League Name"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["name"] == "Updated League Name"

        # Verify in database
        updated = await mongodb["tournaments"].find_one({"_id": tournament["_id"]})
        assert updated["name"] == "Updated League Name"

    async def test_delete_tournament(self, client: AsyncClient, mongodb, admin_token):
        """Test deleting a tournament"""
        from tests.fixtures.data_fixtures import create_test_tournament

        # Setup
        tournament = create_test_tournament()
        await mongodb["tournaments"].insert_one(tournament)

        # Execute
        response = await client.delete(
            f"/tournaments/{tournament['_id']}", headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Assert
        assert response.status_code == 204

        # Verify deleted from database
        deleted = await mongodb["tournaments"].find_one({"_id": tournament["_id"]})
        assert deleted is None


@pytest.mark.asyncio
class TestSeasonsAPI:
    """Test season operations within tournaments"""

    async def test_get_seasons_list(self, client: AsyncClient, mongodb):
        """Test retrieving all seasons for a tournament"""
        from tests.fixtures.data_fixtures import create_test_tournament

        # Setup
        tournament = create_test_tournament()
        await mongodb["tournaments"].insert_one(tournament)

        # Execute
        response = await client.get(f"/tournaments/{tournament['alias']}/seasons")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "data" in data
        assert isinstance(data["data"], list)
        assert len(data["data"]) >= 1

    async def test_get_season_by_alias(self, client: AsyncClient, mongodb):
        """Test retrieving a single season"""
        from tests.fixtures.data_fixtures import create_test_tournament

        # Setup
        tournament = create_test_tournament()
        await mongodb["tournaments"].insert_one(tournament)
        season_alias = tournament["seasons"][0]["alias"]

        # Execute
        response = await client.get(f"/tournaments/{tournament['alias']}/seasons/{season_alias}")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["alias"] == season_alias

    async def test_create_season(self, client: AsyncClient, mongodb, admin_token):
        """Test creating a new season"""
        from tests.fixtures.data_fixtures import create_test_tournament

        # Setup
        tournament = create_test_tournament()
        await mongodb["tournaments"].insert_one(tournament)

        season_data = {
            "name": "2025",
            "alias": "2025",
            "published": True,
            "standingsSettings": {"pointsWinReg": 3, "pointsLossReg": 0, "pointsDrawReg": 1},
        }

        # Execute
        response = await client.post(
            f"/tournaments/{tournament['alias']}/seasons",
            json=season_data,
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["data"]["alias"] == "2025"

    async def test_update_season(self, client: AsyncClient, mongodb, admin_token):
        """Test updating a season"""
        from tests.fixtures.data_fixtures import create_test_tournament

        # Setup
        tournament = create_test_tournament()
        await mongodb["tournaments"].insert_one(tournament)
        season_id = tournament["seasons"][0]["_id"]

        # Execute
        response = await client.patch(
            f"/tournaments/{tournament['alias']}/seasons/{season_id}",
            json={"name": "Updated Season"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["name"] == "Updated Season"

    async def test_delete_season(self, client: AsyncClient, mongodb, admin_token):
        """Test deleting a season"""
        from tests.fixtures.data_fixtures import create_test_tournament

        # Setup
        tournament = create_test_tournament()
        await mongodb["tournaments"].insert_one(tournament)
        season_id = tournament["seasons"][0]["_id"]

        # Execute
        response = await client.delete(
            f"/tournaments/{tournament['alias']}/seasons/{season_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        # Assert
        assert response.status_code == 204


@pytest.mark.asyncio
class TestRoundsAPI:
    """Test round operations within seasons"""

    async def test_get_rounds_list(self, client: AsyncClient, mongodb):
        """Test retrieving all rounds for a season"""
        from tests.fixtures.data_fixtures import create_test_tournament

        # Setup
        tournament = create_test_tournament()
        await mongodb["tournaments"].insert_one(tournament)
        season_alias = tournament["seasons"][0]["alias"]

        # Execute
        response = await client.get(
            f"/tournaments/{tournament['alias']}/seasons/{season_alias}/rounds"
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)
        assert len(data["data"]) >= 1

    async def test_get_round_by_alias(self, client: AsyncClient, mongodb):
        """Test retrieving a single round"""
        from tests.fixtures.data_fixtures import create_test_tournament

        # Setup
        tournament = create_test_tournament()
        await mongodb["tournaments"].insert_one(tournament)
        season_alias = tournament["seasons"][0]["alias"]
        round_alias = tournament["seasons"][0]["rounds"][0]["alias"]

        # Execute
        response = await client.get(
            f"/tournaments/{tournament['alias']}/seasons/{season_alias}/rounds/{round_alias}"
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["alias"] == round_alias

    async def test_create_round(self, client: AsyncClient, mongodb, admin_token):
        """Test creating a new round"""
        from tests.fixtures.data_fixtures import create_test_tournament

        # Setup
        tournament = create_test_tournament()
        await mongodb["tournaments"].insert_one(tournament)
        season_alias = tournament["seasons"][0]["alias"]

        round_data = {
            "name": "Playoffs",
            "alias": "playoffs",
            "sortOrder": 2,
            "createStandings": True,
            "createStats": True,
            "matchdaysType": {"key": "PLAYOFF", "value": "Playoff"},
            "matchdaysSortedBy": {"key": "DATE", "value": "Datum"},
            "published": True,
        }

        # Execute
        response = await client.post(
            f"/tournaments/{tournament['alias']}/seasons/{season_alias}/rounds",
            json=round_data,
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["data"]["alias"] == "playoffs"

    async def test_update_round(self, client: AsyncClient, mongodb, admin_token):
        """Test updating a round"""
        from tests.fixtures.data_fixtures import create_test_tournament

        # Setup
        tournament = create_test_tournament()
        await mongodb["tournaments"].insert_one(tournament)
        season_alias = tournament["seasons"][0]["alias"]
        round_id = tournament["seasons"][0]["rounds"][0]["_id"]

        # Execute
        response = await client.patch(
            f"/tournaments/{tournament['alias']}/seasons/{season_alias}/rounds/{round_id}",
            json={"name": "Updated Round"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["name"] == "Updated Round"

    async def test_delete_round(self, client: AsyncClient, mongodb, admin_token):
        """Test deleting a round"""
        from tests.fixtures.data_fixtures import create_test_tournament

        # Setup
        tournament = create_test_tournament()
        await mongodb["tournaments"].insert_one(tournament)
        season_alias = tournament["seasons"][0]["alias"]
        round_id = tournament["seasons"][0]["rounds"][0]["_id"]

        # Execute
        response = await client.delete(
            f"/tournaments/{tournament['alias']}/seasons/{season_alias}/rounds/{round_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        # Assert
        assert response.status_code == 204


@pytest.mark.asyncio
class TestMatchdaysAPI:
    """Test matchday operations within rounds"""

    async def test_get_matchdays_list(self, client: AsyncClient, mongodb):
        """Test retrieving all matchdays for a round"""
        from tests.fixtures.data_fixtures import create_test_tournament

        # Setup
        tournament = create_test_tournament()
        await mongodb["tournaments"].insert_one(tournament)
        season_alias = tournament["seasons"][0]["alias"]
        round_alias = tournament["seasons"][0]["rounds"][0]["alias"]

        # Execute
        response = await client.get(
            f"/tournaments/{tournament['alias']}/seasons/{season_alias}/rounds/{round_alias}/matchdays"
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)
        assert len(data["data"]) >= 1

    async def test_get_matchday_by_alias(self, client: AsyncClient, mongodb):
        """Test retrieving a single matchday"""
        from tests.fixtures.data_fixtures import create_test_tournament

        # Setup
        tournament = create_test_tournament()
        await mongodb["tournaments"].insert_one(tournament)
        season_alias = tournament["seasons"][0]["alias"]
        round_alias = tournament["seasons"][0]["rounds"][0]["alias"]
        matchday_alias = tournament["seasons"][0]["rounds"][0]["matchdays"][0]["alias"]

        # Execute
        response = await client.get(
            f"/tournaments/{tournament['alias']}/seasons/{season_alias}/rounds/{round_alias}/matchdays/{matchday_alias}"
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["alias"] == matchday_alias

    async def test_create_matchday(self, client: AsyncClient, mongodb, admin_token):
        """Test creating a new matchday"""
        from tests.fixtures.data_fixtures import create_test_tournament

        # Setup
        tournament = create_test_tournament()
        await mongodb["tournaments"].insert_one(tournament)
        season_alias = tournament["seasons"][0]["alias"]
        round_alias = tournament["seasons"][0]["rounds"][0]["alias"]

        matchday_data = {
            "name": "2. Spieltag",
            "alias": "2-spieltag",
            "type": {"key": "REGULAR", "value": "Regulär"},
            "createStandings": True,
            "createStats": True,
            "published": True,
        }

        # Execute
        response = await client.post(
            f"/tournaments/{tournament['alias']}/seasons/{season_alias}/rounds/{round_alias}/matchdays",
            json=matchday_data,
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["data"]["alias"] == "2-spieltag"

    async def test_update_matchday(self, client: AsyncClient, mongodb, admin_token):
        """Test updating a matchday"""
        from tests.fixtures.data_fixtures import create_test_tournament

        # Setup
        tournament = create_test_tournament()
        await mongodb["tournaments"].insert_one(tournament)
        season_alias = tournament["seasons"][0]["alias"]
        round_alias = tournament["seasons"][0]["rounds"][0]["alias"]
        matchday_id = tournament["seasons"][0]["rounds"][0]["matchdays"][0]["_id"]

        # Execute
        response = await client.patch(
            f"/tournaments/{tournament['alias']}/seasons/{season_alias}/rounds/{round_alias}/matchdays/{matchday_id}",
            json={"name": "Updated Matchday"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["name"] == "Updated Matchday"

    async def test_delete_matchday(self, client: AsyncClient, mongodb, admin_token):
        """Test deleting a matchday"""
        from tests.fixtures.data_fixtures import create_test_tournament

        # Setup
        tournament = create_test_tournament()
        await mongodb["tournaments"].insert_one(tournament)
        season_alias = tournament["seasons"][0]["alias"]
        round_alias = tournament["seasons"][0]["rounds"][0]["alias"]
        matchday_id = tournament["seasons"][0]["rounds"][0]["matchdays"][0]["_id"]

        # Execute
        response = await client.delete(
            f"/tournaments/{tournament['alias']}/seasons/{season_alias}/rounds/{round_alias}/matchdays/{matchday_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        # Assert
        assert response.status_code == 204
