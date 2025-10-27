
# API Error Examples for Testing

*Created: 2025-01-22*  
*Purpose: Test error handling implementation*

---

## Quick Test Commands

Use these curl commands to verify error handling is working correctly.

### 1. Test 404 - Resource Not Found

```bash
curl -X GET http://localhost:8080/matches/invalid_id_12345 \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -v
```

**Expected Response:**
```json
{
  "error": {
    "message": "Match with ID 'invalid_id_12345' not found",
    "status_code": 404,
    "correlation_id": "...",
    "timestamp": "...",
    "path": "/matches/invalid_id_12345",
    "details": {
      "resource_type": "Match",
      "resource_id": "invalid_id_12345"
    }
  }
}
```

---

### 2. Test 401 - Invalid Token

```bash
curl -X GET http://localhost:8080/matches \
  -H "Authorization: Bearer invalid_token_xyz" \
  -v
```

**Expected Response:**
```json
{
  "error": {
    "message": "Invalid token",
    "status_code": 401,
    "correlation_id": "...",
    "timestamp": "...",
    "path": "/matches",
    "details": {
      "reason": "invalid_token"
    }
  }
}
```

---

### 3. Test 401 - Missing Token

```bash
curl -X GET http://localhost:8080/matches \
  -v
```

**Expected Response:**
```json
{
  "error": {
    "message": "Not authenticated",
    "status_code": 403,
    "correlation_id": "...",
    "timestamp": "...",
    "path": "/matches"
  }
}
```

---

### 4. Test 400 - Validation Error

```bash
curl -X PUT http://localhost:8080/matches/VALID_MATCH_ID/roster/invalid_flag \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '[]' \
  -v
```

**Expected Response:**
```json
{
  "error": {
    "message": "Validation error on field 'team_flag': Must be 'home' or 'away', got 'invalid_flag'",
    "status_code": 400,
    "correlation_id": "...",
    "timestamp": "...",
    "path": "/matches/.../roster/invalid_flag",
    "details": {
      "field": "team_flag",
      "provided_value": "invalid_flag"
    }
  }
}
```

---

### 5. Test 403 - Insufficient Permissions

```bash
# Login as CLUB_ADMIN user
curl -X POST http://localhost:8080/login \
  -H "Content-Type: application/json" \
  -d '{"email": "club_admin@example.com", "password": "password"}'

# Try to access ADMIN-only endpoint
curl -X POST http://localhost:8080/tournaments \
  -H "Authorization: Bearer CLUB_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Test", "alias": "test"}' \
  -v
```

**Expected Response:**
```json
{
  "error": {
    "message": "Insufficient permissions",
    "status_code": 403,
    "correlation_id": "...",
    "timestamp": "...",
    "path": "/tournaments",
    "details": {
      "required_roles": ["ADMIN", "LEAGUE_ADMIN"],
      "user_roles": ["CLUB_ADMIN"]
    }
  }
}
```

---

## Verification Checklist

After running tests, verify:

- [ ] All errors return JSON with "error" root key
- [ ] All errors include correlation_id (UUID format)
- [ ] All errors include timestamp (ISO 8601 format)
- [ ] All errors include path (request URL)
- [ ] Status codes match error type (404, 401, 403, 400, 500)
- [ ] Error messages are clear and actionable
- [ ] No stack traces exposed to client
- [ ] Correlation IDs found in logs/errors.log

---

## Log Verification

### Check Error Logs

```bash
# View recent errors
tail -n 50 logs/errors.log

# Search for correlation ID
grep "CORRELATION_ID_FROM_RESPONSE" logs/errors.log

# View all errors from last hour
grep "$(date -u +%Y-%m-%d\ %H)" logs/errors.log
```

### Expected Log Format

```
2025-01-22 14:25:30 | ERROR    | routers.matches:get_match:145 - [550e8400-e29b-41d4-a716-446655440000] ResourceNotFoundException: Match with ID 'invalid_id_12345' not found
```

Verify log includes:
- [ ] Timestamp
- [ ] Log level (ERROR)
- [ ] Module and function name
- [ ] Correlation ID in brackets
- [ ] Exception class name
- [ ] Error message

---

## Integration Test Script

Create a test script to automate verification:

```python
# test_error_handling.py
import requests
import json

BASE_URL = "http://localhost:8080"

def test_404_error():
    """Test resource not found"""
    response = requests.get(f"{BASE_URL}/matches/invalid_id")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert "correlation_id" in data["error"]
    print("✓ 404 test passed")

def test_401_error():
    """Test invalid token"""
    response = requests.get(
        f"{BASE_URL}/matches",
        headers={"Authorization": "Bearer invalid"}
    )
    assert response.status_code == 401
    data = response.json()
    assert data["error"]["message"] == "Invalid token"
    print("✓ 401 test passed")

def test_validation_error():
    """Test validation error"""
    token = get_valid_token()  # Implement this
    response = requests.put(
        f"{BASE_URL}/matches/valid_id/roster/invalid",
        headers={"Authorization": f"Bearer {token}"},
        json=[]
    )
    assert response.status_code == 400
    data = response.json()
    assert "Validation error" in data["error"]["message"]
    print("✓ Validation test passed")

if __name__ == "__main__":
    test_404_error()
    test_401_error()
    test_validation_error()
    print("\n✓ All error handling tests passed!")
```

---

*Last Updated: 2025-01-22*
