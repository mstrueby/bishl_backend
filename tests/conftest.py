
"""
Shared pytest fixtures for all tests.
This file is automatically loaded by pytest.
"""
import asyncio
import pytest
import pytest_asyncio
from contextlib import asynccontextmanager
from motor.motor_asyncio import AsyncIOMotorClient
from httpx import AsyncClient
from main import app
from tests.test_config import TestSettings

# Override app settings for testing
app.state.settings = TestSettings()

# Override the lifespan to prevent production DB connection during tests
@asynccontextmanager
async def test_lifespan(app):
    """Test lifespan that doesn't connect to production database"""
    print(f"\n🧪 Test mode: Skipping production database connection")
    yield
    # No cleanup needed - handled by fixtures

# Replace the app's lifespan with test version
app.router.lifespan_context = test_lifespan


@pytest_asyncio.fixture(scope="session", autouse=True)
async def cleanup_before_session():
    """Clean database once before all tests in the session"""
    settings = TestSettings()
    print(f"\n🔧 Using test database: {settings.DB_NAME} at {settings.DB_URL}")
    client = AsyncIOMotorClient(settings.DB_URL)
    db = client[settings.DB_NAME]
    
    # Drop all collections at the start of test session
    collections = await db.list_collection_names()
    for collection_name in collections:
        await db[collection_name].drop()
    
    print(f"🧹 Cleaned {len(collections)} collections from {settings.DB_NAME} before test session\n")
    
    client.close()
    yield


@pytest_asyncio.fixture(scope="function")
async def mongodb():
    """MongoDB client for testing - uses bishl_test database"""
    settings = TestSettings()
    client = AsyncIOMotorClient(settings.DB_URL)
    db = client[settings.DB_NAME]
    
    # Verify we're using the test database
    print(f"📊 Test using database: {settings.DB_NAME}")
    
    # NOTE: Collections are NOT dropped automatically
    # This allows inspecting test data after execution
    # To manually clean before running tests, use: make clean-test-db
    
    # TODO: Create indexes here if needed
    # from scripts.create_indexes import create_indexes
    # await create_indexes(db)
    
    yield db
    
    # DO NOT cleanup after tests - keep data for inspection
    client.close()


@pytest_asyncio.fixture
async def client(mongodb):
    """HTTP client for API testing"""
    settings = TestSettings()
    
    # Override the app's database connection with test database
    app.state.mongodb = mongodb
    app.state.settings = settings
    
    print(f"🔌 Client fixture using database: {settings.DB_NAME}")
    
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


@pytest_asyncio.fixture
async def test_isolation(mongodb):
    """
    Provides test isolation by tracking created documents and cleaning them up.
    Usage:
        async def test_example(test_isolation):
            # Create test data with test_id
            match_id = await test_isolation.create("matches", {"test_id": test_isolation.id, ...})
            # Test runs...
            # Auto cleanup happens after test
    """
    import uuid
    
    class TestIsolation:
        def __init__(self, db):
            self.db = db
            self.id = f"test_{uuid.uuid4().hex[:8]}"
            self.created_docs = []  # Track (collection, filter) for cleanup
        
        async def create(self, collection: str, document: dict):
            """Create a document and track it for cleanup"""
            document["test_id"] = self.id
            result = await self.db[collection].insert_one(document)
            self.created_docs.append((collection, {"_id": result.inserted_id}))
            return result.inserted_id
        
        async def cleanup(self):
            """Clean up all created documents"""
            for collection, filter_dict in reversed(self.created_docs):
                await self.db[collection].delete_many(filter_dict)
            
            # Also clean by test_id as fallback
            for collection_name in await self.db.list_collection_names():
                await self.db[collection_name].delete_many({"test_id": self.id})
    
    isolation = TestIsolation(mongodb)
    yield isolation
    
    # Cleanup after test
    await isolation.cleanup()
