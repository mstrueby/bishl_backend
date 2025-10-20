
# Error Handling Standardization Specification

*Created: 2025-01-XX*  
*Priority: Medium*  
*Estimated Effort: 8-12 hours*

---

## Executive Summary

Standardize error handling across the BISHL backend by creating custom exception classes, implementing centralized exception handlers, and adding structured logging. This will improve debugging, provide consistent error responses to clients, and make the codebase more maintainable.

---

## Current State Analysis

### Problems Identified

1. **Inconsistent HTTPException Usage**
   - Different status codes for similar errors across routers
   - Inconsistent error message formats
   - No standard error response structure

2. **Poor Error Context**
   - Generic error messages ("Failed to update", "Error occurred")
   - Missing context about what operation failed
   - No request correlation IDs for debugging

3. **No Centralized Error Logging**
   - Errors printed to console inconsistently
   - No structured logging format
   - Hard to trace errors across service boundaries

4. **Limited Error Recovery**
   - No graceful degradation
   - All errors result in 500 status codes
   - No retry logic for transient failures

### Examples of Current Issues

```python
# routers/matches.py - Generic error
raise HTTPException(status_code=500, detail="Failed to update tournament standings.")

# routers/roster.py - Inconsistent messaging
raise HTTPException(status_code=500, detail="Could not update roster in mongoDB")

# services/stats_service.py - Better but still generic
raise HTTPException(status_code=500, detail="Failed to calculate roster stats")
```

---

## Proposed Solution

### 1. Custom Exception Classes

Create a hierarchy of custom exceptions that capture domain-specific errors:

```python
# exceptions/custom_exceptions.py

class BISHLException(Exception):
    """Base exception for all BISHL errors"""
    def __init__(self, message: str, status_code: int = 500, details: dict = None):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)

class ResourceNotFoundException(BISHLException):
    """Raised when a requested resource doesn't exist"""
    def __init__(self, resource_type: str, resource_id: str, details: dict = None):
        message = f"{resource_type} with ID '{resource_id}' not found"
        super().__init__(message, status_code=404, details=details)

class ValidationException(BISHLException):
    """Raised when input validation fails"""
    def __init__(self, field: str, message: str, details: dict = None):
        full_message = f"Validation error on field '{field}': {message}"
        super().__init__(full_message, status_code=400, details=details)

class DatabaseOperationException(BISHLException):
    """Raised when database operations fail"""
    def __init__(self, operation: str, collection: str, details: dict = None):
        message = f"Database operation '{operation}' failed on collection '{collection}'"
        super().__init__(message, status_code=500, details=details)

class StatsCalculationException(BISHLException):
    """Raised when stats calculation fails"""
    def __init__(self, stats_type: str, entity_id: str, details: dict = None):
        message = f"Failed to calculate {stats_type} stats for {entity_id}"
        super().__init__(message, status_code=500, details=details)

class AuthenticationException(BISHLException):
    """Raised for authentication failures"""
    def __init__(self, message: str = "Authentication failed", details: dict = None):
        super().__init__(message, status_code=401, details=details)

class AuthorizationException(BISHLException):
    """Raised for authorization failures"""
    def __init__(self, message: str = "Insufficient permissions", details: dict = None):
        super().__init__(message, status_code=403, details=details)

class ExternalServiceException(BISHLException):
    """Raised when external service calls fail"""
    def __init__(self, service: str, operation: str, details: dict = None):
        message = f"External service '{service}' failed during '{operation}'"
        super().__init__(message, status_code=502, details=details)
```

### 2. Centralized Exception Handlers

Add exception handlers in `main.py` to catch and format errors consistently:

