
"""Sample data fixtures for testing"""
from faker import Faker
from datetime import datetime, timedelta
from bson import ObjectId

fake = Faker()


def create_test_tournament():
    """Create a test tournament document"""
    return {
        "_id": "test-tournament",
        "name": "Test League",
        "alias": "test-league",
        "tinyName": "TL",
        "published": True
    }


def create_test_season(tournament_alias="test-league"):
    """Create a test season document"""
    return {
        "alias": "2024",
        "year": 2024,
        "published": True,
        "isCurrent": True
    }


def create_test_team(team_id=None):
    """Create a test team document"""
    return {
        "_id": team_id or str(ObjectId()),
        "name": fake.company(),
        "alias": fake.slug(),
        "clubId": "test-club-id",
        "ageGroup": {"key": "U15", "label": "U15"}
    }


def create_test_player(player_id=None):
    """Create a test player document"""
    return {
        "_id": player_id or str(ObjectId()),
        "firstName": fake.first_name(),
        "lastName": fake.last_name(),
        "alias": fake.user_name(),
        "jersey": fake.random_int(1, 99),
        "sex": "MALE",
        "email": fake.email(),
        "published": True
    }


def create_test_match(match_id=None, status="SCHEDULED"):
    """Create a test match document"""
    match_id = match_id or str(ObjectId())
    
    return {
        "_id": match_id,
        "matchId": fake.random_int(1000, 9999),
        "tournament": {"alias": "test-league"},
        "season": {"alias": "2024"},
        "round": {"alias": "hauptrunde"},
        "matchday": {"alias": "1"},
        "matchStatus": {"key": status},
        "finishType": {"key": "REGULAR"},
        "matchDate": datetime.now() + timedelta(days=7),
        "venue": {"name": "Test Arena"},
        "home": {
            "team": create_test_team("home-team-id"),
            "scores": [],
            "penalties": [],
            "roster": [],
            "stats": {}
        },
        "away": {
            "team": create_test_team("away-team-id"),
            "scores": [],
            "penalties": [],
            "roster": [],
            "stats": {}
        }
    }


def create_test_roster_player(player_id=None):
    """Create a roster entry"""
    return {
        "_id": str(ObjectId()),
        "player": create_test_player(player_id),
        "goals": 0,
        "assists": 0,
        "points": 0,
        "pim": 0
    }
