"""
Standard Response Models

Provides consistent response wrappers for all API endpoints.
Includes pagination support and metadata.
"""

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class PaginationMetadata(BaseModel):
    """Pagination information for list responses"""

    page: int = Field(description="Current page number (1-indexed)")
    page_size: int = Field(description="Number of items per page")
    total_items: int = Field(description="Total number of items available")
    total_pages: int = Field(description="Total number of pages")
    has_next: bool = Field(description="Whether there is a next page")
    has_prev: bool = Field(description="Whether there is a previous page")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "page": 1,
                "page_size": 10,
                "total_items": 25,
                "total_pages": 3,
                "has_next": True,
                "has_prev": False,
            }
        }
    )

    @classmethod
    def from_query(cls, page: int, page_size: int, total_items: int) -> "PaginationMetadata":
        """Create pagination metadata from query parameters"""
        total_pages = (total_items + page_size - 1) // page_size if page_size > 0 else 0

        return cls(
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        )


class StandardResponse[T](BaseModel):
    """Standard response wrapper for single resource"""

    success: bool = Field(default=True, description="Whether the operation was successful")
    data: T | None = Field(description="Response data")
    message: str | None = Field(default=None, description="Optional success message")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "data": {"id": "123", "name": "Example"},
                "message": "Resource retrieved successfully",
            }
        }
    )


class PaginatedResponse[T](BaseModel):
    """Standard response wrapper for paginated lists"""

    success: bool = Field(default=True, description="Whether the operation was successful")
    data: list[T] = Field(description="List of items")
    pagination: PaginationMetadata = Field(description="Pagination information")
    message: str | None = Field(default=None, description="Optional success message")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "data": [{"id": "1", "name": "Item 1"}, {"id": "2", "name": "Item 2"}],
                "pagination": {
                    "page": 1,
                    "page_size": 10,
                    "total_items": 25,
                    "total_pages": 3,
                    "has_next": True,
                    "has_prev": False,
                },
                "message": "Resources retrieved successfully",
            }
        }
    )


class DeleteResponse(BaseModel):
    """Standard response for delete operations"""

    success: bool = Field(default=True, description="Whether the deletion was successful")
    deleted_count: int = Field(description="Number of items deleted")
    message: str | None = Field(default=None, description="Optional success message")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "deleted_count": 1,
                "message": "Resource deleted successfully",
            }
        }
    )


class BulkOperationResponse(BaseModel):
    """Standard response for bulk operations"""

    success: bool = Field(default=True, description="Whether the operation was successful")
    processed_count: int = Field(description="Number of items processed")
    success_count: int = Field(description="Number of items successfully processed")
    error_count: int = Field(description="Number of items that failed")
    errors: list[dict] | None = Field(default=None, description="List of errors if any")
    message: str | None = Field(default=None, description="Optional success message")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "processed_count": 10,
                "success_count": 9,
                "error_count": 1,
                "errors": [{"item_id": "5", "error": "Validation failed"}],
                "message": "Bulk operation completed with some errors",
            }
        }
    )