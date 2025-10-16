
# Stats Calculation Service - Refactoring Plan

## Executive Summary

Consolidate scattered statistics calculation logic from `utils.py` and various routers into a dedicated `services/stats_service.py` module. This will improve maintainability, testability, and performance tracking.

---

## Current State Analysis

### Files Affected:
- **utils.py** (~700 lines of stats code, lines 156-850)
- **routers/matches.py** (calls stats after match updates)
- **routers/scores.py** (calls stats after score changes)
- **routers/penalties.py** (calls stats after penalty changes)
- **routers/roster.py** (calls roster stats)

### Functions to Extract:

#### From utils.py:
1. `calc_match_stats(match_status, finish_type, standings_setting, home_score, away_score)` 
   - **Purpose:** Calculate points/wins/losses for a single match
   - **Why extract:** Core business logic, reused in multiple routers
   
2. `calc_standings_per_round(mongodb, t_alias, s_alias, r_alias)`
   - **Purpose:** Aggregate all match stats for a round into standings
   - **Why extract:** Complex aggregation logic, needs centralized error handling

3. `calc_standings_per_matchday(mongodb, t_alias, s_alias, r_alias, md_alias)`
   - **Purpose:** Aggregate match stats for a specific matchday
   - **Why extract:** Similar to round standings, should be grouped

4. `calc_roster_stats(mongodb, match_id, team_flag)`
   - **Purpose:** Calculate goals/assists/penalties for roster players in a match
   - **Why extract:** ~150 lines, complex player data processing

5. `calc_player_card_stats(mongodb, player_ids, t_alias, s_alias, r_alias, md_alias, token_payload)`
   - **Purpose:** Calculate season/round statistics for player cards (500+ lines!)
   - **Why extract:** Largest function, handles called matches, needs refactoring
   - **Current issues:** Multiple nested helpers, complex logic, performance concerns

---

## Refactoring Goals

### 1. **Separation of Concerns**
   - Stats calculation logic → `services/stats_service.py`
   - Database queries → isolated in service layer
   - Business rules → clearly defined functions

### 2. **Improved Maintainability**
   - Single source of truth for stats calculations
   - Easier to modify standings rules
   - Clear function naming and documentation

### 3. **Performance Optimization**
   - Centralized query optimization
   - Batch processing where possible
   - Clear performance logging

### 4. **Better Error Handling**
   - Consistent error messages
   - Graceful degradation
   - Proper exception handling

### 5. **Testability**
   - Isolated functions easy to unit test
   - Mock database interactions
   - Test different scenarios independently

---

## Step-by-Step Implementation Plan

### Phase 1: Create Service Structure ✅ COMPLETE

#### Step 1.1: Create Service Directory & Base File ✅
```bash
mkdir -p services
touch services/__init__.py
touch services/stats_service.py
```

#### Step 1.2: Define Service Class Structure ✅
Create `StatsService` class with clear responsibilities:
- Match statistics calculation
- Standings aggregation
- Player statistics tracking
- Roster statistics

#### Step 1.3: Add Logging Infrastructure ✅
- Import and configure logging
- Add performance timing decorators
- Create debug level controls

### Phase 2: Extract Match Stats Logic ✅ COMPLETE

#### Step 2.1: Move `calc_match_stats()` 
**From:** `utils.py` lines ~250-350
**To:** `services/stats_service.py` → `StatsService.calculate_match_stats()`

**Why this order:** It's the foundation - other stats depend on this

**Changes needed:**
- Make it a class method
- Add type hints
- Improve error messages for unknown finish types
- Add validation for standings_settings

#### Step 2.2: Move standings helper `fetch_standings_settings()`
**From:** `utils.py` 
**To:** `services/stats_service.py` → `StatsService.get_standings_settings()`

**Why:** Always used together with match stats

### Phase 3: Extract Standings Aggregation ✅ COMPLETE

#### Step 3.1: Move `calc_standings_per_round()`
**From:** `utils.py` lines ~400-600
**To:** `services/stats_service.py` → `StatsService.aggregate_round_standings()`

**Improvements:**
- Extract team key generation logic to helper
- Simplify nested loops
- Add progress logging for large tournaments
- Return structured results

#### Step 3.2: Move `calc_standings_per_matchday()`
**From:** `utils.py` 
**To:** `services/stats_service.py` → `StatsService.aggregate_matchday_standings()`

**Improvements:**
- Share common logic with round standings
- Extract aggregation logic to reusable helpers

### Phase 4: Extract Roster Stats ✅ COMPLETE

#### Step 4.1: Move `calc_roster_stats()`
**From:** `utils.py` lines ~700-850
**To:** `services/stats_service.py` → `StatsService.calculate_roster_stats()`

**Improvements:**
- Separate score counting from penalty counting
- Extract player lookup to helper
- Add validation for team_flag parameter

### Phase 5: Refactor Player Card Stats ✅ COMPLETE (4-5 hours)

#### Step 5.1: Break Down `calc_player_card_stats()` - THE BIG ONE ✅
**From:** `utils.py` (500+ lines!)
**To:** Multiple focused methods in `StatsService`

**New structure:**
```python
class StatsService:
    async def calculate_player_card_stats(...)  # Main entry point
    
    # Helper methods:
    async def _initialize_player_stats(...)
    async def _process_round_stats(...)
    async def _process_matchday_stats(...)
    async def _update_player_stats_from_roster(...)
    async def _save_player_stats(...)
    async def _handle_called_teams(...)
```

