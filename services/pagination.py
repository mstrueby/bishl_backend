"""
Pagination utilities for API responses.

Provides helpers for paginating database queries and creating standardized
paginated responses.
"""

from typing import Any, TypeVar

from motor.motor_asyncio import AsyncIOMotorCollection
from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginationMetadata(BaseModel):
    """Metadata about pagination state"""

    page: int = Field(..., description="Current page number (1-indexed)")
    page_size: int = Field(..., description="Number of items per page")
    total_items: int = Field(..., description="Total number of items across all pages")
    total_pages: int = Field(..., description="Total number of pages")
    has_next: bool = Field(..., description="Whether there is a next page")
    has_prev: bool = Field(..., description="Whether there is a previous page")


class PaginationHelper:
    """Helper class for database query pagination"""

    @staticmethod
    async def paginate_query(
        collection: AsyncIOMotorCollection,
        query: dict[str, Any],
        page: int,
        page_size: int,
        sort: list[tuple[str, int]] | None = None,
        projection: dict[str, int] | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """
        Paginate a MongoDB query.

        Args:
            collection: MongoDB collection to query
            query: MongoDB query filter
            page: Page number (1-indexed)
            page_size: Number of items per page
            sort: Optional list of (field, direction) tuples for sorting
            projection: Optional MongoDB projection specification

        Returns:
            Tuple of (items, total_count)
        """
        skip = (page - 1) * page_size

        # Get total count
        total_count = await collection.count_documents(query)

        # Get paginated items
        cursor = collection.find(query, projection).skip(skip).limit(page_size)

        if sort:
            cursor = cursor.sort(sort)

        items = await cursor.to_list(length=page_size)

        return items, total_count

    @staticmethod
    def create_response(
        items: list[Any],
        page: int,
        page_size: int,
        total_count: int,
        message: str = "Items retrieved successfully",
    ) -> dict:
        """
        Create a standardized paginated response.

        Args:
            items: List of items for current page
            page: Current page number
            page_size: Items per page
            total_count: Total number of items
            message: Success message

        Returns:
            Dictionary with standardized pagination response format
        """
        total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 0

        return {
            "success": True,
            "data": items,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_items": total_count,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
            },
            "message": message,
        }
