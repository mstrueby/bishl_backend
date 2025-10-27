
"""
Pagination Helper Utilities

Provides utilities for paginating database queries and creating paginated responses.
"""

from typing import List, TypeVar, Type
from motor.motor_asyncio import AsyncIOMotorCollection
from models.responses import PaginatedResponse, PaginationMetadata

T = TypeVar('T')


class PaginationHelper:
    """Helper class for paginating database queries"""
    
    @staticmethod
    def validate_params(page: int = 1, page_size: int = 10, max_page_size: int = 100):
        """
        Validate and normalize pagination parameters
        
        Args:
            page: Page number (1-indexed)
            page_size: Number of items per page
            max_page_size: Maximum allowed page size
            
        Returns:
            Tuple of (page, page_size)
        """
        # Ensure page is at least 1
        page = max(1, page)
        
        # Ensure page_size is between 1 and max_page_size
        page_size = max(1, min(page_size, max_page_size))
        
        return page, page_size
    
    @staticmethod
    def calculate_skip(page: int, page_size: int) -> int:
        """Calculate MongoDB skip value from page number"""
        return (page - 1) * page_size
    
    @staticmethod
    async def paginate_query(
        collection: AsyncIOMotorCollection,
        query: dict,
        page: int = 1,
        page_size: int = 10,
        sort: list = None,
        projection: dict = None
    ) -> tuple[List[dict], int]:
        """
        Execute a paginated query on a MongoDB collection
        
        Args:
            collection: MongoDB collection to query
            query: MongoDB query filter
            page: Page number (1-indexed)
            page_size: Number of items per page
            sort: MongoDB sort specification
            projection: MongoDB projection specification
            
        Returns:
            Tuple of (items, total_count)
        """
        # Validate pagination params
        page, page_size = PaginationHelper.validate_params(page, page_size)
        
        # Count total matching documents
        total_count = await collection.count_documents(query)
        
        # Build query cursor
        cursor = collection.find(query, projection)
        
        # Apply sorting if specified
        if sort:
            cursor = cursor.sort(sort)
        
        # Apply pagination
        skip = PaginationHelper.calculate_skip(page, page_size)
        cursor = cursor.skip(skip).limit(page_size)
        
        # Execute query
        items = await cursor.to_list(length=page_size)
        
        return items, total_count
    
    @staticmethod
    def create_response(
        items: List[T],
        page: int,
        page_size: int,
        total_count: int,
        message: str = None
    ) -> PaginatedResponse[T]:
        """
        Create a standardized paginated response
        
        Args:
            items: List of items for current page
            page: Current page number
            page_size: Items per page
            total_count: Total number of items
            message: Optional success message
            
        Returns:
            PaginatedResponse object
        """
        pagination = PaginationMetadata.from_query(page, page_size, total_count)
        
        return PaginatedResponse(
            success=True,
            data=items,
            pagination=pagination,
            message=message
        )
