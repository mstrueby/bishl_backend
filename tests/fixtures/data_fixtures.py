"""Test data fixtures and helper functions for creating test documents"""
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any

from bson import ObjectId
from faker import Faker

fake = Faker()


def generate_test_id() -> str:
    """Generate a unique test ID"""
    return f"test_{uuid.uuid4().hex[:8]}"


def create_test_user(test_id: str = None, **overrides) -> Dict[str, Any]:
    """Create a test user document"""
    test_id = test_id or generate_test_id()
    user = {
        "test_id": test_id,
        "_id": overrides.get("_id", f"user_{test_id}"),
        "email": f"{test_id}@example.com",
        "firstName": "Test",
        "lastName": "User",
        "password": "$argon2id$v=19$m=65536,t=3,p=4$...",  # hashed password
        "roles": ["USER"],
        "isActive": True,
        "emailVerified": False,
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow(),
    }
    user.update(overrides)
    return user


def create_test_tournament():
    """Create a test tournament document"""
    return {
        "_id": str(ObjectId()),
        "name": "Test League",
        "alias": "test-league",
        "published": True
    }


def create_test_season():
    """Create a test season document"""
    return {
        "_id": str(ObjectId()),
        "name": "2024",
        "alias": "2024",
        "published": True
    }


def create_test_team(team_id=None):
    """Create a test team document"""
    team_id = team_id or str(ObjectId())
    return {
        "_id": team_id,
        "teamId": team_id,
        "name": f"Team {team_id[:4]}",
        "fullName": f"Test Team {team_id[:4]}",
        "shortName": f"TT{team_id[:2]}",
        "tinyName": f"T{team_id[:1]}",
        "clubId": str(ObjectId()),
        "clubName": "Test Club",
        "clubAlias": "test-club",
        "published": True,
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow(),
    }


def create_test_match(match_id=None, status="SCHEDULED"):
    """Create a test match document with valid ObjectId and all required fields"""
    # Use valid ObjectId string
    match_id = match_id or str(ObjectId())

    return {
        "_id": match_id,
        "matchId": fake.random_int(1000, 9999),
        "tournament": {
            "name": "Test League",
            "alias": "test-league"
        },
        "season": {
            "name": "2024",
            "alias": "2024"
        },
        "round": {
            "name": "Hauptrunde",
            "alias": "hauptrunde"
        },
        "matchday": {
            "name": "1. Spieltag",
            "alias": "1"
        },
        "matchStatus": {
            "key": status,
            "value": "angesetzt" if status == "SCHEDULED" else "beendet"
        },
        "finishType": {
            "key": "REGULAR",
            "value": "Regulär"
        },
        "startDate": datetime.now() + timedelta(days=7),
        "venue": {
            "venueId": str(ObjectId()),
            "name": "Test Arena",
            "alias": "test-arena"
        },
        "home": {
            "clubId": str(ObjectId()),
            "clubName": "Home Club",
            "clubAlias": "home-club",
            "teamId": str(ObjectId()),
            "teamAlias": "home-team",
            "name": "Home Team",
            "fullName": "Home Team Full Name",
            "shortName": "HOME",
            "tinyName": "HOM",
            "logo": None,
            "roster": [],
            "rosterPublished": False,
            "coach": {
                "firstName": None,
                "lastName": None,
                "licence": None
            },
            "staff": [],
            "scores": [],
            "penalties": [],
            "stats": {
                "gamePlayed": 0,
                "goalsFor": 0,
                "goalsAgainst": 0,
                "points": 0,
                "win": 0,
                "loss": 0,
                "draw": 0,
                "otWin": 0,
                "otLoss": 0,
                "soWin": 0,
                "soLoss": 0
            }
        },
        "away": {
            "clubId": str(ObjectId()),
            "clubName": "Away Club",
            "clubAlias": "away-club",
            "teamId": str(ObjectId()),
            "teamAlias": "away-team",
            "name": "Away Team",
            "fullName": "Away Team Full Name",
            "shortName": "AWAY",
            "tinyName": "AWY",
            "logo": None,
            "roster": [],
            "rosterPublished": False,
            "coach": {
                "firstName": None,
                "lastName": None,
                "licence": None
            },
            "staff": [],
            "scores": [],
            "penalties": [],
            "stats": {
                "gamePlayed": 0,
                "goalsFor": 0,
                "goalsAgainst": 0,
                "points": 0,
                "win": 0,
                "loss": 0,
                "draw": 0,
                "otWin": 0,
                "otLoss": 0,
                "soWin": 0,
                "soLoss": 0
            }
        },
        "referee1": None,
        "referee2": None,
        "published": False,
        "matchSheetComplete": False,
        "supplementarySheet": {
            "refereeAttendance": None,
            "referee1Present": False,
            "referee2Present": False,
            "referee1PassAvailable": False,
            "referee2PassAvailable": False,
            "referee1PassNo": None,
            "referee2PassNo": None,
            "referee1DelayMin": 0,
            "referee2DelayMin": 0,
            "timekeeper1": None,
            "timekeeper2": None,
            "technicalDirector": None,
            "usageApproval": False,
            "ruleBook": False,
            "goalDisplay": False,
            "soundSource": False,
            "matchClock": False,
            "matchBalls": False,
            "firstAidKit": False,
            "fieldLines": False,
            "nets": False,
            "homeRoster": False,
            "homePlayerPasses": False,
            "homeUniformPlayerClothing": False,
            "awayRoster": False,
            "awayPlayerPasses": False,
            "awayUniformPlayerClothing": False,
            "awaySecondJerseySet": False,
            "refereePayment": {
                "referee1": {
                    "travelExpenses": 0.0,
                    "expenseAllowance": 0.0,
                    "gameFees": 0.0
                },
                "referee2": {
                    "travelExpenses": 0.0,
                    "expenseAllowance": 0.0,
                    "gameFees": 0.0
                }
            },
            "specialEvents": False,
            "refereeComments": None,
            "crowd": 0,
            "isSaved": False
        }
    }


def create_test_player(test_id: str = None, **overrides) -> Dict[str, Any]:
    """Create a test player document"""
    test_id = test_id or generate_test_id()
    player = {
        "test_id": test_id,
        "_id": f"player_{test_id}",
        "playerId": f"player_{test_id}",
        "firstName": "Test",
        "lastName": "Player",
        "playerNumber": hash(test_id) % 100,
        "sex": "M",
        "published": True,
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow(),
    }
    player.update(overrides)
    return player


def create_test_club(test_id: str = None, **overrides) -> Dict[str, Any]:
    """Create a test club document"""
    test_id = test_id or generate_test_id()
    club = {
        "test_id": test_id,
        "_id": f"club_{test_id}",
        "clubId": f"club_{test_id}",
        "clubName": f"Test Club {test_id}",
        "clubAlias": f"test-club-{test_id}",
        "published": True,
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow(),
    }
    club.update(overrides)
    return club