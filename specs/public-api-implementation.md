
# Public API Implementation Specification

**Version:** 1.0  
**Status:** Draft  
**Last Updated:** 2025-01-07  
**Effort:** Medium | **Impact:** High | **Risk:** Medium

---

## Overview

This document outlines the implementation plan for adding a public, read-only API to the BISHL backend using the `/public` prefix approach. This will allow external consumers (other clubs, websites) to access BISHL data without authentication while keeping internal administrative APIs secure.

---

## Architecture Decision

**Selected Approach:** Option 1 - `/public` Prefix (Single Backend)

### URL Structure
```
# Internal API (authenticated, full CRUD)
api.bishl.de/matches/{id}
api.bishl.de/tournaments
api.bishl.de/players/{id}

# Public API (no auth, read-only, filtered data)
api.bishl.de/public/matches/{id}
api.bishl.de/public/tournaments
api.bishl.de/public/players/{id}
```

### Key Benefits
- ✅ Single deployment (simpler DevOps)
- ✅ Shared database connection pool
- ✅ Same domain (easier SSL/DNS management)
- ✅ Service layer completely reused (no duplication)
- ✅ Clear separation of public vs internal endpoints

---

## Implementation Strategy

### 1. Code Reuse Pattern

#### Services Layer - 100% REUSED ✅
All existing services will be **completely reused** without any duplication:
- `StatsService`
- `MatchService`
- `TournamentService`
- `PaginationHelper`
- Database query logic

#### Routers - NEW (Minimal Duplication)
Create **separate router files** in `routers/public/` with:
- **No authentication dependencies**
- **Read-only operations only** (GET endpoints)
- **Filtered response data** (exclude sensitive fields)
- **Same service calls** as internal routers

### 2. Directory Structure

```
routers/
├── public/                    # NEW - Public API routers
│   ├── __init__.py
│   ├── matches.py            # Public match endpoints
│   ├── tournaments.py        # Public tournament endpoints
│   ├── players.py            # Public player endpoints
│   ├── clubs.py              # Public club endpoints
│   └── venues.py             # Public venue endpoints
├── matches.py                # EXISTING - Internal API
├── tournaments.py            # EXISTING - Internal API
└── ...
```

---

## Detailed Implementation Plan

### Phase 1: Foundation (2-3 hours)

#### 1.1 Create Public Router Base Structure

**File:** `routers/public/__init__.py`
```python
"""
Public API Routers

Read-only, unauthenticated endpoints for external data consumers.
All endpoints filter sensitive data before returning responses.
"""
```

**Files to Create:**
- `routers/public/__init__.py`
- `routers/public/matches.py`
- `routers/public/tournaments.py`
- `routers/public/players.py`
- `routers/public/clubs.py`
- `routers/public/venues.py`

#### 1.2 Define Response Filtering Strategy

**Sensitive Data to Exclude:**
- Internal database IDs (keep only public aliases where applicable)
- User email addresses
- Referee personal contact information
- Unpublished/draft content
- Internal administrative notes
- Audit timestamps (created_at, updated_at)
- System metadata

**Public Data to Include:**
- Match schedules and results
- Tournament structures and standings
- Player statistics (public stats only)
- Club and team information
- Venue locations and details

---

### Phase 2: Public Match Endpoints (3-4 hours)

#### 2.1 Implement Public Match Router

**File:** `routers/public/matches.py`

**Endpoints to Create:**

1. **GET /public/matches** - List matches with filters
   - Query params: `tournament`, `season`, `round`, `matchday`, `club`, `team`, `date_from`, `date_to`
   - Pagination: `page`, `page_size`
   - No roster details, simplified response

2. **GET /public/matches/{match_id}** - Single match details
   - Include: scores, basic stats, team names, venue, start time
   - Exclude: referee contact info, internal notes, roster details

3. **GET /public/matches/today** - Today's matches
   - Same filters as list endpoint
   - Lightweight response

4. **GET /public/matches/upcoming** - Upcoming matches
   - Next matchday with games

