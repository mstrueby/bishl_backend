
# Testing Infrastructure Guide

## Overview

This document outlines the complete testing infrastructure for the BISHL backend API. The goal is to establish a robust, maintainable test suite that ensures code quality and prevents regressions.

---

## Concept & Architecture

### Testing Pyramid

```
                    /\
                   /  \
                  / E2E \
                 /______\
                /        \
               / Integration\
              /______________\
             /                \
            /   Unit Tests     \
           /____________________\
```

**Unit Tests (60%)**: Test individual functions in isolation
- Stats calculations
- Data transformations
- Validators
- Utility functions

**Integration Tests (30%)**: Test API endpoints with real database
- CRUD operations
- Authentication flows
- Database queries
- Business logic

**E2E Tests (10%)**: Test complete workflows
- Match creation → scoring → standings
- Referee assignment workflow
- Player stats aggregation

---

## Tools & Dependencies

### Core Testing Stack

```toml
[tool.poetry.group.test.dependencies]
pytest = "^7.4.0"
pytest-asyncio = "^0.21.0"
pytest-cov = "^4.1.0"
pytest-mock = "^3.12.0"
httpx = "^0.27.0"  # Already installed
faker = "^20.0.0"
freezegun = "^1.4.0"
```

### Purpose of Each Tool

- **pytest**: Main test framework
- **pytest-asyncio**: Support for async test functions
- **pytest-cov**: Code coverage reporting
- **pytest-mock**: Mocking and patching utilities
- **httpx**: HTTP client for API testing (already installed)
- **faker**: Generate realistic test data
- **freezegun**: Time manipulation for testing

---

## Project Structure

```
tests/
├── __init__.py
├── conftest.py                 # Shared fixtures
├── test_config.py              # Test configuration
│
├── unit/
│   ├── __init__.py
│   ├── test_stats_service.py
│   ├── test_authentication.py
│   ├── test_utils.py
│   └── test_validators.py
│
├── integration/
│   ├── __init__.py
│   ├── test_matches_api.py
│   ├── test_scores_api.py
│   ├── test_roster_api.py
│   ├── test_penalties_api.py
│   ├── test_players_api.py
│   ├── test_users_api.py
│   └── test_assignments_api.py
│
├── e2e/
│   ├── __init__.py
│   ├── test_match_workflow.py
│   ├── test_referee_workflow.py
│   └── test_standings_workflow.py
│
└── fixtures/
    ├── __init__.py
    ├── data_fixtures.py        # Sample data
    ├── db_fixtures.py           # Database setup
    └── auth_fixtures.py         # Auth tokens
```

---

## Database Setup

### Test Database Strategy

**Approach**: Use a separate test database that mirrors production structure

```python
# tests/test_config.py
import os
from config import Settings

class TestSettings(Settings):
    """Override settings for testing"""
    
    DB_NAME: str = "bishl_test"
    JWT_SECRET_KEY: str = "test-secret-key-do-not-use-in-production"
    JWT_REFRESH_SECRET_KEY: str = "test-refresh-secret-do-not-use-in-production"
    DEBUG_LEVEL: int = 0  # Suppress debug output in tests
    
    class Config:
        env_file = ".env.test"
```

### Database Lifecycle

**Per Test Session:**
1. Connect to test database
2. Drop all collections (clean slate)
3. Create indexes
4. Run tests
5. Optionally keep data for inspection

**Per Test Function:**
1. Insert test data (fixtures)
2. Run test
3. Clean up (optional - can use session cleanup)

---

## Fixtures Setup

### Base Fixtures (conftest.py)

```python
# tests/conftest.py
import asyncio
import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from httpx import AsyncClient
from main import app
from tests.test_config import TestSettings

# Override app settings for testing
app.state.settings = TestSettings()

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def mongodb():
    """MongoDB client for testing"""
    settings = TestSettings()
    client = AsyncIOMotorClient(settings.get_db_url())
    db = client[settings.DB_NAME]
    
    # Drop all collections before tests
    for collection_name in await db.list_collection_names():
        await db[collection_name].drop()
    
    # Create indexes
    # (Import and run create_indexes logic here)
    
    yield db
    
    # Cleanup after all tests (optional)
    # await client.drop_database(settings.DB_NAME)
    client.close()


@pytest.fixture
async def client(mongodb):
    """HTTP client for API testing"""
    app.state.mongodb = mongodb
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def admin_token():
    """Generate admin authentication token"""
    from authentication import AuthHandler
    
    auth = AuthHandler()
    token_payload = {
        "sub": "test-admin-id",
        "roles": ["ADMIN", "REF_ADMIN"],
        "email": "admin@test.com",
        "clubId": "test-club-id",
        "clubName": "Test Club"
    }
    
    # Create a mock user object
    class MockUser:
        def __init__(self):
            self.id = "test-admin-id"
            self.roles = ["ADMIN", "REF_ADMIN"]
            self.email = "admin@test.com"
            self.clubId = "test-club-id"
            self.clubName = "Test Club"
    
    return auth.encode_token(MockUser())


@pytest.fixture
async def clean_collections(mongodb):
    """Clean specific collections before each test"""
    async def _clean(*collection_names):
        for name in collection_names:
            await mongodb[name].delete_many({})
    return _clean
```

