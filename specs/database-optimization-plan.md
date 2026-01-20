
# Database Query Optimization Plan

*Created: 2025-01-22*  
*Priority: Low*  
*Estimated Effort: 8-12 hours*

---

## Executive Summary

Optimize MongoDB queries across the BISHL backend by adding appropriate indexes, refactoring N+1 queries, using aggregation pipelines for complex queries, and implementing query performance monitoring.

---

## Current State Analysis

### Performance Concerns

1. **Missing Indexes**
   - No documented index strategy
   - Potential slow queries on common lookups
   - No compound indexes for complex filters

2. **N+1 Query Patterns**
   - Stats calculations may fetch data multiple times
   - Roster operations iterate over players
   - Match listings don't use projections

3. **No Query Performance Monitoring**
   - No slow query logging
   - No performance metrics tracked
   - Hard to identify bottlenecks

---

## Proposed Optimizations

### Phase 1: Index Analysis & Creation (3-4 hours)

#### Common Query Patterns to Index

**Matches Collection:**
```python
# Frequently queried fields with documented purposes

- {"_id": 1}  # Default MongoDB index
- {"tournament.alias": 1, "season.alias": 1, "round.alias": 1}
  # Purpose: Fetch matches for standings calculations by round
  # Used in: StatsService.calculate_standings(), rounds router
  
- {"tournament.alias": 1, "season.alias": 1, "matchday.alias": 1}
  # Purpose: Fetch matches for specific matchday displays
  # Used in: matchdays router, match listings
  
- {"status": 1, "startDate": 1}
  # Purpose: Filter upcoming/completed matches sorted by date
  # Used in: GET /matches with status filters, homepage queries
  
- {"home.teamId": 1}
  # Purpose: Fetch all home matches for a team
  # Used in: Team schedule views, team stats calculations
  
- {"away.teamId": 1}
  # Purpose: Fetch all away matches for a team
  # Used in: Team schedule views, team stats calculations
```

**Players Collection:**
```python
- {"_id": 1}  # Default MongoDB index

- {"alias": 1}  # Unique index
  # Purpose: Direct player lookups by URL-safe identifier
  # Used in: GET /players/{alias}, roster operations
  # NOTE: Currently has duplicates in DB - must be cleaned before unique constraint works
  
- {"lastName": 1, "firstName": 1, "yearOfBirth": 1}
  # Purpose: Player search and duplicate detection during imports
  # Used in: import_players.py, import_hobby_players.py, player search queries
  
- {"assignedClubs.clubId": 1}
  # Purpose: Fetch all players for a club
  # Used in: Club roster views, team assignment operations
```

**Tournaments Collection:**
```python
- {"alias": 1}  # Unique index
  # Purpose: Direct tournament lookups by URL-safe identifier
  # Used in: GET /tournaments/{alias}, all tournament operations
```

**Users Collection:**
```python
- {"email": 1}  # Unique index
  # Purpose: User authentication and login
  # Used in: POST /users/login, user account lookups
  
- {"club.clubId": 1}
  # Purpose: Fetch all users (referees/admins) for a club
  # Used in: Assignment operations, referee availability checks
```

**Assignments Collection:**
```python
- {"matchId": 1}
  # Purpose: Fetch all referee assignments for a match
  # Used in: GET /matches/{id}/assignments, assignment conflict checks
  
- {"userId": 1}
  # Purpose: Fetch all assignments for a referee
  # Used in: Referee schedule views, availability checks
  
- {"status": 1}
  # Purpose: Filter assignments by acceptance status
  # Used in: Pending assignments dashboard, assignment reports
```

#### Known Issues

**Player Alias Duplicates:**
The `alias` field in the players collection currently contains duplicate values, preventing creation of the unique index. Before the unique index can be applied in production:

1. Run duplicate detection query:
   ```javascript
   db.players.aggregate([
     {$group: {_id: "$alias", count: {$sum: 1}}},
     {$match: {count: {$gt: 1}}},
     {$sort: {count: -1}}
   ])
   ```

2. Manually resolve duplicates by updating alias values to be unique
3. Re-run `python scripts/create_indexes.py --prod` to create the unique index
```

#### Index Creation Script

Create `scripts/create_indexes.py`:
```python
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
import os
from logging_config import logger