**Why break it down:**
- Original function is 500+ lines (too complex)
- Has 8+ nested helper functions
- Mixes multiple responsibilities
- Hard to test and debug

#### Step 5.2: Optimize Database Queries
- Batch player lookups instead of individual queries
- Use aggregation pipelines where possible
- Cache tournament/season data

#### Step 5.3: Improve Called Teams Logic
- Extract `_process_called_teams_assignments()` 
- Simplify team assignment creation
- Add better error handling for API calls

### Phase 6: Update Router Imports (1 hour)

#### Step 6.1: Update `routers/matches.py`
Replace:
```python
from utils import calc_match_stats, calc_standings_per_round, calc_standings_per_matchday, calc_roster_stats, calc_player_card_stats
```

With:
```python
from services.stats_service import StatsService

stats_service = StatsService()
```

#### Step 6.2: Update all router calls
- `routers/scores.py` - use `stats_service.*` methods
- `routers/penalties.py` - use `stats_service.*` methods  
- `routers/roster.py` - use `stats_service.*` methods
- `routers/matches.py` - use `stats_service.*` methods

#### Step 6.3: Keep backward compatibility (temporarily)
- Leave original functions in `utils.py` with deprecation warnings
- They call new service methods
- Remove in next refactoring phase

### Phase 7: Add Comprehensive Logging (1 hour)

#### Step 7.1: Add Performance Metrics
- Log execution time for each stats calculation
- Track number of players/matches processed
- Identify slow operations

#### Step 7.2: Add Debug Information
- Log when stats are skipped (PHASE 1 optimization)
- Show which players are being updated
- Track standings changes

### Phase 8: Testing & Validation (2-3 hours)

#### Step 8.1: Create Test Match Scenarios
- Regular time win/loss/draw
- Overtime scenarios
- Shootout scenarios
- Forfeited matches

#### Step 8.2: Validate Stats Consistency
- Compare old vs new calculations
- Verify standings aggregation
- Check player card stats accuracy

#### Step 8.3: Performance Testing
- Measure improvement in match updates
- Test with large tournaments
- Validate PHASE 1 optimization still works

---

## File Structure After Refactoring

```
services/
├── __init__.py
└── stats_service.py
    ├── StatsService (class)
    │   ├── Match Stats Methods
    │   │   ├── calculate_match_stats()
    │   │   └── get_standings_settings()
    │   ├── Standings Methods
    │   │   ├── aggregate_round_standings()
    │   │   ├── aggregate_matchday_standings()
    │   │   └── _calculate_team_standings()
    │   ├── Player Stats Methods
    │   │   ├── calculate_roster_stats()
    │   │   ├── calculate_player_card_stats()
    │   │   ├── _process_round_stats()
    │   │   ├── _process_matchday_stats()
    │   │   ├── _update_player_stats_from_roster()
    │   │   └── _save_player_stats()
    │   └── Helper Methods
    │       ├── _create_team_key()
    │       ├── _handle_called_teams()
    │       └── _initialize_player_stats()
```

---

## Key Benefits

### 1. **Maintainability**
   - ✅ Single file for all stats logic (~500-600 lines vs scattered 700+ lines)
   - ✅ Clear function responsibilities
   - ✅ Easy to find and fix bugs

### 2. **Performance**
   - ✅ Centralized optimization points
   - ✅ Easy to add caching layer
   - ✅ Clear performance logging

### 3. **Testing**
   - ✅ Isolated functions for unit tests
   - ✅ Mock database easily
   - ✅ Test edge cases independently

### 4. **Future Enhancements**
   - ✅ Easy to add new stat types
   - ✅ Simple to modify standings rules
   - ✅ Can add real-time stats updates

---

## Risks & Mitigation

### Risk 1: Breaking Existing Functionality
**Mitigation:** 
- Keep utils.py functions as wrappers initially
- Extensive testing before removing old code
- Deploy with feature flag

### Risk 2: Performance Regression
**Mitigation:**
- Add performance benchmarks
- Test with real tournament data
- Keep PHASE 1 optimizations

### Risk 3: Database Query Changes
**Mitigation:**
- Review all aggregation pipelines
- Add query explain() for optimization
- Monitor production performance

---

## Estimated Timeline

| Phase | Task | Time | Priority |
|-------|------|------|----------|
| 1 | Create service structure | 2-3h | High |
| 2 | Extract match stats | 2h | High |
| 3 | Extract standings aggregation | 3h | High |
| 4 | Extract roster stats | 2h | Medium |
| 5 | Refactor player card stats | 4-5h | High |
| 6 | Update router imports | 1h | High |
| 7 | Add logging | 1h | Low |
| 8 | Testing & validation | 2-3h | High |
| **Total** | | **17-20 hours** | |

---

## Success Criteria

- ✅ All stats calculations work identically to current implementation
- ✅ No performance degradation (ideally improvement)
- ✅ All router tests pass
- ✅ Code coverage >60% for stats service
- ✅ Clear performance logging in place
- ✅ Documentation updated

---

## Next Steps After This Refactoring

1. Add caching layer for frequently accessed stats
2. Implement real-time stats updates via WebSocket
3. Create stats calculation queue for async processing
4. Add stats history/versioning for auditing

---

## Notes

- Keep `DEBUG_LEVEL` environment variable for logging control
- Maintain backward compatibility during transition
- Document all breaking changes
- Update API documentation with new service architecture
