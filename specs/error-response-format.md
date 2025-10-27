
# Error Response Format Documentation

*Created: 2025-01-22*  
*Status: Standard*

---

## Overview

All API errors in the BISHL backend follow a standardized JSON format that includes:
- Clear error messages
- HTTP status codes
- Correlation IDs for tracing
- Timestamps
- Request context
- Additional details when available

---

## Standard Error Response Structure

```json
{
  "error": {
    "message": "Human-readable error message",
    "status_code": 404,
    "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2025-01-22T10:30:00.000Z",
    "path": "/api/endpoint",
    "details": {
      "additional_context_key": "value"
    }
  }
}
```

### Field Descriptions

| Field | Type | Description |
|-------|------|-------------|
| `message` | string | Clear, actionable error message explaining what went wrong |
| `status_code` | integer | HTTP status code (400, 401, 403, 404, 500, etc.) |
| `correlation_id` | string (UUID) | Unique identifier for tracing this error in logs |
| `timestamp` | string (ISO 8601) | When the error occurred (UTC) |
| `path` | string | API endpoint where the error occurred |
| `details` | object | Optional additional context (varies by error type) |

---

## Error Types and Examples

### 1. Resource Not Found (404)

**Scenario:** Requesting a resource that doesn't exist

```json
{
  "error": {
    "message": "Match with ID '67165e0190212e4ad16ca8dd' not found",
    "status_code": 404,
    "correlation_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "timestamp": "2025-01-22T14:25:30.123Z",
    "path": "/matches/67165e0190212e4ad16ca8dd",
    "details": {
      "resource_type": "Match",
      "resource_id": "67165e0190212e4ad16ca8dd"
    }
  }
}
```

**Common Causes:**
- Invalid ID in URL
- Resource was deleted
- User doesn't have access to resource

---

### 2. Validation Error (400)

**Scenario:** Invalid input data

```json
{
  "error": {
    "message": "Validation error on field 'team_flag': Must be 'home' or 'away', got 'invalid'",
    "status_code": 400,
    "correlation_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
    "timestamp": "2025-01-22T14:26:15.456Z",
    "path": "/matches/67165e0190212e4ad16ca8dd/roster/home",
    "details": {
      "field": "team_flag",
      "provided_value": "invalid",
      "allowed_values": ["home", "away"]
    }
  }
}
```

**Common Causes:**
- Missing required fields
- Invalid data format
- Values outside allowed range
- Type mismatches

---

### 3. Authentication Error (401)

**Scenario:** Invalid or expired authentication token

```json
{
  "error": {
    "message": "Token has expired",
    "status_code": 401,
    "correlation_id": "c3d4e5f6-a7b8-9012-cdef-123456789012",
    "timestamp": "2025-01-22T14:27:00.789Z",
    "path": "/matches",
    "details": {
      "reason": "expired_signature"
    }
  }
}
```

**Common Causes:**
- Token expired (default: 60 minutes)
- Invalid token format
- Token signature verification failed

**Client Action:** Re-authenticate to get a new token

---

### 4. Authorization Error (403)

**Scenario:** User lacks required permissions

```json
{
  "error": {
    "message": "Insufficient permissions",
    "status_code": 403,
    "correlation_id": "d4e5f6a7-b8c9-0123-def1-234567890123",
    "timestamp": "2025-01-22T14:28:30.012Z",
    "path": "/tournaments/bishl-2024/seasons/2024/rounds/hauptrunde",
    "details": {
      "required_roles": ["ADMIN", "LEAGUE_ADMIN"],
      "user_roles": ["CLUB_ADMIN"]
    }
  }
}
```

**Common Causes:**
- User role doesn't match required roles
- User's club doesn't match resource's club
- Resource requires higher privileges

**Client Action:** Cannot be resolved by client; requires admin intervention

---

### 5. Database Operation Error (500)

**Scenario:** Database operation failed

```json
{
  "error": {
    "message": "Database operation 'update_one' failed on collection 'matches'",
    "status_code": 500,
    "correlation_id": "e5f6a7b8-c9d0-1234-ef12-345678901234",
    "timestamp": "2025-01-22T14:29:45.345Z",
    "path": "/matches/67165e0190212e4ad16ca8dd",
    "details": {
      "operation": "update_one",
      "collection": "matches",
      "match_id": "67165e0190212e4ad16ca8dd",
      "modified_count": 0
    }
  }
}
```

**Common Causes:**
- Database connection issues
- Write conflicts
- Constraint violations
- Timeout errors

**Client Action:** Retry the request; contact support if persists

---

### 6. Stats Calculation Error (500)

**Scenario:** Statistics calculation failed

```json
{
  "error": {
    "message": "Failed to calculate player_card stats for player_12345",
    "status_code": 500,
    "correlation_id": "f6a7b8c9-d0e1-2345-f123-456789012345",
    "timestamp": "2025-01-22T14:30:20.678Z",
    "path": "/players/player_12345/stats",
    "details": {
      "stats_type": "player_card",
      "entity_id": "player_12345",
      "tournament_alias": "bishl-2024",
      "season_alias": "2024"
    }
  }
}
```