```python
# main.py additions

from exceptions.custom_exceptions import BISHLException
from fastapi.responses import JSONResponse
from fastapi import Request
import traceback
import uuid
from datetime import datetime

@app.exception_handler(BISHLException)
async def bishl_exception_handler(request: Request, exc: BISHLException):
    """Handle all BISHL custom exceptions"""
    correlation_id = str(uuid.uuid4())
    
    error_response = {
        "error": {
            "message": exc.message,
            "status_code": exc.status_code,
            "correlation_id": correlation_id,
            "timestamp": datetime.utcnow().isoformat(),
            "path": request.url.path,
            "details": exc.details
        }
    }
    
    # Log the error with correlation ID
    logger.error(
        f"[{correlation_id}] {exc.__class__.__name__}: {exc.message}",
        extra={
            "correlation_id": correlation_id,
            "status_code": exc.status_code,
            "path": request.url.path,
            "details": exc.details
        }
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle FastAPI HTTPExceptions with consistent format"""
    correlation_id = str(uuid.uuid4())
    
    error_response = {
        "error": {
            "message": exc.detail,
            "status_code": exc.status_code,
            "correlation_id": correlation_id,
            "timestamp": datetime.utcnow().isoformat(),
            "path": request.url.path
        }
    }
    
    logger.error(
        f"[{correlation_id}] HTTPException: {exc.detail}",
        extra={
            "correlation_id": correlation_id,
            "status_code": exc.status_code,
            "path": request.url.path
        }
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Catch-all handler for unexpected exceptions"""
    correlation_id = str(uuid.uuid4())
    
    # Log full traceback for unexpected errors
    logger.error(
        f"[{correlation_id}] Unhandled exception: {str(exc)}",
        extra={
            "correlation_id": correlation_id,
            "path": request.url.path,
            "traceback": traceback.format_exc()
        }
    )
    
    error_response = {
        "error": {
            "message": "An unexpected error occurred",
            "status_code": 500,
            "correlation_id": correlation_id,
            "timestamp": datetime.utcnow().isoformat(),
            "path": request.url.path
        }
    }
    
    return JSONResponse(
        status_code=500,
        content=error_response
    )
```

### 3. Structured Logging with Loguru

Replace print statements with structured logging:

```python
# logging_config.py

from loguru import logger
import sys
import os

DEBUG_LEVEL = int(os.environ.get('DEBUG_LEVEL', 0))

# Remove default handler
logger.remove()

# Add console handler with formatting
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="DEBUG" if DEBUG_LEVEL > 0 else "INFO",
    colorize=True
)

# Add file handler for errors
logger.add(
    "logs/errors.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    level="ERROR",
    rotation="10 MB",
    retention="30 days",
    compression="zip"
)

# Add file handler for all logs (if debug mode)
if DEBUG_LEVEL > 0:
    logger.add(
        "logs/debug.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG",
        rotation="50 MB",
        retention="7 days",
        compression="zip"
    )
```

### 4. Error Response Format

Standardize all error responses to follow this structure:

```json
{
  "error": {
    "message": "Match with ID 'abc123' not found",
    "status_code": 404,
    "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2025-01-15T10:30:00.000Z",
    "path": "/matches/abc123",
    "details": {
      "resource_type": "Match",
      "resource_id": "abc123"
    }
  }
}
```

---

## Implementation Plan

### Phase 1: Create Exception Infrastructure (2 hours)

**Step 1.1: Create Exception Classes**
- Create `exceptions/__init__.py`
- Create `exceptions/custom_exceptions.py` with exception hierarchy
- Add docstrings and examples

**Step 1.2: Set Up Logging**
- Create `logging_config.py`
- Install loguru: Already in dependencies
- Create logs directory in .gitignore

### Phase 2: Add Exception Handlers (1 hour)

**Step 2.1: Update main.py**
- Import custom exceptions
- Add exception handlers
- Configure logging on startup

### Phase 3: Refactor Stats Service (2 hours)

**Step 3.1: Update stats_service.py**
- Replace HTTPException with custom exceptions
- Add proper error context
- Replace print statements with logger calls

**Example migration:**
```python
# Before
raise HTTPException(
    status_code=404,
    detail=f"Match {match_id} not found"
)

# After
raise ResourceNotFoundException(
    resource_type="Match",
    resource_id=match_id,
    details={"team_flag": team_flag}
)
```

### Phase 4: Refactor Routers (4-5 hours)

