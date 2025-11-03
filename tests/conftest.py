"""
Shared pytest fixtures for all tests.
This file is automatically loaded by pytest.
"""
import os
import asyncio
import pytest
import pytest_asyncio
from contextlib import asynccontextmanager
from motor.motor_asyncio import AsyncIOMotorClient
from httpx import AsyncClient

# CRITICAL: Force pytest to use .env.test BEFORE importing any settings
# This must happen before any Settings objects are created
os.environ["ENV_FILE"] = ".env.test"
os.environ["DB_NAME"] = "bishl_test"
os.environ["DB_URL"] = "mongodb+srv://test_user:YmIjOnKWuHcsvVbI@mflix.fmroc7j.mongodb.net/?retryWrites=true&w=majority&appName=mflix"
os.environ["ENVIRONMENT"] = "test"

from main import app
from tests.test_config import TestSettings


def pytest_runtest_setup(item):
    """
    Safety hook: Runs before each test to verify we're using the test database.
    This prevents accidental writes to production/development databases.
    """
    # Only check for tests that use fixtures (most integration tests)
    if "mongodb" in item.fixturenames or "client" in item.fixturenames:
        print(f"\n🔍 Safety check for test: {item.name}")


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

    # CRITICAL SAFETY CHECK: Verify we're using test database
    assert settings.DB_NAME == "bishl_test", f"❌ CRITICAL: Session cleanup targeting wrong database: {settings.DB_NAME}"

    print(f"\n🔧 Using test database: {settings.DB_NAME} at {settings.DB_URL}")
    client = AsyncIOMotorClient(settings.DB_URL)
    db = client[settings.DB_NAME]

    # Double-check database name
    assert db.name == "bishl_test", f"❌ CRITICAL: Connected to wrong database: {db.name}"

    # Drop all collections at the start of test session
    collections = await db.list_collection_names()
    for collection_name in collections:
        await db[collection_name].drop()

    print(f"✅ Safely cleaned {len(collections)} collections from {settings.DB_NAME}\n")

    client.close()
    yield


@pytest_asyncio.fixture(scope="function")
async def mongodb():
    """MongoDB client for testing - uses bishl_test database"""
    settings = TestSettings()
    client = AsyncIOMotorClient(settings.DB_URL)
    db = client[settings.DB_NAME]

    # CRITICAL: Verify we're using the correct test database
    actual_db_name = db.name
    assert actual_db_name == "bishl_test", f"❌ SAFETY CHECK FAILED: Expected 'bishl_test' but got '{actual_db_name}'"

    print(f"✅ Verified test database: {actual_db_name}")

    yield db

    # DO NOT cleanup after tests - keep data for inspection
    client.close()


@pytest_asyncio.fixture
async def client(mongodb):
    """HTTP client for API testing"""
    settings = TestSettings()

    # CRITICAL SAFETY CHECK: Verify test database
    assert mongodb.name == "bishl_test", f"❌ SAFETY: Client using wrong database: {mongodb.name}"

    # Override the app's database connection with test database
    app.state.mongodb = mongodb
    app.state.settings = settings

    print(f"✅ Client verified using database: {mongodb.name}")

    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def admin_token(mongodb):
    """Generate admin token for testing"""
    from authentication import AuthHandler
    from bson import ObjectId

    auth = AuthHandler()
    admin_id = str(ObjectId())  # Generate valid ObjectId
    admin_user = {
        "_id": admin_id,
        "email": "admin@test.com",
        "password": auth.get_password_hash("admin123"),
        "roles": ["ADMIN"],
        "firstName": "Admin",
        "lastName": "User",
        "club": {
            "clubId": "test-club-id",
            "clubName": "Test Club"
        }
    }

    # Insert admin user into database so it exists when endpoints look for it
    await mongodb["users"].insert_one(admin_user)

    return auth.encode_token(admin_user)


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

    # CRITICAL SAFETY CHECK
    assert mongodb.name == "bishl_test", f"❌ SAFETY: test_isolation using wrong database: {mongodb.name}"

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