**Common Causes:**
- Missing related data (matches, rounds, etc.)
- Invalid standings settings
- Calculation logic errors

**Client Action:** Verify data integrity; contact support with correlation_id

---

## Using Correlation IDs

### Purpose
Correlation IDs allow you to trace a specific error through the entire request lifecycle, including:
- API request logs
- Database operation logs
- Stats calculation logs
- External service calls

### Finding Errors in Logs

1. **Extract correlation_id from error response**
   ```json
   "correlation_id": "550e8400-e29b-41d4-a716-446655440000"
   ```

2. **Search logs for correlation_id**
   ```bash
   grep "550e8400-e29b-41d4-a716-446655440000" logs/errors.log
   ```

3. **Example log entry**
   ```
   2025-01-22 14:25:30 | ERROR    | routers.matches:get_match:145 - [550e8400-e29b-41d4-a716-446655440000] ResourceNotFoundException: Match with ID '67165e0190212e4ad16ca8dd' not found
   ```

---

## Client Implementation Guide

### Error Handling Pattern

```javascript
async function fetchMatch(matchId) {
  try {
    const response = await fetch(`/matches/${matchId}`);
    
    if (!response.ok) {
      const errorData = await response.json();
      
      // Log correlation ID for support requests
      console.error(`Error ${errorData.error.correlation_id}:`, errorData.error.message);
      
      // Handle specific error types
      switch (errorData.error.status_code) {
        case 401:
          // Token expired - redirect to login
          redirectToLogin();
          break;
        case 403:
          // Insufficient permissions - show access denied
          showAccessDenied();
          break;
        case 404:
          // Resource not found - show not found page
          showNotFound(errorData.error.message);
          break;
        case 500:
          // Server error - show error with correlation ID
          showServerError(errorData.error.correlation_id);
          break;
        default:
          // Generic error handler
          showError(errorData.error.message);
      }
      
      return null;
    }
    
    return await response.json();
  } catch (error) {
    console.error('Network error:', error);
    showNetworkError();
    return null;
  }
}
```

### Displaying Errors to Users

**Good Practice:**
```
❌ Match not found
Please verify the match ID and try again.
If the problem persists, contact support with error ID: 550e8400-e29b-41d4-a716-446655440000
```

**Bad Practice:**
```
Error: Match with ID '67165e0190212e4ad16ca8dd' not found
```

---

## HTTP Status Code Reference

| Code | Meaning | When Used |
|------|---------|-----------|
| 400 | Bad Request | Invalid input, validation errors |
| 401 | Unauthorized | Missing or invalid authentication |
| 403 | Forbidden | Valid auth but insufficient permissions |
| 404 | Not Found | Requested resource doesn't exist |
| 500 | Internal Server Error | Database errors, calculation failures |
| 502 | Bad Gateway | External service failures |

---

## Migration Notes

### Legacy Error Format (Deprecated)

Old errors may still use this format:
```json
{
  "detail": "Error message"
}
```

**Action:** These will be migrated to the new format in upcoming releases.

### Backward Compatibility

Clients should handle both formats during transition:
```javascript
function parseError(response) {
  // New format
  if (response.error) {
    return response.error;
  }
  
  // Legacy format
  if (response.detail) {
    return {
      message: response.detail,
      status_code: response.status_code || 500
    };
  }
  
  return { message: 'Unknown error' };
}
```

---

## Support and Debugging

### When Contacting Support

Always include:
1. **Correlation ID** from error response
2. **Timestamp** of the error
3. **Request details** (endpoint, method, payload)
4. **Expected behavior** vs actual behavior

### Example Support Request

```
Subject: Error when updating match roster

Correlation ID: 550e8400-e29b-41d4-a716-446655440000
Timestamp: 2025-01-22T14:25:30.123Z
Endpoint: PUT /matches/67165e0190212e4ad16ca8dd/roster/home
Error: Database operation 'update_one' failed on collection 'matches'

Expected: Roster should update successfully
Actual: 500 error returned

Steps to reproduce:
1. Navigate to match 67165e0190212e4ad16ca8dd
2. Click "Edit Roster" for home team
3. Add player to roster
4. Click "Save"
```

---

## Best Practices

### For API Consumers

1. ✅ **Always check status_code** before processing response
2. ✅ **Log correlation_id** for all errors
3. ✅ **Implement retry logic** for 500-level errors
4. ✅ **Handle 401 by re-authenticating** automatically
5. ✅ **Show user-friendly messages** based on error type

### For API Developers

1. ✅ **Use custom exception classes** not HTTPException
2. ✅ **Include relevant context** in details object
3. ✅ **Log errors with correlation_id** for tracing
4. ✅ **Don't expose sensitive data** in error messages
5. ✅ **Test error scenarios** in development

---

*Last Updated: 2025-01-22*