**Step 4.1: Update Critical Routers**
Priority order:
1. `routers/matches.py` - Core functionality
2. `routers/roster.py` - Complex error scenarios
3. `routers/scores.py` - Stats calculations
4. `routers/penalties.py` - Stats calculations
5. `routers/users.py` - Authentication errors

**Step 4.2: Update Remaining Routers**
- `routers/players.py`
- `routers/clubs.py`
- `routers/tournaments.py`
- `routers/assignments.py`
- Others as needed

### Phase 5: Update Utilities (1 hour)

**Step 5.1: Update utils.py**
- Replace print statements with logger
- Update deprecated function wrappers
- Add error context to calculations

**Step 5.2: Update authentication.py**
- Use AuthenticationException
- Use AuthorizationException
- Add structured logging

### Phase 6: Testing & Documentation (2 hours)

**Step 6.1: Manual Testing**
- Test error responses for each router
- Verify correlation IDs in logs
- Check error message clarity

**Step 6.2: Documentation**
- Document error response format
- Add examples to API docs
- Update deployment checklist

---

## Migration Guidelines

### Before/After Examples

#### Example 1: Resource Not Found
```python
# BEFORE
match = await mongodb['matches'].find_one({'_id': match_id})
if not match:
    raise HTTPException(status_code=404, detail="Match not found")

# AFTER
match = await mongodb['matches'].find_one({'_id': match_id})
if not match:
    raise ResourceNotFoundException(
        resource_type="Match",
        resource_id=match_id
    )
```

#### Example 2: Database Operation
```python
# BEFORE
result = await mongodb['matches'].update_one(...)
if not result.acknowledged:
    raise HTTPException(status_code=500, detail="Failed to update match")

# AFTER
result = await mongodb['matches'].update_one(...)
if not result.acknowledged:
    raise DatabaseOperationException(
        operation="update_one",
        collection="matches",
        details={"match_id": match_id, "modified_count": result.modified_count}
    )
```

#### Example 3: Validation Error
```python
# BEFORE
if team_flag not in ['home', 'away']:
    raise HTTPException(status_code=400, detail="Invalid team flag")

# AFTER
if team_flag not in ['home', 'away']:
    raise ValidationException(
        field="team_flag",
        message=f"Must be 'home' or 'away', got '{team_flag}'"
    )
```

#### Example 4: Logging
```python
# BEFORE
if DEBUG_LEVEL > 0:
    print(f"[STATS] Calculating roster stats for {match_id}...")

# AFTER
logger.info(f"Calculating roster stats", extra={
    "match_id": match_id,
    "team_flag": team_flag
})
```

---

## Benefits

### 1. Better Debugging
- Correlation IDs trace errors across services
- Structured logs easy to search/filter
- Full context in error details

### 2. Improved Client Experience
- Consistent error format
- Clear error messages
- Proper HTTP status codes

### 3. Easier Maintenance
- Custom exceptions document domain logic
- Centralized error handling
- Type-safe error handling

### 4. Production Readiness
- Log rotation and compression
- Error aggregation ready
- Better monitoring capabilities

---

## Dependencies

**New Dependencies:**
- ✅ `loguru` - Already in pyproject.toml
- No additional packages needed

**Files to Create:**
- `exceptions/__init__.py`
- `exceptions/custom_exceptions.py`
- `logging_config.py`

**Files to Modify:**
- `main.py` - Add exception handlers
- `services/stats_service.py` - Use custom exceptions
- All routers - Replace HTTPException
- `utils.py` - Add logging
- `authentication.py` - Use custom exceptions

---

## Success Criteria

- ✅ All errors return consistent JSON format
- ✅ All errors include correlation IDs
- ✅ Structured logging in place
- ✅ No print statements in production code
- ✅ Custom exceptions for domain errors
- ✅ Error logs rotated and compressed
- ✅ Clear error messages for debugging

---

## Next Steps After Completion

1. Add error monitoring/alerting (future)
2. Create error analytics dashboard (future)
3. Implement retry logic for transient failures (future)
4. Add circuit breakers for external services (future)

---

*This spec is ready for implementation. Start with Phase 1 and proceed sequentially.*