**Example Implementation Pattern:**
```python
# routers/public/matches.py
from fastapi import APIRouter, Request, Query
from services.match_service import MatchService
from services.pagination import PaginationHelper

router = APIRouter()

@router.get("")
async def get_public_matches(
    request: Request,
    tournament: str | None = None,
    season: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100)
):
    mongodb = request.app.state.mongodb
    
    # Reuse existing query logic
    query = {"season.alias": season} if season else {}
    if tournament:
        query["tournament.alias"] = tournament
    
    # Exclude sensitive fields
    projection = {
        "home.roster": 0,
        "away.roster": 0,
        "referee1.email": 0,
        "referee2.email": 0,
        "referee1.phone": 0,
        "referee2.phone": 0
    }
    
    items, total_count = await PaginationHelper.paginate_query(
        collection=mongodb["matches"],
        query=query,
        page=page,
        page_size=page_size,
        projection=projection
    )
    
    # Filter response data
    filtered_items = [filter_match_data(match) for match in items]
    
    return PaginationHelper.create_response(
        items=filtered_items,
        page=page,
        page_size=page_size,
        total_count=total_count
    )

def filter_match_data(match: dict) -> dict:
    """Remove sensitive fields from match data"""
    return {
        "id": match["_id"],
        "tournament": match.get("tournament"),
        "season": match.get("season"),
        "round": match.get("round"),
        "matchday": match.get("matchday"),
        "startDate": match.get("startDate"),
        "venue": match.get("venue"),
        "home": {
            "club": match["home"].get("clubName"),
            "team": match["home"].get("teamName"),
            "stats": match["home"].get("stats")
        },
        "away": {
            "club": match["away"].get("clubName"),
            "team": match["away"].get("teamName"),
            "stats": match["away"].get("stats")
        },
        "matchStatus": match.get("matchStatus")
    }
```

---

### Phase 3: Public Tournament Endpoints (2-3 hours)

#### 3.1 Implement Public Tournament Router

**File:** `routers/public/tournaments.py`

**Endpoints to Create:**

1. **GET /public/tournaments** - List all tournaments
   - Include: name, alias, current season, sport type
   - Exclude: internal settings, admin notes

2. **GET /public/tournaments/{tournament_alias}** - Tournament details
   - Include: seasons list, tournament structure
   - Exclude: rounds (too nested for public API)

3. **GET /public/tournaments/{tournament_alias}/standings** - Current standings
   - Season standings with team statistics
   - Cached/pre-calculated data only

**Implementation Notes:**
- Reuse `TournamentService.get_standings_settings()`
- Filter out internal tournament configuration
- Provide simplified season structure

---

### Phase 4: Public Player/Club/Venue Endpoints (2-3 hours)

#### 4.1 Public Players Router

**Endpoints:**
1. **GET /public/players** - Search players (limited fields)
2. **GET /public/players/{player_id}** - Player public profile
   - Include: name, jersey number, statistics
   - Exclude: email, phone, internal IDs, ISHD logs

#### 4.2 Public Clubs Router

**Endpoints:**
1. **GET /public/clubs** - List all clubs
2. **GET /public/clubs/{club_alias}** - Club details with teams

#### 4.3 Public Venues Router

**Endpoints:**
1. **GET /public/venues** - List all venues
2. **GET /public/venues/{venue_alias}** - Venue details

---

### Phase 5: Main App Integration (1 hour)

#### 5.1 Register Public Routers in Main.py

**File:** `main.py`

```python
# Add imports
from routers.public import matches as public_matches
from routers.public import tournaments as public_tournaments
from routers.public import players as public_players
from routers.public import clubs as public_clubs
from routers.public import venues as public_venues

# Register public routers (add after existing routers)
app.include_router(
    public_matches.router,
    prefix="/public/matches",
    tags=["public-api"]
)
app.include_router(
    public_tournaments.router,
    prefix="/public/tournaments",
    tags=["public-api"]
)
app.include_router(
    public_players.router,
    prefix="/public/players",
    tags=["public-api"]
)
app.include_router(
    public_clubs.router,
    prefix="/public/clubs",
    tags=["public-api"]
)
app.include_router(
    public_venues.router,
    prefix="/public/venues",
    tags=["public-api"]
)
```

#### 5.2 Update OpenAPI Tags

Add new tag definition:
```python
{
    "name": "public-api",
    "description": "Public read-only API endpoints for external data consumers. No authentication required."
}
```

---

### Phase 6: Documentation & Rate Limiting (2-3 hours)

#### 6.1 Create Public API Documentation

**File:** `specs/public-api-usage-guide.md`

**Contents:**
- Overview of public API
- Available endpoints
- Response formats
- Usage examples
- Rate limits (if implemented)
- Attribution requirements

#### 6.2 Implement Rate Limiting (Optional but Recommended)

**Library:** `slowapi`

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.get("")
@limiter.limit("100/minute")
async def get_public_matches(...):
    ...