async def create_indexes():
    """Create all necessary indexes for optimal query performance"""
    
    client = AsyncIOMotorClient(os.environ['DB_URL'])
    db = client[os.environ['DB_NAME']]
    
    logger.info("Starting index creation...")
    
    # Matches indexes
    await db.matches.create_index([
        ("tournament.alias", 1),
        ("season.alias", 1),
        ("round.alias", 1)
    ], name="tournament_season_round_idx")
    
    await db.matches.create_index([
        ("tournament.alias", 1),
        ("season.alias", 1),
        ("matchday.alias", 1)
    ], name="tournament_season_matchday_idx")
    
    await db.matches.create_index([("status", 1), ("startDate", 1)], 
                                   name="status_startdate_idx")
    
    await db.matches.create_index([("home.teamId", 1)], name="home_team_idx")
    await db.matches.create_index([("away.teamId", 1)], name="away_team_idx")
    
    # Players indexes
    await db.players.create_index([("alias", 1)], unique=True, name="alias_unique_idx")
    await db.players.create_index([
        ("lastName", 1),
        ("firstName", 1),
        ("yearOfBirth", 1)
    ], name="player_lookup_idx")
    
    await db.players.create_index([("assignedClubs.clubId", 1)], 
                                   name="assigned_clubs_idx")
    
    # Tournaments indexes
    await db.tournaments.create_index([("alias", 1)], unique=True, 
                                      name="tournament_alias_unique_idx")
    
    # Users indexes
    await db.users.create_index([("email", 1)], unique=True, name="email_unique_idx")
    await db.users.create_index([("club.clubId", 1)], name="club_idx")
    
    # Assignments indexes
    await db.assignments.create_index([("matchId", 1)], name="match_idx")
    await db.assignments.create_index([("userId", 1)], name="user_idx")
    await db.assignments.create_index([("status", 1)], name="status_idx")
    
    logger.info("Index creation completed successfully")
    
    # List all indexes for verification
    for collection_name in ["matches", "players", "tournaments", "users", "assignments"]:
        indexes = await db[collection_name].index_information()
        logger.info(f"{collection_name} indexes: {list(indexes.keys())}")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(create_indexes())
```

---

### Phase 2: Query Optimization (3-4 hours)

#### Optimize Stats Calculations

Replace multiple queries with aggregation pipeline in `services/stats_service.py`:

**Before (N+1 pattern):**
```python
# Fetches tournament, then iterates seasons, rounds, matchdays
tournament = await db["tournaments"].find_one({"alias": t_alias})
for season in tournament["seasons"]:
    for round in season["rounds"]:
        for matchday in round["matchdays"]:
            # Multiple database hits
```

**After (Aggregation pipeline):**
```python
pipeline = [
    {"$match": {"alias": t_alias}},
    {"$unwind": "$seasons"},
    {"$match": {"seasons.alias": s_alias}},
    {"$unwind": "$seasons.rounds"},
    {"$match": {"seasons.rounds.alias": r_alias}},
    {"$project": {
        "matchday": "$seasons.rounds.matchdays",
        "settings": "$seasons.rounds.settings"
    }}
]
result = await db["tournaments"].aggregate(pipeline).to_list(1)
```

#### Use Projections to Limit Data Transfer

**Before:**
```python
matches = await db["matches"].find(filter).to_list(1000)
# Fetches entire match documents
```

**After:**
```python
matches = await db["matches"].find(
    filter,
    projection={
        "_id": 1,
        "status": 1,
        "home.teamId": 1,
        "away.teamId": 1,
        "scores": 1
    }
).to_list(1000)
```

---

### Phase 3: Query Performance Monitoring (2-3 hours)

#### Add Query Timing Decorator

Create `services/performance_monitor.py`:
```python
import time
from functools import wraps
from logging_config import logger

def monitor_query(operation_name: str):
    """Decorator to monitor database query performance"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                elapsed = time.time() - start_time
                
                if elapsed > 1.0:  # Log slow queries (> 1 second)
                    logger.warning(
                        f"Slow query detected: {operation_name}",
                        extra={
                            "operation": operation_name,
                            "duration_seconds": round(elapsed, 3),
                            "function": func.__name__
                        }
                    )
                else:
                    logger.debug(
                        f"Query completed: {operation_name}",
                        extra={
                            "operation": operation_name,
                            "duration_seconds": round(elapsed, 3)
                        }
                    )
                
                return result
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error(
                    f"Query failed: {operation_name}",
                    extra={
                        "operation": operation_name,
                        "duration_seconds": round(elapsed, 3),
                        "error": str(e)
                    }
                )
                raise
        return wrapper
    return decorator
```

**Usage:**
```python
from services.performance_monitor import monitor_query

@monitor_query("fetch_match_standings")
async def fetch_standings(t_alias, s_alias, r_alias):
    # Database query here
    pass
```

---

## Implementation Checklist

### Phase 1: Indexes
- [x] Create `scripts/create_indexes.py`
- [x] Test index creation on dev database
- [x] Document each index purpose
- [ ] Fix player alias duplicates before applying unique index
- [ ] Run explain() on common queries to verify index usage
- [ ] Apply indexes to production (during low-traffic window)

### Phase 2: Query Optimization
- [ ] Identify top 10 most-called queries
- [ ] Refactor stats calculations to use aggregation
- [ ] Add projections to match listings
- [ ] Optimize player lookup queries
- [ ] Test performance improvements

### Phase 3: Monitoring
- [ ] Create `services/performance_monitor.py`
- [ ] Add @monitor_query to critical operations
- [ ] Set up slow query alerting threshold
- [ ] Create performance dashboard (future)

---

## Success Metrics

- ✅ All common queries use appropriate indexes
- ✅ No N+1 query patterns in hot paths
- ✅ Average query response time < 100ms
- ✅ Slow queries (>1s) logged and tracked
- ✅ 50%+ reduction in data transferred for list operations

---

## Risks & Mitigation

**Risk:** Index creation locks collection  
**Mitigation:** Use background index creation, schedule during off-hours

**Risk:** Aggregation pipelines complex to maintain  
**Mitigation:** Add comprehensive comments and unit tests

**Risk:** Over-indexing increases write overhead  
**Mitigation:** Only index frequently queried fields, monitor write performance

---

*Ready for implementation after Phase 7 (Error Handling) completion*
