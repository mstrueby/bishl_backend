
"""Test data fixtures and helper functions for creating test documents"""
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any


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


def create_test_match(test_id: str = None, **overrides) -> Dict[str, Any]:
    """Create a test match document"""
    test_id = test_id or generate_test_id()
    match = {
        "test_id": test_id,
        "_id": f"match_{test_id}",
        "matchNumber": 1000 + hash(test_id) % 1000,  # Unique match number
        "status": "SCHEDULED",
        "home": {
            "teamId": f"team_home_{test_id}",
            "teamName": "Home Team",
            "roster": [],
            "scores": [],
            "penalties": [],
            "stats": {"goals": 0, "assists": 0, "points": 0}
        },
        "away": {
            "teamId": f"team_away_{test_id}",
            "teamName": "Away Team",
            "roster": [],
            "scores": [],
            "penalties": [],
            "stats": {"goals": 0, "assists": 0, "points": 0}
        },
        "dateTime": datetime.utcnow() + timedelta(days=1),
        "venue": f"venue_{test_id}",
        "round": f"round_{test_id}",
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow(),
    }
    match.update(overrides)
    return match


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