```

---

## Data Access Patterns

### What Gets Reused vs Created

| Component | Status | Notes |
|-----------|--------|-------|
| **Services** | ✅ 100% Reused | Same business logic |
| **Database Queries** | ✅ 100% Reused | Via services |
| **Models** | ⚠️ 90% Reused | May need public response models |
| **Authentication** | ❌ Not Used | Public = no auth |
| **Route Handlers** | ⚠️ New Files | ~30-40% code overlap |
| **Response Filtering** | ✅ New Logic | Public-specific filtering |

---

## Security Considerations

### 1. No Authentication Required
- Public endpoints explicitly **do not** use `Depends(auth.auth_wrapper)`
- No token validation
- Open to all consumers

### 2. Data Filtering
- Implement strict output filtering functions
- Never expose sensitive fields
- Whitelist approach (only include safe fields)

### 3. Rate Limiting (Recommended)
- Prevent API abuse
- Suggested: 100 requests/minute per IP
- Return 429 status on limit exceeded

### 4. CORS Configuration
- Public API should allow broader CORS
- Consider adding specific CORS settings for `/public/*` routes

---

## Testing Strategy

### 1. Unit Tests
- Test response filtering functions
- Verify sensitive data exclusion
- Test pagination with public endpoints

### 2. Integration Tests
- Test all public endpoints without auth tokens
- Verify data completeness (non-sensitive fields)
- Test query filters and pagination

### 3. Manual Testing Checklist
- [ ] Access public endpoints without authentication
- [ ] Verify no sensitive data in responses
- [ ] Test all query parameters
- [ ] Verify pagination works correctly
- [ ] Test CORS from external domain
- [ ] Verify rate limiting (if implemented)

---

## Deployment Considerations

### 1. DNS Configuration
Already configured:
- `api.bishl.de` → points to Replit deployment
- No additional DNS changes needed

### 2. Replit Deployment
- Single deployment for both internal and public APIs
- Update deployment configuration if needed
- Monitor resource usage with public access

### 3. Monitoring
- Track public API usage separately
- Monitor for abuse/excessive requests
- Set up alerts for unusual patterns

---

## Success Criteria

- ✅ Public API accessible at `api.bishl.de/public/*`
- ✅ No authentication required for public endpoints
- ✅ All sensitive data filtered from responses
- ✅ Services layer 100% reused (no duplication)
- ✅ Comprehensive documentation for external consumers
- ✅ Rate limiting prevents abuse (if implemented)
- ✅ All tests passing
- ✅ CORS properly configured for external access

---

## Future Enhancements

### Phase 7 (Future)
1. **API Key System** (Optional)
   - Track usage per consumer
   - Different rate limits per API key
   - Usage analytics

2. **Webhooks** (Future)
   - Notify consumers of new matches
   - Real-time score updates
   - Tournament changes

3. **GraphQL Endpoint** (Future)
   - Allow consumers to query exactly what they need
   - Reduce over-fetching

4. **SDK/Client Libraries** (Future)
   - JavaScript/TypeScript client
   - Python client
   - Documentation with code examples

---

## Rollout Plan

### Week 1: Foundation
- Create public router structure
- Implement response filtering utilities
- Set up testing framework

### Week 2: Core Endpoints
- Implement public matches endpoints
- Implement public tournaments endpoints
- Write integration tests

### Week 3: Additional Endpoints
- Implement players/clubs/venues public endpoints
- Complete documentation
- Manual testing

### Week 4: Polish & Launch
- Rate limiting implementation (optional)
- Final testing and bug fixes
- Soft launch with select partners
- Gather feedback

### Week 5: Public Announcement
- Full public documentation
- Blog post/announcement
- Monitor usage and performance

---

## Estimated Timeline

**Total Effort:** 12-16 hours
- Phase 1: 2-3 hours
- Phase 2: 3-4 hours
- Phase 3: 2-3 hours
- Phase 4: 2-3 hours
- Phase 5: 1 hour
- Phase 6: 2-3 hours

---

## Related Documents

- `specs/api-response-standardization.md` - Standard response formats
- `specs/api-usage-guide.md` - Internal API documentation
- `specs/error-handling-standardization.md` - Error response format

---

## Appendix: Example Public API Responses

### GET /public/matches
```json
{
  "success": true,
  "data": [
    {
      "id": "match123",
      "tournament": {"name": "BISHL 2024/25", "alias": "bishl-2024-25"},
      "season": {"name": "Regular Season", "alias": "regular"},
      "startDate": "2025-01-15T19:00:00Z",
      "venue": {"name": "Ice Arena Berlin"},
      "home": {
        "club": "Berlin Thunder",
        "team": "Men A",
        "stats": {"goalsFor": 5, "points": 3}
      },
      "away": {
        "club": "Hamburg Sharks",
        "team": "Men A",
        "stats": {"goalsFor": 3, "points": 0}
      },
      "matchStatus": {"key": "FINISHED", "name": "Finished"}
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total_items": 156,
    "total_pages": 8,
    "has_next": true,
    "has_prev": false
  }
}
```

### GET /public/tournaments/{alias}
```json
{
  "success": true,
  "data": {
    "id": "bishl-2024-25",
    "name": "BISHL 2024/25",
    "alias": "bishl-2024-25",
    "sportType": "Inline Hockey",
    "currentSeason": {
      "name": "Regular Season",
      "alias": "regular",
      "startDate": "2024-09-01T00:00:00Z"
    },
    "seasons": [
      {
        "name": "Regular Season",
        "alias": "regular",
        "startDate": "2024-09-01T00:00:00Z"
      }
    ]
  }
}
```

---

**End of Specification**
