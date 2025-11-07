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

# Configure pytest-asyncio to use function-scoped event loops
pytest_plugins = ('pytest_asyncio',)

# CRITICAL: Force pytest to use .env.test BEFORE importing any settings
# This must happen before any Settings objects are created
os.environ["ENV_FILE"] = ".env.test"
os.environ["DB_NAME"] = "bishl_test"
os.environ["DB_URL"] = "mongodb+srv://test_user:YmIjOnKWuHcsvVbI@mflix.fmroc7j.mongodb.net/?retryWrites=true&w=majority&appName=mflix"
os.environ["ENVIRONMENT"] = "test"

from main import app
from tests.test_config import TestSettings


@pytest.fixture(scope="function")
def event_loop():
    """Create a new event loop for each test function."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


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
    """MongoDB client for testing - function scoped for fresh connection per test"""
    settings = TestSettings()
    client = AsyncIOMotorClient(settings.DB_URL)
    db = client[settings.DB_NAME]

    # CRITICAL: Verify we're using the correct test database
    actual_db_name = db.name
    assert actual_db_name == "bishl_test", f"❌ SAFETY CHECK FAILED: Expected 'bishl_test' but got '{actual_db_name}'"

    print(f"✅ Verified test database: {actual_db_name}")

    # Clean before test
    collections_to_clean = ["users", "matches", "assignments", "teams", "clubs", "tournaments"]
    for collection_name in collections_to_clean:
        try:
            await db[collection_name].delete_many({})
        except Exception as e:
            print(f"Warning: Could not clean {collection_name}: {e}")

    yield db

    # Clean after test
    for collection_name in collections_to_clean:
        try:
            await db[collection_name].delete_many({})
        except Exception as e:
            print(f"Warning: Could not cleanup {collection_name}: {e}")

    # Close client to prevent event loop issues
    client.close()


@pytest_asyncio.fixture
async def client(mongodb):
    """HTTP client for API testing"""
    settings = TestSettings()

    # CRITICAL SAFETY CHECK: Verify test database
    assert mongodb.name == "bishl_test", f"❌ SAFETY: Client using wrong database: {mongodb.name}"

    # CRITICAL: Create a NEW Motor client bound to the CURRENT event loop
    # This prevents "Event loop is closed" errors when tests run in sequence
    import asyncio
    loop = asyncio.get_event_loop()
    fresh_client = AsyncIOMotorClient(settings.DB_URL)
    fresh_db = fresh_client[settings.DB_NAME]
    
    # Override the app's database connection with fresh client
    app.state.mongodb = fresh_db
    app.state.settings = settings

    print(f"✅ Client using fresh Motor client for database: {fresh_db.name}")

    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
    
    # Cleanup: Close the Motor client and clear app state
    fresh_client.close()
    app.state.mongodb = None


@pytest_asyncio.fixture
async def admin_token(mongodb):
    """Generate admin token for testing"""
    from authentication import AuthHandler
    from bson import ObjectId

    auth = AuthHandler()

    # IMPORTANT: Generate ObjectId and convert to string for MongoDB
    admin_id = ObjectId()
    admin_user = {
        "_id": str(admin_id),  # MongoDB stores as string
        "email": "admin@test.com",
        "password": auth.get_password_hash("admin123"),
        "roles": ["ADMIN", "REF_ADMIN"],
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
async def create_test_user(mongodb):
    """Helper to create test users directly in DB (faster than API calls)"""
    from authentication import AuthHandler
    from bson import ObjectId

    auth = AuthHandler()

    async def _create(email: str, password: str, roles: list = None, **kwargs):
        """Create a user directly in the database"""
        user_id = str(ObjectId())
        user_doc = {
            "_id": user_id,
            "email": email,
            "password": auth.get_password_hash(password),
            "roles": roles or [],
            "firstName": kwargs.get("firstName", "Test"),
            "lastName": kwargs.get("lastName", "User"),
            "club": kwargs.get("club"),
        }

        # Clean up existing user with same email
        await mongodb["users"].delete_many({"email": email})
        await mongodb["users"].insert_one(user_doc)

        return user_id

    return _create


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