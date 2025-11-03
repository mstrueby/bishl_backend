"""
Centralized Import Service

Provides common functionality for all data import operations:
- Database connection management
- Authentication handling
- Error handling and rollback
- Progress tracking and logging
"""

import os
from collections.abc import Callable
from typing import Any

import certifi
import requests
from pymongo import MongoClient
from pymongo.database import Database

from config import settings
from logging_config import logger


class ImportService:
    """Unified service for data import operations"""

    def __init__(self, use_production: bool = False):
        """
        Initialize import service

        Args:
            use_production: If True, use production database and API
        """
        self.use_production = use_production
        self.client: MongoClient | None = None
        self.db: Database[Any] | None = None
        self.token: str | None = None
        self.headers: dict[str, str] | None = None

        # Set environment-specific URLs
        if use_production:
            self.db_url = os.environ["DB_URL_PROD"]
            self.db_name = "bishl"
            self.base_url = os.environ.get("BE_API_URL_PROD", settings.BE_API_URL)
        else:
            self.db_url = os.environ["DB_URL"]
            self.db_name = "bishl_dev"
            self.base_url = os.environ.get("BE_API_URL", settings.BE_API_URL)

        logger.info(
            f"Import Service initialized for {'PRODUCTION' if use_production else 'DEVELOPMENT'}"
        )
        logger.info(f"Database: {self.db_name}")
        logger.info(f"API URL: {self.base_url}")

    def connect_db(self) -> None:
        """Establish database connection"""
        try:
            self.client = MongoClient(self.db_url, tlsCAFile=certifi.where())
            self.db = self.client[self.db_name]
            logger.info("Database connection established")
        except Exception as e:
            logger.error(f"Failed to connect to database: {str(e)}")
            raise

    def authenticate(self) -> bool:
        """
        Authenticate with API and get token

        Returns:
            True if authentication successful, False otherwise
        """
        login_url = f"{self.base_url}/users/login"
        login_data = {
            "email": os.environ["SYS_ADMIN_EMAIL"],
            "password": os.environ["SYS_ADMIN_PASSWORD"],
        }

        try:
            response = requests.post(login_url, json=login_data)

            if response.status_code != 200:
                logger.error(f"Authentication failed: {response.text}")
                return False

            self.token = response.json()["access_token"]
            self.headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            }
            logger.info("Authentication successful")
            return True

        except Exception as e:
            logger.error(f"Authentication error: {str(e)}")
            return False

    def get_collection(self, collection_name: str):
        """Get a database collection"""
        if not self.db:
            raise RuntimeError("Database not connected. Call connect_db() first.")
        return self.db[collection_name]

    def import_with_rollback(
        self, import_func: Callable, collection_name: str, backup_before: bool = True
    ) -> tuple[bool, str]:
        """
        Execute import function with automatic rollback on failure

        Args:
            import_func: Function to execute (should return success boolean and message)
            collection_name: Name of collection being modified
            backup_before: Whether to backup collection before import

        Returns:
            Tuple of (success: bool, message: str)
        """
        collection = self.get_collection(collection_name)
        backup_data = None

        try:
            # Backup if requested
            if backup_before:
                logger.info(f"Backing up {collection_name} collection...")
                backup_data = list(collection.find())
                logger.info(f"Backed up {len(backup_data)} documents")

            # Execute import
            success, message = import_func()

            if success:
                logger.info(f"Import completed successfully: {message}")
                return True, message
            else:
                logger.warning(f"Import returned failure: {message}")
                return False, message

        except Exception as e:
            error_msg = f"Import failed with error: {str(e)}"
            logger.error(error_msg)

            # Rollback if we have backup
            if backup_data is not None:
                try:
                    logger.info("Rolling back changes...")
                    collection.delete_many({})
                    if backup_data:
                        collection.insert_many(backup_data)
                    logger.info("Rollback completed")
                    return False, f"{error_msg} (rolled back)"
                except Exception as rollback_error:
                    logger.error(f"Rollback failed: {str(rollback_error)}")
                    return False, f"{error_msg} (rollback failed: {str(rollback_error)})"

            return False, error_msg

    def close(self) -> None:
        """Close database connection"""
        if self.client:
            self.client.close()
            logger.info("Database connection closed")

    def __enter__(self):
        """Context manager entry"""
        self.connect_db()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()
        return False


class ImportProgress:
    """Track and log import progress"""

    def __init__(self, total: int, description: str = "Processing"):
        self.total = total
        self.current = 0
        self.description = description
        self.errors: list[str] = []

    def update(self, increment: int = 1, message: str | None = None):
        """Update progress counter"""
        self.current += increment
        percentage = (self.current / self.total * 100) if self.total > 0 else 0

        if message:
            logger.info(
                f"{self.description}: {self.current}/{self.total} ({percentage:.1f}%) - {message}"
            )
        elif self.current % max(1, self.total // 10) == 0:  # Log every 10%
            logger.info(f"{self.description}: {self.current}/{self.total} ({percentage:.1f}%)")

    def add_error(self, error: str):
        """Record an error"""
        self.errors.append(error)
        logger.warning(f"Error recorded: {error}")

    def summary(self) -> str:
        """Get progress summary"""
        success_count = self.current - len(self.errors)
        summary = f"Completed: {self.current}/{self.total} ({success_count} successful, {len(self.errors)} errors)"

        if self.errors:
            summary += "\nErrors:\n" + "\n".join(f"  - {err}" for err in self.errors[:10])
            if len(self.errors) > 10:
                summary += f"\n  ... and {len(self.errors) - 10} more errors"

        return summary
