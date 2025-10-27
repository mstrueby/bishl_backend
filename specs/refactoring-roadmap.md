
# BISHL Backend Refactoring Roadmap

*Generated: 2025 Post-Season Analysis*

---

## Critical Priority (Do First)

### 1. Version Control & Backup Strategy
**Effort:** Low | **Impact:** Critical | **Risk if ignored:** High

**Problem:**
- No visible git history or backup strategy
- Single point of failure for codebase

**Actions:**
- Initialize proper git repository with .gitignore
- Set up automated backups of MongoDB
- Create staging/production branch strategy
- Tag current state as v1.0.0

**Estimated Time:** 2-4 hours

---

### 2. Password Hashing Migration
**Effort:** Medium | **Impact:** High | **Risk if ignored:** High

**Problem:**
- Using bcrypt via passlib which is deprecated
- Security vulnerability over time

**Current Code Location:**
- `authentication.py` lines 11-17

**Actions:**
- Migrate to argon2-cffi (modern standard)
- Create migration script for existing password hashes
- Update AuthHandler class

**Estimated Time:** 4-6 hours

**Dependencies:**
```toml
argon2-cffi = "^23.1.0"
```

---

### 3. Assignment-Match Synchronization Bug
**Effort:** Medium | **Impact:** High | **Risk if ignored:** Medium

**Problem:**
- `check_assignment_conflicts.py` shows REF_ADMIN workflow creates assignments but doesn't update matches
- Referees marked as ASSIGNED but not actually in match document

**Current Code Location:**
- `routers/assignments.py` - assignment creation
- `routers/matches.py` - match updates
- Missing transaction support

**Actions:**
- Implement database transactions for assignment operations
- Add rollback mechanism if match update fails
- Create data repair script for existing conflicts

**Estimated Time:** 6-8 hours

---

## High Priority

### 4. Pydantic v2 Migration
**Effort:** High | **Impact:** High | **Risk if ignored:** Low

**Problem:**
- Using Pydantic v1 (1.10.18)
- Missing performance improvements and better validation
- Will become unsupported

**Current Impact:**
- All model files in `/models`
- 10+ router files

**Actions:**
- Update to Pydantic v2
- Replace `.dict()` with `.model_dump()`
- Update validators to use `@field_validator`
- Fix Config classes to ConfigDict

**Breaking Changes:**
```python
# Old (v1)
class Model(BaseModel):
    class Config:
        schema_extra = {...}
    
# New (v2)
from pydantic import ConfigDict
class Model(BaseModel):
    model_config = ConfigDict(json_schema_extra={...})
```

**Estimated Time:** 16-24 hours

---

### 5. Centralized Stats Calculation Service ✅ COMPLETE
**Effort:** Medium | **Impact:** Medium | **Risk if ignored:** Low

**Status:** ✅ **COMPLETED**

**What was done:**
- ✅ Created `services/stats_service.py` with `StatsService` class
- ✅ Extracted all calculation logic (match stats, standings, roster stats, player card stats)
- ✅ Added comprehensive logging with @log_performance decorator
- ✅ Maintained backward compatibility in `utils.py`
- ✅ Created validation script to verify correctness
- ✅ All stats calculations working identically to original implementation

**Files Created:**
- `services/stats_service.py` (~900 lines, well-documented)
- `validate_stats_refactoring.py` (comprehensive validation)
- `find_test_matches.py` (helper for testing)
- `specs/stats-service-refactoring-plan.md` (detailed spec)

**Estimated Time:** 8-12 hours ✅

---

### 6. Testing Infrastructure
**Effort:** High | **Impact:** High | **Risk if ignored:** Medium

**Problem:**
- No visible test suite
- Manual testing only
- Regression risks

**Actions:**
- Set up pytest
- Create test fixtures for MongoDB
- Add integration tests for critical workflows:
  - Match creation → scoring → standings
  - Referee assignment workflow
  - Player stats calculation
- Aim for 60%+ coverage on critical paths

**Estimated Time:** 20-30 hours

**Dependencies:**
```toml
pytest = "^7.4.0"
pytest-asyncio = "^0.21.0"
httpx = "^0.27.0"  # already installed
faker = "^20.0.0"
```

---

## Medium Priority

### 7. Error Handling Standardization ✅ COMPLETE
**Effort:** Medium | **Impact:** Medium | **Risk if ignored:** Low

**Status:** ✅ **COMPLETED**

