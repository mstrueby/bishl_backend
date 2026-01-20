
# BISHL API Usage Guide

*Last Updated: 2025-01-22*

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Authentication](#authentication)
3. [Common Patterns](#common-patterns)
4. [Endpoint Reference](#endpoint-reference)
5. [Error Handling](#error-handling)
6. [Best Practices](#best-practices)

---

## Getting Started

### Base URL

**Development:** `http://localhost:8080`  
**Production:** `https://api.bishl.be`

### API Documentation

Interactive API documentation is available at:
- **Swagger UI:** `/docs`
- **ReDoc:** `/redoc`

---

## Authentication

### Login

Obtain access and refresh tokens by logging in:

```http
POST /users/login
Content-Type: application/json

{
  "email": "referee@bishl.be",
  "password": "your_password"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "_id": "507f1f77bcf86cd799439011",
    "email": "referee@bishl.be",
    "firstName": "John",
    "lastName": "Doe",
    "roles": ["REFEREE"],
    "accessToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "refreshToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
  },
  "message": "Login successful"
}
```

### Using Tokens

Include the access token in the Authorization header for all authenticated requests:

```http
GET /matches
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Token Refresh

Access tokens expire after 15 minutes. Refresh them using:

```http
POST /users/refresh
Content-Type: application/json

{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "access_token": "new_access_token_here",
    "token_type": "bearer"
  },
  "message": "Token refreshed successfully"
}
```

---

## Common Patterns

### Pagination

All list endpoints support pagination:

```http
GET /matches?page=2&page_size=20
Authorization: Bearer <token>
```

**Response:**
```json
{
  "success": true,
  "data": [...],
  "pagination": {
    "page": 2,
    "page_size": 20,
    "total_items": 156,
    "total_pages": 8,
    "has_next": true,
    "has_prev": true
  },
  "message": "Retrieved 20 matches"
}
```

### Filtering

Filter resources using query parameters:

```http
GET /matches?status=UPCOMING&tournament=schuelerliga-p-2024
GET /players?search=john&clubId=507f1f77bcf86cd799439011
```

### Sorting

Specify sort order (where supported):

```http
GET /matches?sort_by=startDate&sort_order=desc
```

---

## Endpoint Reference

### Matches

#### List Matches

```http
GET /matches?page=1&page_size=10&status=UPCOMING
Authorization: Bearer <token>
```

**Query Parameters:**
- `page` (int, default: 1) - Page number
- `page_size` (int, default: 10, max: 100) - Items per page
- `status` (string, optional) - Filter by status: UPCOMING, LIVE, COMPLETED, POSTPONED, CANCELLED
- `tournament` (string, optional) - Filter by tournament alias
- `season` (string, optional) - Filter by season alias

**Response:** `PaginatedResponse[Match]`

#### Get Match Details

```http
GET /matches/{match_id}
Authorization: Bearer <token>
```

**Response:**
```json
{


### Calendar/Schedule Views

For displaying full season schedules or calendars, use one of these approaches:

**Approach 1: Dedicated Calendar Endpoint (Recommended)**
```javascript
// Fetch all matches for a season calendar
async function fetchSeasonCalendar(season, tournament = null) {
  const params = new URLSearchParams({ season });
  if (tournament) params.append('tournament', tournament);
  
  const response = await fetch(`/matches/calendar?${params}`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  
  const { data } = await response.json();
  return data; // All matches, no pagination handling needed
}

// Usage in calendar component
const matches = await fetchSeasonCalendar('2024-25', 'league-a');
// Group by date and display in calendar
const matchesByDate = groupMatchesByDate(matches);
```

**Approach 2: Large Page Size**
```javascript
// Request all matches with large page size
async function fetchAllMatches(season) {
  const response = await fetch(
    `/matches?season=${season}&page_size=500`,
    { headers: { 'Authorization': `Bearer ${token}` } }
  );
  
  const result = await response.json();
  
  // Check if there are more pages (unlikely with page_size=500)
  if (result.pagination.has_next) {
    console.warn('More matches exist, consider fetching next page');
  }
  
  return result.data;
}
```

**Performance Considerations:**
- Calendar endpoint returns ~50-300 matches typically (one season)
- Response size: ~100-500KB (without rosters/scores)
- Cache this data client-side, refresh periodically
- Consider grouping by month/week for better UX

**Example: React Calendar Component**
```javascript
function SeasonCalendar({ season, tournament }) {
  const [matches, setMatches] = useState([]);
  const [loading, setLoading] = useState(true);
  
  useEffect(() => {
    async function loadCalendar() {
      try {
        const data = await fetchSeasonCalendar(season, tournament);
        setMatches(data);
      } finally {
        setLoading(false);
      }
    }
    loadCalendar();
  }, [season, tournament]);
  
  // Group matches by date
  const matchesByDate = useMemo(() => {
    return matches.reduce((acc, match) => {
      const date = match.startDate.split('T')[0];
      if (!acc[date]) acc[date] = [];
      acc[date].push(match);
      return acc;
    }, {});
  }, [matches]);
  
  return (
    <Calendar 
      events={matchesByDate}
      loading={loading}
    />
  );
}
```

  "success": true,
  "data": {
    "_id": "67165e0190212e4ad16ca8dd",
    "tournament": {"alias": "schuelerliga-p-2024", "name": "Schülerliga Plus"},
    "season": {"alias": "2024-25", "name": "2024/25"},
    "matchday": {"alias": "matchday-1", "name": "Matchday 1"},
    "home": {"teamId": "...", "teamName": "Team A"},
    "away": {"teamId": "...", "teamName": "Team B"},
    "status": "COMPLETED",
    "startDate": "2024-10-15T18:00:00Z",
    "scores": {...}
  },
  "message": "Match retrieved successfully"
}
```

#### Update Match Score

```http
PUT /matches/{match_id}/scores
Authorization: Bearer <token>
Content-Type: application/json

{
  "homeScore": 5,
  "awayScore": 3,
  "period": "FINAL"
}
```

### Players

#### Search Players

```http
GET /players?search=smith&page=1&page_size=20
Authorization: Bearer <token>
```

**Query Parameters:**
- `search` (string, optional) - Search by name
- `clubId` (string, optional) - Filter by club
- `page`, `page_size` - Pagination parameters

#### Get Player Statistics

```http
GET /players/{player_id}/stats?tournament=schuelerliga-p-2024&season=2024-25
Authorization: Bearer <token>
```

**Response:**
```json
{
  "success": true,
  "data": {
    "player": {...},
    "stats": {
      "games_played": 12,
      "goals": 8,
      "assists": 5,
      "points": 13,
      "yellow_cards": 2,
      "red_cards": 0
    }
  },
  "message": "Player statistics retrieved successfully"
}
```

### Tournaments

#### List Tournaments

```http
GET /tournaments?page=1&page_size=10
Authorization: Bearer <token>
```

#### Get Tournament Standings

```http
GET /tournaments/{tournament_alias}/seasons/{season_alias}/rounds/{round_alias}/standings
Authorization: Bearer <token>
```

**Response:**
```json
{
  "success": true,
  "data": {
    "standings": [
      {
        "position": 1,
        "team": {"id": "...", "name": "Team A"},
        "games_played": 10,
        "wins": 8,
        "draws": 1,
        "losses": 1,
        "goals_for": 45,
        "goals_against": 12,
        "goal_difference": 33,
        "points": 25
      }
    ]
  },
  "message": "Standings retrieved successfully"
}
```

### Assignments

#### Get Referee Assignments

```http
GET /assignments/referee/{user_id}?status=PENDING
Authorization: Bearer <token>
```

**Query Parameters:**
- `status` (string, optional) - Filter by status: PENDING, ACCEPTED, DECLINED

---

## Error Handling

### Standard Error Format

All errors return a consistent format:

```json
{
  "error": {
    "message": "Match not found",
    "status_code": 404,
    "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2025-01-22T10:30:00.000Z",
    "path": "/matches/invalid-id",
    "details": {
      "resource_type": "Match",
      "resource_id": "invalid-id"
    }
  }
}
```

### Common HTTP Status Codes

- **200 OK** - Request successful
- **201 Created** - Resource created successfully
- **400 Bad Request** - Invalid request data
- **401 Unauthorized** - Missing or invalid authentication
- **403 Forbidden** - Insufficient permissions
- **404 Not Found** - Resource not found
- **409 Conflict** - Resource conflict (e.g., duplicate)
- **422 Unprocessable Entity** - Validation error
- **500 Internal Server Error** - Server error

### Error Handling Example

```javascript
try {
  const response = await fetch('/matches/123', {
    headers: {
      'Authorization': `Bearer ${accessToken}`
    }
  });
  
  if (!response.ok) {
    const error = await response.json();
    console.error('Error:', error.error.message);
    console.error('Correlation ID:', error.error.correlation_id);
    
    if (response.status === 401) {
      // Token expired, refresh it
      await refreshToken();
    }
  }
  
  const result = await response.json();
  return result.data;
} catch (error) {
  console.error('Network error:', error);
}
```

---

## Best Practices

### 1. Token Management

- **Store tokens securely** - Use httpOnly cookies or secure storage
- **Implement automatic refresh** - Refresh tokens before they expire
- **Handle 401 errors** - Automatically refresh and retry

### 2. Pagination

- **Use appropriate page sizes** - Don't request more data than needed
- **Cache results** - Cache paginated results when possible
- **Handle empty pages** - Check `total_items` before rendering

### 3. Error Handling

- **Check success field** - Always check `success: true` in responses
- **Log correlation IDs** - Include correlation IDs in error reports
- **Provide user feedback** - Show user-friendly error messages

### 4. Performance

- **Use filters** - Filter server-side instead of client-side
- **Request only needed fields** - Use projections when available
- **Implement debouncing** - Debounce search inputs

### 5. Security

- **Never log tokens** - Don't log access or refresh tokens
- **Validate input** - Validate data before sending to API
- **Use HTTPS** - Always use HTTPS in production

---

## Rate Limiting

*(Coming soon)*

Currently, there are no rate limits enforced. However, please be considerate:
- Don't make excessive requests
- Implement reasonable caching
- Use webhooks for real-time updates (when available)

---

## Support

For API support or questions:
- **Email:** tech@bishl.be
- **Documentation:** https://api.bishl.be/docs

---

*This guide is continuously updated. Last revision: 2025-01-22*