### Data Fixtures

```python
# tests/fixtures/data_fixtures.py
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
```

---

## Writing Tests

### Unit Test Example

```python
# tests/unit/test_stats_service.py
import pytest
from services.stats_service import StatsService

class TestStatsService:
    
    @pytest.fixture
    def stats_service(self, mongodb):
        return StatsService(mongodb)
    
    def test_calculate_match_stats_regular_win(self, stats_service):
        """Test match stats for regular time win"""
        result = stats_service.calculate_match_stats(
            match_status="FINISHED",
            finish_type="REGULAR",
            standings_settings={},
            home_score=5,
            away_score=3
        )
        
        assert result["home"]["points"] == 3  # Win = 3 points
        assert result["away"]["points"] == 0  # Loss = 0 points
        assert result["home"]["wins"] == 1
        assert result["away"]["losses"] == 1
    
    def test_calculate_match_stats_overtime_win(self, stats_service):
        """Test match stats for overtime win"""
        result = stats_service.calculate_match_stats(
            match_status="FINISHED",
            finish_type="OVERTIME",
            standings_settings={},
            home_score=4,
            away_score=3
        )
        
        assert result["home"]["points"] == 2  # OT win = 2 points
        assert result["away"]["points"] == 1  # OT loss = 1 point
        assert result["home"]["overtimeWins"] == 1
        assert result["away"]["overtimeLosses"] == 1
    
    @pytest.mark.asyncio
    async def test_calculate_roster_stats(self, stats_service, mongodb):
        """Test roster stats calculation from scores/penalties"""
        from tests.fixtures.data_fixtures import create_test_match
        
        # Insert test match with scores
        match = create_test_match(status="INPROGRESS")
        match["home"]["scores"] = [
            {
                "_id": "score-1",
                "goalPlayer": {"playerId": "player-1"},
                "assistPlayer": {"playerId": "player-2"}
            }
        ]
        match["home"]["roster"] = [
            {"_id": "r1", "player": {"playerId": "player-1"}, "goals": 0, "assists": 0},
            {"_id": "r2", "player": {"playerId": "player-2"}, "goals": 0, "assists": 0}
        ]
        
        await mongodb["matches"].insert_one(match)
        
        # Calculate stats
        await stats_service.calculate_roster_stats(match["_id"], "home")
        
        # Verify
        updated = await mongodb["matches"].find_one({"_id": match["_id"]})
        roster_by_id = {r["player"]["playerId"]: r for r in updated["home"]["roster"]}
        
        assert roster_by_id["player-1"]["goals"] == 1
        assert roster_by_id["player-1"]["points"] == 1
        assert roster_by_id["player-2"]["assists"] == 1
        assert roster_by_id["player-2"]["points"] == 1
```

### Integration Test Example

```python
# tests/integration/test_scores_api.py
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
class TestScoresAPI:
    
    async def test_create_score_success(self, client: AsyncClient, mongodb, admin_token):
        """Test creating a score during INPROGRESS match"""
        from tests.fixtures.data_fixtures import (
            create_test_match,
            create_test_roster_player
        )
        
        # Setup: Create match with roster
        match = create_test_match(status="INPROGRESS")
        player = create_test_roster_player("test-player-id")
        match["home"]["roster"] = [player]
        await mongodb["matches"].insert_one(match)
        
        # Execute: Create score
        score_data = {
            "matchTime": "10:30",
            "goalPlayer": {"playerId": "test-player-id"},
            "assistPlayer": None
        }
        
        response = await client.post(
            f"/matches/{match['_id']}/home/scores",
            json=score_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        # Assert: Response
        assert response.status_code == 201
        data = response.json()
        assert data["matchTime"] == "10:30"
        assert data["goalPlayer"]["playerId"] == "test-player-id"
        
        # Assert: Database updated
        updated_match = await mongodb["matches"].find_one({"_id": match["_id"]})
        assert len(updated_match["home"]["scores"]) == 1
        assert updated_match["home"]["stats"]["goalsFor"] == 1
    
    async def test_create_score_player_not_in_roster(
        self, client: AsyncClient, mongodb, admin_token
    ):
        """Test creating score with player not in roster fails"""
        from tests.fixtures.data_fixtures import create_test_match
        
        match = create_test_match(status="INPROGRESS")
        await mongodb["matches"].insert_one(match)
        
        score_data = {
            "matchTime": "10:30",
            "goalPlayer": {"playerId": "invalid-player-id"}
        }
        
        response = await client.post(
            f"/matches/{match['_id']}/home/scores",
            json=score_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 400
        assert "not in roster" in response.json()["error"]["message"]
    
    async def test_create_score_wrong_match_status(
        self, client: AsyncClient, mongodb, admin_token
    ):
        """Test creating score when match not INPROGRESS fails"""
        from tests.fixtures.data_fixtures import create_test_match
        
        match = create_test_match(status="SCHEDULED")
        await mongodb["matches"].insert_one(match)
        
        score_data = {"matchTime": "10:30"}
        
        response = await client.post(
            f"/matches/{match['_id']}/home/scores",
            json=score_data,
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        assert response.status_code == 400
        assert "INPROGRESS" in response.json()["error"]["message"]
```

