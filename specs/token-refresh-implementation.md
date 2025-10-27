
# Token Refresh Implementation

*Created: 2025-01-22*  
*Status: Implemented*

---

## Overview

The BISHL backend now uses a **two-token authentication system** to improve user experience while maintaining security:

- **Access Token** (short-lived: 15 minutes) - Used for API requests
- **Refresh Token** (long-lived: 7 days) - Used only to obtain new access tokens

---

## How It Works

### 1. Login Flow

**Endpoint:** `POST /users/login`

**Request:**
```json
{
  "email": "referee@example.com",
  "password": "password123"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 900
}
```

### 2. Using Access Token

All API requests use the access token in the `Authorization` header:

```
Authorization: Bearer <access_token>
```

### 3. Token Refresh Flow

When the access token expires (after 15 minutes), the client receives a `401` response:

```json
{
  "error": {
    "message": "Token has expired",
    "status_code": 401,
    "details": {
      "reason": "expired_signature"
    }
  }
}
```

**Client should then:**

1. Call the refresh endpoint with the refresh token
2. Receive new tokens
3. Retry the original request

**Endpoint:** `POST /users/refresh`

**Request:**
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 900
}
```

### 4. Refresh Token Expiration

When the refresh token expires (after 7 days), the client must re-login.

---

## Frontend Implementation Guide

### Storage

Store both tokens securely:

```javascript
// After login
localStorage.setItem('access_token', response.access_token);
localStorage.setItem('refresh_token', response.refresh_token);
```

### Axios Interceptor (Recommended)

```javascript
import axios from 'axios';

let isRefreshing = false;
let failedQueue = [];

const processQueue = (error, token = null) => {
  failedQueue.forEach(prom => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token);
    }
  });
  failedQueue = [];
};

// Response interceptor
axios.interceptors.response.use(
  response => response,
  async error => {
    const originalRequest = error.config;

    // If error is 401 and we haven't tried to refresh yet
    if (error.response?.status === 401 && !originalRequest._retry) {
      if (isRefreshing) {
        // Queue this request while refresh is in progress
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        }).then(token => {
          originalRequest.headers['Authorization'] = 'Bearer ' + token;
          return axios(originalRequest);
        }).catch(err => {
          return Promise.reject(err);
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      const refreshToken = localStorage.getItem('refresh_token');
      
      if (!refreshToken) {
        // No refresh token, redirect to login
        window.location.href = '/login';
        return Promise.reject(error);
      }

      try {
        const response = await axios.post('/users/refresh', {
          refresh_token: refreshToken
        });

        const { access_token, refresh_token: new_refresh_token } = response.data;
        
        // Store new tokens
        localStorage.setItem('access_token', access_token);
        localStorage.setItem('refresh_token', new_refresh_token);

        // Update default authorization header
        axios.defaults.headers.common['Authorization'] = 'Bearer ' + access_token;
        
        // Retry all queued requests
        processQueue(null, access_token);

        // Retry original request
        originalRequest.headers['Authorization'] = 'Bearer ' + access_token;
        return axios(originalRequest);
      } catch (refreshError) {
        // Refresh failed, clear tokens and redirect to login
        processQueue(refreshError, null);
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        window.location.href = '/login';
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);
```

### Request Interceptor

```javascript
// Add access token to all requests
axios.interceptors.request.use(
  config => {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers['Authorization'] = 'Bearer ' + token;
    }
    return config;
  },
  error => Promise.reject(error)
);
```

---

## Security Considerations

### Why Two Secrets?

Access and refresh tokens use different secrets:
- `SECRET_KEY` for access tokens
- `SECRET_KEY + "_refresh"` for refresh tokens

This prevents a leaked access token from being used as a refresh token.

### Token Payload Differences

**Access Token:**
```json
{
  "sub": "user_id",
  "roles": ["REFEREE", "ADMIN"],
  "firstName": "John",
  "lastName": "Doe",
  "clubId": "club123",
  "clubName": "Example Club",
  "type": "access",
  "exp": 1234567890,
  "iat": 1234567000
}
```

**Refresh Token (minimal payload):**
```json
{
  "sub": "user_id",
  "type": "refresh",
  "exp": 1234567890,
  "iat": 1234567000
}
```

### Why Stateless?

Refresh tokens are **stateless JWTs** (not stored in database):

**Pros:**
- No database queries needed
- Simpler implementation
- Horizontally scalable

**Cons:**
- Cannot revoke tokens before expiration
- Cannot track active sessions

**Future Enhancement:** Store refresh tokens in DB for revocation capability.

---

## Migration Notes

### Backward Compatibility

The `/users/login` endpoint now returns:
```json
{
  "access_token": "...",
  "refresh_token": "...",
  "token_type": "bearer",
  "expires_in": 900
}
```

**Old clients** expecting `{"token": "..."}` will break. Update frontend before deploying.

### Deployment Steps

1. Deploy backend with token refresh feature
2. Update frontend to use new token structure
3. Inform users they need to re-login after deployment

---

## Testing

### Manual Testing

```bash
# 1. Login
curl -X POST http://localhost:8080/users/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "password123"}'

# Response:
# {
#   "access_token": "eyJ...",
#   "refresh_token": "eyJ...",
#   "token_type": "bearer",
#   "expires_in": 900
# }

# 2. Use access token (works for 15 minutes)
curl http://localhost:8080/matches \
  -H "Authorization: Bearer <access_token>"

# 3. After 15 minutes, access token expires, refresh it
curl -X POST http://localhost:8080/users/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "eyJ..."}'

# 4. After 7 days, refresh token expires, must re-login
```

---

## Benefits

✅ **Better UX:** Users stay logged in for 7 days instead of 60 minutes  
✅ **Security:** Short-lived access tokens limit exposure window  
✅ **Scalability:** Stateless tokens require no database lookups  
✅ **Future-proof:** Can add token revocation later if needed  

---

*Implementation completed in Step 9 of refactoring roadmap*
