"""
Test Safety Utilities

Provides utilities to ensure tests never accidentally run against production databases.
"""

import os


def verify_test_environment():
    """
    Verify we're in a test environment before running tests.
    Raises assertion error if running against production.
    """
    # Check environment variable
    db_name = os.getenv("DB_NAME", "")

    # CRITICAL: Ensure we're not using production database
    assert db_name != "bishl", "❌ CRITICAL: Cannot run tests against production database 'bishl'"
    assert db_name == "bishl_test", f"❌ Expected 'bishl_test' but DB_NAME is '{db_name}'"

    print(f"✅ Environment safety verified: {db_name}")


def get_safe_test_db_name():
    """Get the test database name with safety checks"""
    db_name = os.getenv("DB_NAME", "bishl_test")

    # Ensure it's a test database
    assert "test" in db_name.lower(), f"Database name must contain 'test': {db_name}"

    return db_name