### E2E Test Example

```python
# tests/e2e/test_match_workflow.py
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
class TestMatchWorkflow:
    
    async def test_complete_match_workflow(self, client: AsyncClient, mongodb, admin_token):
        """Test complete match flow: create → start → score → finish → standings"""
        from tests.fixtures.data_fixtures import (
            create_test_match,
            create_test_player,
            create_test_roster_player
        )
        
        # 1. Setup: Create match with roster
        match = create_test_match(status="SCHEDULED")
        player1 = create_test_player("player-1")
        player2 = create_test_player("player-2")
        await mongodb["players"].insert_many([player1, player2])
        
        match["home"]["roster"] = [
            create_test_roster_player("player-1"),
            create_test_roster_player("player-2")
        ]
        await mongodb["matches"].insert_one(match)
        match_id = match["_id"]
        
        # 2. Start match
        response = await client.patch(
            f"/matches/{match_id}",
            json={"matchStatus": {"key": "INPROGRESS"}},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        
        # 3. Add scores
        # Home scores 2 goals
        for i in range(2):
            response = await client.post(
                f"/matches/{match_id}/home/scores",
                json={
                    "matchTime": f"{i+5}:00",
                    "goalPlayer": {"playerId": "player-1"}
                },
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            assert response.status_code == 201
        
        # Away scores 1 goal
        response = await client.post(
            f"/matches/{match_id}/away/scores",
            json={"matchTime": "15:00"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 201
        
        # 4. Finish match
        response = await client.patch(
            f"/matches/{match_id}",
            json={
                "matchStatus": {"key": "FINISHED"},
                "finishType": {"key": "REGULAR"}
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        
        # 5. Verify match stats
        match_doc = await mongodb["matches"].find_one({"_id": match_id})
        assert match_doc["home"]["stats"]["goalsFor"] == 2
        assert match_doc["home"]["stats"]["points"] == 3  # Win
        assert match_doc["away"]["stats"]["goalsFor"] == 1
        assert match_doc["away"]["stats"]["points"] == 0  # Loss
        
        # 6. Verify roster stats
        home_roster = {r["player"]["playerId"]: r for r in match_doc["home"]["roster"]}
        assert home_roster["player-1"]["goals"] == 2
        assert home_roster["player-1"]["points"] == 2
        
        # 7. Verify player stats aggregated
        player1_doc = await mongodb["players"].find_one({"_id": "player-1"})
        # Check that stats were aggregated (implementation dependent)
```

---

## Running Tests

### Basic Commands

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific test file
pytest tests/unit/test_stats_service.py

# Run specific test
pytest tests/unit/test_stats_service.py::TestStatsService::test_calculate_match_stats_regular_win

# Run only unit tests
pytest tests/unit/

# Run only integration tests
pytest tests/integration/

# Run with verbose output
pytest -v

# Run and stop on first failure
pytest -x

# Run failed tests from last run
pytest --lf
```

### Makefile Integration

```makefile
# Add to makefile
.PHONY: test test-unit test-integration test-e2e test-cov

test:
	pytest -v

test-unit:
	pytest tests/unit/ -v

test-integration:
	pytest tests/integration/ -v

test-e2e:
	pytest tests/e2e/ -v

test-cov:
	pytest --cov=. --cov-report=html --cov-report=term
	@echo "Coverage report: htmlcov/index.html"

test-watch:
	pytest-watch