**What was done:**
- ✅ Created `exceptions/custom_exceptions.py` with full exception hierarchy
- ✅ Added centralized exception handlers in `main.py`
- ✅ Configured structured logging with loguru in `logging_config.py`
- ✅ Migrated all routers to use custom exceptions (matches, roster, scores, penalties, players, etc.)
- ✅ Updated `services/stats_service.py` to use custom exceptions
- ✅ Created comprehensive documentation:
  - `specs/error-response-format.md` - Standard error format
  - `specs/deployment-checklist.md` - Deployment guidelines
  - `specs/api-error-examples.md` - Usage examples

**Files Created/Modified:**
- `exceptions/custom_exceptions.py` (new)
- `logging_config.py` (new)
- `main.py` (updated with exception handlers)
- All router files (migrated to custom exceptions)
- `services/stats_service.py` (migrated to custom exceptions)
- `utils.py` (added logging)
- `authentication.py` (using AuthenticationException)

**Estimated Time:** 8-12 hours ✅

---

### 8. Environment Configuration Cleanup ✅ COMPLETE
**Effort:** Low | **Impact:** Medium | **Risk if ignored:** Low

**Status:** ✅ **COMPLETED**

**What was done:**
- ✅ Created `config.py` with Pydantic Settings and full validation
- ✅ Documented all environment variables with descriptions and defaults
- ✅ Added validators for debug_level, CORS origins, JWT expiration
- ✅ Updated `main.py` to use settings for DB connection and CORS
- ✅ Updated `authentication.py` to use settings for JWT configuration
- ✅ Updated `utils.py` to use settings for DEBUG_LEVEL
- ✅ Created `.env.example` documenting all required variables
- ✅ Added convenience methods: `is_production()`, `get_db_url()`, `get_db_name()`

**Files Created/Modified:**
- `config.py` (new - centralized configuration)
- `.env.example` (new - documentation)
- `main.py` (updated to use settings)
- `authentication.py` (updated to use settings)
- `utils.py` (updated to use settings)

**Estimated Time:** 4-6 hours ✅

---

### 9. Authentication Token Refresh ✅ COMPLETE
**Effort:** Medium | **Impact:** Medium | **Risk if ignored:** Low

**Status:** ✅ **COMPLETED**

**What was done:**
- ✅ Implemented two-token system (access + refresh tokens)
- ✅ Access tokens expire after 15 minutes (short-lived)
- ✅ Refresh tokens expire after 7 days (long-lived)
- ✅ Added `POST /users/refresh` endpoint for token renewal
- ✅ Updated `POST /users/login` to return both tokens
- ✅ Used separate secrets for access and refresh tokens
- ✅ Stateless JWT implementation (no DB storage needed)
- ✅ Created comprehensive documentation with frontend implementation guide

**Files Created/Modified:**
- `authentication.py` (added refresh token methods)
- `routers/users.py` (updated login, added refresh endpoint)
- `specs/token-refresh-implementation.md` (new - complete guide)
- `.env.example` (updated comments)

**Frontend Changes Required:**
- Update login handler to store both tokens
- Implement axios interceptor for automatic token refresh
- Handle 401 errors by calling `/users/refresh`
- Redirect to login when refresh token expires

**Estimated Time:** 6-8 hours ✅

---

### 10. API Response Standardization ✅ COMPLETE
**Effort:** Low | **Impact:** Low | **Risk if ignored:** Low

**Status:** ✅ **COMPLETED**

**What was done:**
- ✅ Created `models/responses.py` with standard response models
- ✅ Created `utils/pagination.py` with pagination helpers
- ✅ Updated `routers/matches.py` with paginated GET /matches
- ✅ Updated `routers/players.py` with paginated GET /players and search
- ✅ Updated `routers/tournaments.py` with paginated GET /tournaments
- ✅ Updated `routers/clubs.py` with paginated GET /clubs
- ✅ Updated `routers/users.py` with paginated GET /referees
- ✅ Updated `routers/posts.py` with paginated GET /posts
- ✅ Updated `routers/documents.py` with paginated GET /documents and GET /categories/{category}
- ✅ Created comprehensive documentation in `specs/api-response-standardization.md`

**Files Updated:**
- `routers/tournaments.py` (GET /tournaments)
- `routers/clubs.py` (GET /clubs)
- `routers/users.py` (GET /referees)
- `routers/posts.py` (GET /posts)
- `routers/documents.py` (GET /documents, GET /categories/{category})

**Note:** Assignments router not updated as it has specialized response structures for match-specific and user-specific queries that don't fit standard pagination patterns.

**Estimated Time:** 6-8 hours ✅

---

## Low Priority (Nice to Have)

