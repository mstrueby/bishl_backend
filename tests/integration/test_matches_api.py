
"""Integration tests for matches API endpoints"""
import pytest
from httpx import AsyncClient
from bson import ObjectId


@pytest.mark.asyncio
class TestMatchesAPI:
    """Test matches CRUD operations"""

    async def test_create_match_success(self, client: AsyncClient, mongodb, admin_token):
        """Test creating a new match"""
        from tests.fixtures.data_fixtures import create_test_tournament, create_test_season
        from bson import ObjectId
        
        # Setup: Insert required data
        tournament = create_test_tournament()
        season = create_test_season()
        
        # Create teams with all required fields
        home_team_id = str(ObjectId())
        away_team_id = str(ObjectId())
        
        home_team = {
            "_id": home_team_id,
            "name": "Home Team",
            "fullName": "Home Team Full",
            "shortName": "HOME",
            "tinyName": "HOM",
            "teamAlias": "home-team",
            "published": True
        }
        
        away_team = {
            "_id": away_team_id,
            "name": "Away Team",
            "fullName": "Away Team Full",
            "shortName": "AWAY",
            "tinyName": "AWY",
            "teamAlias": "away-team",
            "published": True
        }
        
        await mongodb["tournaments"].insert_one(tournament)
        await mongodb["seasons"].insert_one({**season, "tournament": {"alias": tournament["alias"]}})
        await mongodb["teams"].insert_many([home_team, away_team])
        
        # Create match data with all required fields
        match_data = {
            "matchId": 1001,
            "tournament": {"name": tournament["name"], "alias": tournament["alias"]},
            "season": {"name": season["name"], "alias": season["alias"]},
            "round": {"name": "Hauptrunde", "alias": "hauptrunde"},
            "matchday": {"name": "1. Spieltag", "alias": "1"},
            "matchStatus": {"key": "SCHEDULED", "value": "angesetzt"},
            "home": {
                "teamAlias": home_team["teamAlias"],
                "name": home_team["name"],
                "fullName": home_team["fullName"],
                "shortName": home_team["shortName"],
                "tinyName": home_team["tinyName"]
            },
            "away": {
                "teamAlias": away_team["teamAlias"],
                "name": away_team["name"],
                "fullName": away_team["fullName"],
                "shortName": away_team["shortName"],
                "tinyName": away_team["tinyName"]
            }
        }
        
        # Execute
        response = await client.post(
            "/matches/",
            json=match_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        # Assert response
        assert response.status_code == 201
        data = response.json()
        assert data["matchId"] == 1001
        assert data["matchStatus"]["key"] == "SCHEDULED"
        assert data["home"]["team"]["_id"] == home_team["_id"]
        
        # Assert database
        match_in_db = await mongodb["matches"].find_one({"_id": data["_id"]})
        assert match_in_db is not None
        assert match_in_db["matchId"] == 1001

    async def test_get_match_by_id(self, client: AsyncClient, mongodb):
        """Test retrieving a match by ID"""
        from tests.fixtures.data_fixtures import create_test_match
        
        # Setup
        match = create_test_match()
        await mongodb["matches"].insert_one(match)
        
        # Execute
        response = await client.get(f"/matches/{match['_id']}")
        
        # Assert
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["success"] is True
        assert response_data["data"]["_id"] == match["_id"]
        assert response_data["data"]["matchId"] == match["matchId"]

    async def test_get_match_not_found(self, client: AsyncClient):
        """Test retrieving non-existent match returns 404"""
        fake_id = str(ObjectId())
        
        response = await client.get(f"/matches/{fake_id}")
        
        assert response.status_code == 404
        assert "not found" in response.json()["error"]["message"].lower()

    async def test_update_match_status(self, client: AsyncClient, mongodb, admin_token):
        """Test updating match status"""
        from tests.fixtures.data_fixtures import create_test_match
        
        # Setup
        match = create_test_match(status="SCHEDULED")
        await mongodb["matches"].insert_one(match)
        
        # Execute - Start match
        response = await client.patch(
            f"/matches/{match['_id']}",
            json={"matchStatus": {"key": "INPROGRESS"}},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["matchStatus"]["key"] == "INPROGRESS"
        
        # Verify in database
        updated = await mongodb["matches"].find_one({"_id": match["_id"]})
        assert updated["matchStatus"]["key"] == "INPROGRESS"

    async def test_update_match_unauthorized(self, client: AsyncClient, mongodb):
        """Test updating match without auth token fails"""
        from tests.fixtures.data_fixtures import create_test_match
        
        match = create_test_match()
        await mongodb["matches"].insert_one(match)
        
        response = await client.patch(
            f"/matches/{match['_id']}",
            json={"matchStatus": {"key": "INPROGRESS"}}
        )
        
        assert response.status_code == 401

    async def test_finish_match_updates_stats(self, client: AsyncClient, mongodb, admin_token):
        """Test finishing match calculates and stores stats"""
        from tests.fixtures.data_fixtures import create_test_match
        
        # Setup - Match in progress with scores
        match = create_test_match(status="INPROGRESS")
        match["home"]["scores"] = [{"_id": "s1"}, {"_id": "s2"}]
        match["away"]["scores"] = [{"_id": "s3"}]
        await mongodb["matches"].insert_one(match)
        
        # Execute - Finish match
        response = await client.patch(
            f"/matches/{match['_id']}",
            json={
                "matchStatus": {"key": "FINISHED"},
                "finishType": {"key": "REGULAR"}
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["matchStatus"]["key"] == "FINISHED"
        
        # Verify stats were calculated
        updated = await mongodb["matches"].find_one({"_id": match["_id"]})
        assert updated["home"]["stats"]["goalsFor"] == 2
        assert updated["home"]["stats"]["points"] == 3  # Win
        assert updated["away"]["stats"]["goalsFor"] == 1
        assert updated["away"]["stats"]["points"] == 0  # Loss

    async def test_list_matches_pagination(self, client: AsyncClient, mongodb):
        """Test listing matches with pagination"""
        from tests.fixtures.data_fixtures import create_test_match
        
        # Setup - Insert multiple matches
        matches = [create_test_match() for _ in range(5)]
        await mongodb["matches"].insert_many(matches)
        
        # Execute - Get first page
        response = await client.get("/matches?page=1&page_size=3")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 3
        assert data["page"] == 1
        assert data["total_items"] == 5
        assert data["total_pages"] == 2

    async def test_list_matches_filter_by_tournament(self, client: AsyncClient, mongodb):
        """Test filtering matches by tournament"""
        from tests.fixtures.data_fixtures import create_test_match
        
        # Setup - Matches from different tournaments
        match1 = create_test_match()
        match1["tournament"] = {"alias": "league-a"}
        match2 = create_test_match()
        match2["tournament"] = {"alias": "league-b"}
        await mongodb["matches"].insert_many([match1, match2])
        
        # Execute
        response = await client.get("/matches?tournament_alias=league-a")
        
        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["tournament"]["alias"] == "league-a"

    async def test_delete_match(self, client: AsyncClient, mongodb, admin_token):
        """Test deleting a match"""
        from tests.fixtures.data_fixtures import create_test_match
        
        # Setup
        match = create_test_match()
        await mongodb["matches"].insert_one(match)
        
        # Execute
        response = await client.delete(
            f"/matches/{match['_id']}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        # Assert
        assert response.status_code == 204
        
        # Verify deleted from database
        deleted = await mongodb["matches"].find_one({"_id": match["_id"]})
        assert deleted is None