```

---

## Coverage Goals

### Target Coverage by Component

| Component | Target | Priority |
|-----------|--------|----------|
| services/stats_service.py | 90% | Critical |
| authentication.py | 85% | Critical |
| routers/matches.py | 80% | High |
| routers/scores.py | 80% | High |
| routers/roster.py | 75% | High |
| routers/penalties.py | 75% | High |
| utils.py | 70% | Medium |
| Other routers | 60% | Medium |

### Overall Target: 60%+ coverage on critical paths

---

## CI/CD Integration (Future)

### GitHub Actions Workflow

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      mongodb:
        image: mongo:7
        ports:
          - 27017:27017
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      
      - name: Install dependencies
        run: |
          pip install poetry
          poetry install
      
      - name: Run tests with coverage
        run: poetry run pytest --cov=. --cov-report=xml
        env:
          DB_URL: mongodb://localhost:27017
          DB_NAME: bishl_test
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

---

## Best Practices

### Test Naming Convention

```python
# Pattern: test_<function>_<scenario>_<expected_result>
def test_create_score_valid_data_returns_201()
def test_create_score_player_not_in_roster_returns_400()
def test_calculate_standings_tie_breaker_sorts_by_goals()
```

### AAA Pattern (Arrange-Act-Assert)

```python
async def test_example(self, client, mongodb):
    # Arrange: Setup test data
    match = create_test_match()
    await mongodb["matches"].insert_one(match)
    
    # Act: Execute the code under test
    response = await client.get(f"/matches/{match['_id']}")
    
    # Assert: Verify expectations
    assert response.status_code == 200
    assert response.json()["_id"] == match["_id"]
```

### Use Fixtures for Common Setup

```python
@pytest.fixture
async def match_with_roster(mongodb):
    """Reusable fixture for match with roster"""
    match = create_test_match(status="INPROGRESS")
    match["home"]["roster"] = [create_test_roster_player() for _ in range(5)]
    await mongodb["matches"].insert_one(match)
    return match

async def test_something(match_with_roster):
    # Use the fixture
    assert len(match_with_roster["home"]["roster"]) == 5
```

---

## Implementation Checklist

### Phase 1: Setup (4-6 hours)
- [ ] Install test dependencies: `poetry add --group test pytest pytest-asyncio pytest-cov faker`
- [ ] Create `tests/` directory structure
- [ ] Create `tests/conftest.py` with base fixtures
- [ ] Create `tests/test_config.py` with test settings
- [ ] Create `.env.test` file
- [ ] Add test commands to `makefile`

### Phase 2: Unit Tests (6-8 hours)
- [ ] Write tests for `StatsService` (15+ tests)
- [ ] Write tests for `AuthHandler` (10+ tests)
- [ ] Write tests for utility functions (10+ tests)
- [ ] Write tests for validators (5+ tests)
- [ ] Aim for 80%+ coverage on tested modules

### Phase 3: Integration Tests (8-10 hours)
- [ ] Create data fixtures in `tests/fixtures/`
- [ ] Write tests for matches API (10+ tests)
- [ ] Write tests for scores API (8+ tests)
- [ ] Write tests for roster API (6+ tests)
- [ ] Write tests for penalties API (6+ tests)
- [ ] Write tests for players API (6+ tests)
- [ ] Aim for 60%+ coverage on routers

### Phase 4: E2E Tests (4-6 hours)
- [ ] Write match workflow test (create → score → finish)
- [ ] Write referee assignment workflow test
- [ ] Write standings calculation workflow test
- [ ] Verify critical business logic end-to-end

### Phase 5: Documentation & Polish (2-4 hours)
- [ ] Add test documentation to README
- [ ] Create testing best practices guide
- [ ] Set up coverage reporting
- [ ] Review and refactor tests for clarity

**Total Estimated Time: 24-34 hours**

---

## Troubleshooting

### Common Issues

**Issue**: `RuntimeError: Event loop is closed`
```python
# Solution: Use proper async fixtures
@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
```

**Issue**: Tests interfere with each other
```python
# Solution: Clean database between tests
@pytest.fixture(autouse=True)
async def clean_db(mongodb):
    yield
    for collection in await mongodb.list_collection_names():
        await mongodb[collection].delete_many({})
```

**Issue**: Slow tests
```python
# Solution: Use session-scoped fixtures for expensive setup
@pytest.fixture(scope="session")
async def mongodb():
    # Setup once per session
    ...
```

---

## Success Metrics

After implementation, you should have:

✅ 100+ test cases covering critical functionality
✅ 60%+ overall code coverage
✅ 80%+ coverage on `StatsService` and `AuthHandler`
✅ All critical workflows tested end-to-end
✅ Tests run in < 30 seconds
✅ Clear test documentation
✅ Easy to add new tests

---

*Ready for implementation after completing Phase 1-5 of refactoring roadmap*
*Estimated total effort: 24-34 hours*
