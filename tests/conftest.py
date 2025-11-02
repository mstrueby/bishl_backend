
"""
Shared pytest fixtures for all tests.
This file is automatically loaded by pytest.
"""
import asyncio
import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from httpx import AsyncClient
from main import app
from tests.test_config import TestSettings

# Override app settings for testing
app.state.settings = TestSettings()


@pytest_asyncio.fixture(scope="function")
async def mongodb():
    """MongoDB client for testing"""
    settings = TestSettings()
    client = AsyncIOMotorClient(settings.DB_URL)
    db = client[settings.DB_NAME]
    
    # Drop all collections before tests for clean slate
    for collection_name in await db.list_collection_names():
        await db[collection_name].drop()
    
    # TODO: Create indexes here if needed
    # from scripts.create_indexes import create_indexes
    # await create_indexes(db)
    
    yield db
    
    # Cleanup after all tests (optional - comment out to inspect data)
    # await client.drop_database(settings.DB_NAME)
    client.close()


@pytest_asyncio.fixture
async def client(mongodb):
    """HTTP client for API testing"""
    app.state.mongodb = mongodb
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def admin_token(mongodb):
    """Generate admin authentication token"""
    from authentication import AuthHandler
    
    auth = AuthHandler()
    
    # Create a mock admin user
    class MockUser:
        def __init__(self):
            self.id = "test-admin-id"
            self.roles = ["ADMIN", "REF_ADMIN"]
            self.email = "admin@test.com"
            self.clubId = "test-club-id"
            self.clubName = "Test Club"
    
    mock_user = MockUser()
    user_dict = {
        "_id": mock_user.id,
        "roles": mock_user.roles,
        "firstName": "Test",
        "lastName": "Admin",
        "club": {
            "clubId": mock_user.clubId,
            "clubName": mock_user.clubName
        }
    }
    
    return auth.encode_token(user_dict)


@pytest_asyncio.fixture
async def clean_collections(mongodb):
    """Clean specific collections before each test"""
    async def _clean(*collection_names):
        for name in collection_names:
            await mongodb[name].delete_many({})
    return _clean
