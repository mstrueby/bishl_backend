
# BISHL Backend Refactoring Roadmap

*Generated: 2024 Post-Season Analysis*

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

### 5. Centralized Stats Calculation Service
**Effort:** Medium | **Impact:** Medium | **Risk if ignored:** Low

**Problem:**
- `calc_roster_stats`, `calc_standings`, `calc_player_card_stats` scattered
- Similar logic in `utils.py` lines 500+ and multiple routers
- Difficult to maintain consistency

**Current Code Location:**
- `utils.py` lines 156-850
- `routers/scores.py`
- `routers/penalties.py`
- `routers/roster.py`

**Actions:**
- Create `services/stats_service.py`
- Extract all calculation logic
- Create unified API for stats updates
- Add proper logging

**Estimated Time:** 8-12 hours

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

### 7. Error Handling Standardization
**Effort:** Medium | **Impact:** Medium | **Risk if ignored:** Low

**Problem:**
- Inconsistent HTTPException usage
- No centralized error logging
- Poor error messages for debugging

**Current Code Location:**
- All router files
- `utils.py` helper functions

**Actions:**
- Create `exceptions/custom_exceptions.py`
- Create exception handlers in `main.py`
- Standardize error response format
- Add structured logging (loguru)

**Estimated Time:** 8-12 hours

---

### 8. Environment Configuration Cleanup
**Effort:** Low | **Impact:** Medium | **Risk if ignored:** Low

**Problem:**
- Environment variables scattered throughout code
- No validation at startup
- DEBUG_LEVEL as int directly accessed

**Current Code Location:**
- `utils.py` line 7-8
- Various router files

**Actions:**
- Create `config.py` with Pydantic Settings
- Validate all env vars at startup
- Type-safe configuration access
- Document all required env vars

**Estimated Time:** 4-6 hours

**Example:**
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    db_url: str
    db_name: str
    be_api_url: str
    debug_level: int = 0
    
    class Config:
        env_file = ".env"
```

---

### 9. Authentication Token Refresh
**Effort:** Medium | **Impact:** Medium | **Risk if ignored:** Low

**Problem:**
- No refresh token mechanism
- Users logged out after timeout
- Poor UX for long sessions

**Current Code Location:**
- `authentication.py`
- `routers/users.py`

**Actions:**
- Implement refresh token pattern
- Add refresh endpoint
- Update frontend to use refresh tokens

**Estimated Time:** 6-8 hours

---

### 10. API Response Standardization
**Effort:** Low | **Impact:** Low | **Risk if ignored:** Low

**Problem:**
- Inconsistent response formats
- Some return JSONResponse, others models
- No pagination standard

**Actions:**
- Create standard response wrapper
- Implement pagination helper
- Update all endpoints to use standard format

**Estimated Time:** 6-8 hours

---

## Low Priority (Nice to Have)

### 11. Database Query Optimization
**Effort:** Medium | **Impact:** Medium | **Risk if ignored:** Low

**Problem:**
- No indexes documented
- Potential N+1 queries in stats calculation
- No query performance monitoring

**Actions:**
- Add MongoDB indexes for common queries
- Use aggregation pipeline for complex queries
- Add query performance logging

**Estimated Time:** 8-12 hours

---

### 12. API Documentation Enhancement
**Effort:** Low | **Impact:** Low | **Risk if ignored:** Very Low

**Problem:**
- Basic FastAPI auto-docs only
- No examples in OpenAPI schema
- Missing description for many endpoints

**Actions:**
- Add detailed docstrings to all endpoints
- Add request/response examples
- Create API usage guide

**Estimated Time:** 4-6 hours

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
