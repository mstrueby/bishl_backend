"""
Custom Exception Classes for BISHL Backend

Provides a hierarchy of exceptions for better error handling and consistent error responses.
All custom exceptions inherit from BISHLException which includes status codes and details.
"""

import uuid
from datetime import datetime
from typing import Any


class BISHLException(Exception):
    """Base exception for all BISHL errors"""

    def __init__(self, message: str, status_code: int = 500, details: dict[Any, Any] | None = None):
        """
        Args:
            message: Human-readable error message
            status_code: HTTP status code for the error
            details: Additional context as a dictionary
        """
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class ResourceNotFoundException(BISHLException):
    """Raised when a requested resource doesn't exist"""

    def __init__(
        self, resource_type: str, resource_id: str = "", details: dict[Any, Any] | None = None
    ):
        """
        Args:
            resource_type: Type of resource (e.g., 'Match', 'Player', 'Tournament')
            resource_id: ID of the missing resource
            details: Additional context

        Example:
            raise ResourceNotFoundException('Match', match_id, {'team_flag': 'home'})
        """
        message = f"{resource_type} with resource ID '{resource_id}' not found"
        extra_details = {"resource_type": resource_type, "resource_id": resource_id}
        if details:
            extra_details.update(details)
        super().__init__(message, status_code=404, details=extra_details)


class ValidationException(BISHLException):
    """Raised when input validation fails"""

    def __init__(self, field: str, message: str, details: dict[Any, Any] | None = None):
        """
        Args:
            field: Name of the field that failed validation
            message: Description of the validation error
            details: Additional context

        Example:
            raise ValidationException('email', 'Invalid email format', {'value': user_input})
        """
        full_message = f"Validation error on field '{field}': {message}"
        extra_details = {"field": field}
        if details:
            extra_details.update(details)
        super().__init__(full_message, status_code=400, details=extra_details)


class DatabaseOperationException(BISHLException):
    """Raised when database operations fail"""

    def __init__(
        self,
        operation: str,
        message: str = "",
        collection: str = "",
        details: dict[Any, Any] | None = None,
    ):
        """
        Args:
            operation: Type of operation (e.g., 'insert', 'update', 'delete', 'find')
            message: Description of the database error
            collection: Name of the collection
            details: Additional context (e.g., query, error message)

        Example:
            raise DatabaseOperationException('update', 'matches', {'match_id': match_id, 'error': str(e)})
        """
        self.operation = operation
        self.collection = collection
        self.details = details or {}
        self.correlation_id = str(uuid.uuid4())
        self.timestamp = datetime.utcnow().isoformat()

        error_message = message or f"Database operation '{operation}' failed"
        if collection and not message:
            error_message += f" on collection '{collection}'"

        super().__init__(error_message)


class StatsCalculationException(BISHLException):
    """Raised when stats calculation fails"""

    def __init__(
        self, calculation_type: str, message: str = "", details: dict[Any, Any] | None = None
    ):
        """
        Args:
            calculation_type: Type of stats being calculated (e.g., 'roster', 'standings', 'match')
            message: Description of the calculation error
            details: Additional context

        Example:
            raise StatsCalculationException('roster', 'Missing penalty data', {'match_id': match_id})
        """
        full_message = f"Stats calculation failed for '{calculation_type}': {message}"
        extra_details = {"calculation_type": calculation_type}
        if details:
            extra_details.update(details)
        super().__init__(full_message, status_code=500, details=extra_details)


class AuthenticationException(BISHLException):
    """Raised when authentication fails"""

    def __init__(
        self, message: str = "Authentication failed", details: dict[Any, Any] | None = None
    ):
        """
        Args:
            message: Description of the authentication error
            details: Additional context

        Example:
            raise AuthenticationException('Invalid credentials')
        """
        super().__init__(message, status_code=401, details=details)


class AuthorizationException(BISHLException):
    """Raised when user lacks permission for an action"""

    def __init__(
        self, message: str = "Insufficient permissions", details: dict[Any, Any] | None = None
    ):
        """
        Args:
            message: Description of the authorization error
            details: Additional context (e.g., required role, user role)

        Example:
            raise AuthorizationException('Admin role required', {'user_role': 'USER', 'required_role': 'ADMIN'})
        """
        super().__init__(message, status_code=403, details=details)


class ExternalServiceException(BISHLException):
    """Raised when external service calls fail"""

    def __init__(self, service_name: str, message: str, details: dict[Any, Any] | None = None):
        """
        Args:
            service_name: Name of the external service
            message: Description of the error
            details: Additional context (e.g., status code, response)

        Example:
            raise ExternalServiceException('BE_API', 'Failed to fetch penalty sheet', {'status_code': 500})
        """
        full_message = f"External service '{service_name}' error: {message}"
        extra_details = {"service_name": service_name}
        if details:
            extra_details.update(details)
        super().__init__(full_message, status_code=502, details=extra_details)
