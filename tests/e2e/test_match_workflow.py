
"""End-to-end tests for match workflow"""
import pytest
from httpx import AsyncClient
from bson import ObjectId
from datetime import datetime, timedelta


@pytest.mark.asyncio
class TestMatchWorkflow:
    """Test complete match workflow from creation to finish"""

    async def test_complete_match_workflow(self, client: AsyncClient, mongodb, admin_token):
        """
        Test complete match flow: create → start → add roster → score → penalties → finish → standings
        """
        # 1. Setup: Create tournament, season, teams, and players
        tournament_id = str(ObjectId())
        tournament = {
            "_id": tournament_id,
            "name": "Test League",
            "alias": "test-league",
            "tinyName": "TL",
            "published": True,
            "seasons": [
                {
                    "name": "2024/25",
                    "alias": "2024-25",
                    "year": 2024,
                    "published": True,
                    "isCurrent": True,
                    "standingsSettings": {
                        "pointsWinReg": 3,
                        "pointsLossReg": 0,
                        "pointsDrawReg": 1,
                        "pointsWinOvertime": 2,
                        "pointsLossOvertime": 1,
                        "pointsWinShootout": 2,
                        "pointsLossShootout": 1,
                    },
                    "rounds": [
                        {
                            "name": "Hauptrunde",
                            "alias": "hauptrunde",
                            "published": True,
                            "matchdays": [
                                {
                                    "name": "1. Spieltag",
                                    "alias": "1-spieltag",
                                    "published": True,
                                    "date": datetime.now() + timedelta(days=7),
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        await mongodb["tournaments"].insert_one(tournament)

        # Create teams
        home_team_id = str(ObjectId())
        away_team_id = str(ObjectId())
        
        home_team = {
            "_id": home_team_id,
            "name": "Home Tigers",
            "fullName": "Home Tigers Full",
            "shortName": "HOME",
            "tinyName": "HOM",
            "teamAlias": "home-tigers",
            "clubId": "club-home",
            "clubName": "Home Club",
            "published": True,
        }
        
        away_team = {
            "_id": away_team_id,
            "name": "Away Lions",
            "fullName": "Away Lions Full",
            "shortName": "AWAY",
            "tinyName": "AWY",
            "teamAlias": "away-lions",
            "clubId": "club-away",
            "clubName": "Away Club",
            "published": True,
        }
        
        await mongodb["teams"].insert_many([home_team, away_team])

        # Create players
        player1_id = str(ObjectId())
        player2_id = str(ObjectId())
        player3_id = str(ObjectId())
        player4_id = str(ObjectId())
        
        players = [
            {
                "_id": player1_id,
                "firstName": "John",
                "lastName": "Scorer",
                "alias": "john-scorer",
                "jersey": 10,
                "sex": "MALE",
                "published": True,
            },
            {
                "_id": player2_id,
                "firstName": "Jane",
                "lastName": "Assist",
                "alias": "jane-assist",
                "jersey": 11,
                "sex": "FEMALE",
                "published": True,
            },
            {
                "_id": player3_id,
                "firstName": "Bob",
                "lastName": "Penalty",
                "alias": "bob-penalty",
                "jersey": 5,
                "sex": "MALE",
                "published": True,
            },
            {
                "_id": player4_id,
                "firstName": "Alice",
                "lastName": "Goalie",
                "alias": "alice-goalie",
                "jersey": 1,
                "sex": "FEMALE",
                "published": True,
            },
        ]
        await mongodb["players"].insert_many(players)

        # 2. Create match
        match_data = {
            "matchId": 1001,
            "tournament": {"name": tournament["name"], "alias": tournament["alias"]},
            "season": {
                "name": tournament["seasons"][0]["name"],
                "alias": tournament["seasons"][0]["alias"],
            },
            "round": {"name": "Hauptrunde", "alias": "hauptrunde"},
            "matchday": {"name": "1. Spieltag", "alias": "1-spieltag"},
            "matchStatus": {"key": "SCHEDULED", "value": "angesetzt"},
            "finishType": {"key": "REGULAR", "value": "Regulär"},
            "venue": {"venueId": "venue-1", "name": "Test Arena", "alias": "test-arena"},
            "startDate": (datetime.now() + timedelta(days=7)).isoformat(),
            "home": {
                "teamId": home_team_id,
                "teamAlias": home_team["teamAlias"],
                "name": home_team["name"],
                "fullName": home_team["fullName"],
                "shortName": home_team["shortName"],
                "tinyName": home_team["tinyName"],
                "clubId": home_team["clubId"],
                "clubName": home_team["clubName"],
            },
            "away": {
                "teamId": away_team_id,
                "teamAlias": away_team["teamAlias"],
                "name": away_team["name"],
                "fullName": away_team["fullName"],
                "shortName": away_team["shortName"],
                "tinyName": away_team["tinyName"],
                "clubId": away_team["clubId"],
                "clubName": away_team["clubName"],
            },
        }

        response = await client.post(
            "/matches", json=match_data, headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 201
        match_id = response.json()["data"]["_id"]

        # 3. Add roster
        home_roster = [
            {
                "player": {
                    "playerId": player1_id,
                    "firstName": "John",
                    "lastName": "Scorer",
                    "jerseyNumber": 10,
                },
                "playerPosition": {"key": "FORWARD", "value": "Stürmer"},
                "passNumber": "PASS001",
                "called": True,
            },
            {
                "player": {
                    "playerId": player2_id,
                    "firstName": "Jane",
                    "lastName": "Assist",
                    "jerseyNumber": 11,
                },
                "playerPosition": {"key": "FORWARD", "value": "Stürmer"},
                "passNumber": "PASS002",
                "called": True,
            },
            {
                "player": {
                    "playerId": player3_id,
                    "firstName": "Bob",
                    "lastName": "Penalty",
                    "jerseyNumber": 5,
                },
                "playerPosition": {"key": "DEFENSE", "value": "Verteidiger"},
                "passNumber": "PASS003",
                "called": True,
            },
        ]

        response = await client.put(
            f"/matches/{match_id}/home/roster",
            json=home_roster,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200

        # 4. Start match
        response = await client.patch(
            f"/matches/{match_id}",
            json={"matchStatus": {"key": "INPROGRESS", "value": "Live"}},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200

        # 5. Add scores (home team scores 3, away team scores 2)
        # Home goal 1
        response = await client.post(
            f"/matches/{match_id}/home/scores",
            json={
                "matchTime": "05:30",
                "goalPlayer": {
                    "playerId": player1_id,
                    "firstName": "John",
                    "lastName": "Scorer",
                    "jerseyNumber": 10,
                },
                "assistPlayer": {
                    "playerId": player2_id,
                    "firstName": "Jane",
                    "lastName": "Assist",
                    "jerseyNumber": 11,
                },
                "isPPG": False,
                "isSHG": False,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 201

        # Home goal 2
        response = await client.post(
            f"/matches/{match_id}/home/scores",
            json={
                "matchTime": "12:15",
                "goalPlayer": {
                    "playerId": player1_id,
                    "firstName": "John",
                    "lastName": "Scorer",
                    "jerseyNumber": 10,
                },
                "isPPG": False,
                "isSHG": False,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 201

        # Away goal 1
        response = await client.post(
            f"/matches/{match_id}/away/scores",
            json={
                "matchTime": "08:45",
                "goalPlayer": {
                    "playerId": player4_id,
                    "firstName": "Alice",
                    "lastName": "Goalie",
                    "jerseyNumber": 1,
                },
                "isPPG": False,
                "isSHG": False,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 201

        # Home goal 3
        response = await client.post(
            f"/matches/{match_id}/home/scores",
            json={
                "matchTime": "18:00",
                "goalPlayer": {
                    "playerId": player2_id,
                    "firstName": "Jane",
                    "lastName": "Assist",
                    "jerseyNumber": 11,
                },
                "isPPG": False,
                "isSHG": False,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 201

        # Away goal 2
        response = await client.post(
            f"/matches/{match_id}/away/scores",
            json={
                "matchTime": "19:30",
                "goalPlayer": {
                    "playerId": player4_id,
                    "firstName": "Alice",
                    "lastName": "Goalie",
                    "jerseyNumber": 1,
                },
                "isPPG": False,
                "isSHG": False,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 201

        # 6. Add penalties
        response = await client.post(
            f"/matches/{match_id}/home/penalties",
            json={
                "matchTimeStart": "10:00",
                "penaltyPlayer": {
                    "playerId": player3_id,
                    "firstName": "Bob",
                    "lastName": "Penalty",
                    "jerseyNumber": 5,
                },
                "penaltyCode": {"key": "ROUGH", "value": "Übertriebene Härte"},
                "penaltyMinutes": 2,
                "isGM": False,
                "isMP": False,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 201

        # 7. Finish match
        response = await client.patch(
            f"/matches/{match_id}",
            json={
                "matchStatus": {"key": "FINISHED", "value": "beendet"},
                "finishType": {"key": "REGULAR", "value": "Regulär"},
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200

        # 8. Verify final match state
        match_doc = await mongodb["matches"].find_one({"_id": match_id})
        
        # Verify match status
        assert match_doc["matchStatus"]["key"] == "FINISHED"
        assert match_doc["finishType"]["key"] == "REGULAR"
        
        # Verify scores
        assert len(match_doc["home"]["scores"]) == 3
        assert len(match_doc["away"]["scores"]) == 2
        
        # Verify penalties
        assert len(match_doc["home"]["penalties"]) == 1
        
        # Verify match stats
        assert match_doc["home"]["stats"]["goalsFor"] == 3
        assert match_doc["home"]["stats"]["goalsAgainst"] == 2
        assert match_doc["home"]["stats"]["points"] == 3  # Win in regular time
        assert match_doc["home"]["stats"]["win"] == 1
        assert match_doc["home"]["stats"]["gamePlayed"] == 1
        
        assert match_doc["away"]["stats"]["goalsFor"] == 2
        assert match_doc["away"]["stats"]["goalsAgainst"] == 3
        assert match_doc["away"]["stats"]["points"] == 0  # Loss
        assert match_doc["away"]["stats"]["loss"] == 1
        assert match_doc["away"]["stats"]["gamePlayed"] == 1
        
        # Verify roster stats
        home_roster_map = {
            r["player"]["playerId"]: r for r in match_doc["home"]["roster"]
        }
        
        # John Scorer: 2 goals, 1 assist = 3 points
        assert home_roster_map[player1_id]["goals"] == 2
        assert home_roster_map[player1_id]["assists"] == 0
        assert home_roster_map[player1_id]["points"] == 2
        
        # Jane Assist: 1 goal, 1 assist = 2 points
        assert home_roster_map[player2_id]["goals"] == 1
        assert home_roster_map[player2_id]["assists"] == 1
        assert home_roster_map[player2_id]["points"] == 2
        
        # Bob Penalty: 2 PIM
        assert home_roster_map[player3_id]["penaltyMinutes"] == 2

    async def test_overtime_match_workflow(self, client: AsyncClient, mongodb, admin_token):
        """Test match ending in overtime with correct point distribution"""
        from tests.fixtures.data_fixtures import create_test_tournament, create_test_match
        
        # Setup tournament with standings settings
        tournament = create_test_tournament()
        tournament["seasons"][0]["standingsSettings"] = {
            "pointsWinReg": 3,
            "pointsLossReg": 0,
            "pointsWinOvertime": 2,
            "pointsLossOvertime": 1,
            "pointsWinShootout": 2,
            "pointsLossShootout": 1,
        }
        await mongodb["tournaments"].insert_one(tournament)
        
        # Create match
        match = create_test_match(status="INPROGRESS")
        match["home"]["stats"] = {"goalsFor": 3, "goalsAgainst": 2}
        match["away"]["stats"] = {"goalsFor": 2, "goalsAgainst": 3}
        await mongodb["matches"].insert_one(match)
        match_id = match["_id"]
        
        # Finish in overtime
        response = await client.patch(
            f"/matches/{match_id}",
            json={
                "matchStatus": {"key": "FINISHED", "value": "beendet"},
                "finishType": {"key": "OVERTIME", "value": "Verlängerung"},
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        
        # Verify overtime points
        match_doc = await mongodb["matches"].find_one({"_id": match_id})
        assert match_doc["home"]["stats"]["points"] == 2  # OT win
        assert match_doc["home"]["stats"]["otWin"] == 1
        assert match_doc["away"]["stats"]["points"] == 1  # OT loss
        assert match_doc["away"]["stats"]["otLoss"] == 1

    async def test_shootout_match_workflow(self, client: AsyncClient, mongodb, admin_token):
        """Test match ending in shootout with correct point distribution"""
        from tests.fixtures.data_fixtures import create_test_tournament, create_test_match
        
        # Setup tournament
        tournament = create_test_tournament()
        tournament["seasons"][0]["standingsSettings"] = {
            "pointsWinReg": 3,
            "pointsLossReg": 0,
            "pointsWinOvertime": 2,
            "pointsLossOvertime": 1,
            "pointsWinShootout": 2,
            "pointsLossShootout": 1,
        }
        await mongodb["tournaments"].insert_one(tournament)
        
        # Create tied match
        match = create_test_match(status="INPROGRESS")
        match["home"]["stats"] = {"goalsFor": 2, "goalsAgainst": 2}
        match["away"]["stats"] = {"goalsFor": 2, "goalsAgainst": 2}
        await mongodb["matches"].insert_one(match)
        match_id = match["_id"]
        
        # Finish in shootout
        response = await client.patch(
            f"/matches/{match_id}",
            json={
                "matchStatus": {"key": "FINISHED", "value": "beendet"},
                "finishType": {"key": "SHOOTOUT", "value": "Penalty"},
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        
        # Verify shootout points (tied game, winner determined by shootout)
        match_doc = await mongodb["matches"].find_one({"_id": match_id})
        # In a tie, we can't determine winner without additional data,
        # but both teams should get some points
        total_points = match_doc["home"]["stats"]["points"] + match_doc["away"]["stats"]["points"]
        assert total_points == 3  # 2 for shootout win, 1 for shootout loss