### 11. Database Query Optimization ⏸️ PARTIALLY COMPLETE
**Effort:** Medium | **Impact:** Medium | **Risk if ignored:** Low

**Status:** ⏸️ **PARTIALLY COMPLETED - POSTPONED**

**What was done:**
- ✅ Created `scripts/create_indexes.py` with comprehensive index strategy
- ✅ Documented all index purposes in `specs/database-optimization-plan.md`
- ✅ Created `services/performance_monitor.py` for query monitoring
- ✅ Tested index creation on dev database
- ⚠️ Identified player alias duplicates preventing unique index

**Remaining work (postponed):**
- [ ] Fix player alias duplicates in production
- [ ] Apply indexes to production database
- [ ] Refactor N+1 queries to use aggregation pipelines
- [ ] Verify index usage with explain() queries
- [ ] Implement query performance monitoring in production

**Estimated Time for completion:** 4-6 hours

---

### 12. API Documentation Enhancement ✅ COMPLETE
**Effort:** Low | **Impact:** Low | **Risk if ignored:** Very Low

**Status:** ✅ **COMPLETED**

**What was done:**
- ✅ Enhanced FastAPI app metadata with comprehensive API description
- ✅ Added OpenAPI tags for all endpoint categories
- ✅ Created detailed API usage guide with authentication examples
- ✅ Documented common patterns (pagination, filtering, error handling)
- ✅ Added endpoint reference with request/response examples
- ✅ Included best practices for token management and performance
- ✅ Fixed pagination import path conflict (moved to services/)

**Files Created/Modified:**
- `main.py` (enhanced with rich API documentation)
- `specs/api-usage-guide.md` (new - comprehensive guide)
- `services/pagination.py` (moved from utils/ to avoid conflict)
- All routers (updated import paths)

**Estimated Time:** 4-6 hours ✅

---

### 13. Import Scripts Consolidation
**Effort:** Medium | **Impact:** Low | **Risk if ignored:** Very Low

**Problem:**
- 10+ separate import scripts
- Duplicated connection logic
- No unified import framework

**Current Files:**
- `import_*.py` (10 files)

**Actions:**
- Create `services/import_service.py`
- Unified CLI for imports
- Better error handling and rollback

**Estimated Time:** 8-10 hours

---

### 14. Code Quality Tools
**Effort:** Low | **Impact:** Low | **Risk if ignored:** Very Low

**Actions:**
- Add black for formatting
- Add ruff for linting
- Add mypy for type checking
- Pre-commit hooks

**Estimated Time:** 2-4 hours

**Dependencies:**
```toml
black = "^23.0.0"
ruff = "^0.1.0"
mypy = "^1.7.0"
pre-commit = "^3.5.0"
```

---

## Summary Matrix

| Priority | Total Items | Total Effort (hours) | Risk Level |
|----------|-------------|---------------------|------------|
| Critical | 3 | 12-18 | High |
| High | 3 | 44-66 | Medium |
| Medium | 5 | 38-56 | Low |
| Low | 4 | 22-32 | Very Low |
| **TOTAL** | **15** | **116-172** | **Mixed** |

---

## Recommended Phased Approach

### Phase 1: Foundation (Week 1-2)
- Version control setup
- Password migration
- Assignment bug fix
- Environment configuration

**Total: ~26-38 hours**

### Phase 2: Modernization (Week 3-4)
- Pydantic v2 migration
- Error handling standardization
- Stats service extraction

**Total: ~32-48 hours**

### Phase 3: Quality (Week 5-6)
- Testing infrastructure
- API standardization
- Documentation

**Total: ~30-44 hours**

### Phase 4: Polish (Week 7+)
- Database optimization
- Import consolidation
- Code quality tools

**Total: ~28-42 hours**

---

## Notes

1. **Don't rush Pydantic v2** - It's breaking changes, test thoroughly
2. **Assignment bug is real** - Check `check_assignment_conflicts.py` output
3. **Consider MongoDB transactions** - Motor supports them since v3.0
4. **Keep backward compatibility** - Season 2 shouldn't break Season 1 data
5. **Document as you go** - Future you will thank present you

---

## Migration Checklist Template

```markdown
- [ ] Create feature branch
- [ ] Write tests for current behavior
- [ ] Make changes
- [ ] Run test suite
- [ ] Manual testing
- [ ] Update documentation
- [ ] Code review
- [ ] Deploy to staging
- [ ] Production deployment
- [ ] Monitor for issues
```

---

*Last updated: Post-Season 1*
*Next review: Before Season 2 kickoff*
