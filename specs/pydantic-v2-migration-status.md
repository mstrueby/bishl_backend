
# Pydantic v2 Migration Status

## Overview
Migration from Pydantic v1 to v2 for all model files in the BISHL backend.

## Completed Files ✅

### 1. models/users.py
- ✅ Replaced `@validator` with `@field_validator`
- ✅ Changed `Config` class to `model_config = ConfigDict(...)`
- ✅ Updated `PyObjectId` to use `__get_pydantic_core_schema__` instead of `__get_validators__`
- ✅ Added proper imports for Pydantic v2

### 2. models/clubs.py
- ✅ Replaced `@validator` with `@field_validator`
- ✅ Changed `Config` class to `model_config` dict
- ✅ Updated all validators to use `mode='before'` and `@classmethod`
- ✅ Commented out old validators for reference

### 3. models/tournaments.py
- ✅ Replaced `@validator` with `@field_validator`
- ✅ Changed `Config` class to `model_config` dict
- ✅ Updated all validators to use proper v2 syntax
- ✅ Added proper field validation methods

## All Model Files Completed! ✅

All model files have been successfully migrated to Pydantic v2.

## Summary of Changes

### 4. models/documents.py ✅
- ✅ Replaced `Config` class with `model_config`
- ✅ Updated `PyObjectId` to use `__get_pydantic_core_schema__`
- ✅ Already had `@field_validator` decorators

### 5. models/posts.py ✅
- ✅ Replaced `Config` class with `model_config`
- ✅ Updated `PyObjectId` to use `__get_pydantic_core_schema__`
- ✅ Already had `@field_validator` decorators

### 6. models/messages.py ✅
- ✅ Replaced `Config` class with `model_config`
- ✅ Updated `PyObjectId` to use `__get_pydantic_core_schema__`
- ✅ Already had `@field_validator` decorators

### 7. models/assignments.py ✅
- ✅ Replaced `@validator` with `@field_validator`
- ✅ Replaced `Config` class with `model_config`
- ✅ Updated `PyObjectId` to use `__get_pydantic_core_schema__`

### 8. models/venues.py ✅
- ✅ Replaced `Config` class with `model_config`
- ✅ Updated `PyObjectId` to use `__get_pydantic_core_schema__`
- ✅ Commented out validators

### 9. models/matches.py ✅
- ✅ Replaced `@validator` with `@field_validator`
- ✅ Replaced `Config` class with `model_config`
- ✅ Updated `PyObjectId` to use `__get_pydantic_core_schema__`
- ✅ Removed deprecated `BaseSettings` import

### 10. models/players.py ✅
- ✅ Replaced `Config` class with `model_config`
- ✅ Updated `PyObjectId` to use `__get_pydantic_core_schema__`
- ✅ Updated `.dict()` method to `.model_dump()`
- ✅ Updated schema_extra to json_schema_extra

### 11. models/configs.py ✅
- ✅ Already v2 compatible (no validators, simple structure)

## Migration Checklist
- [x] Update PyObjectId class to use __get_pydantic_core_schema__
- [x] Replace @validator with @field_validator
- [x] Add mode='before' to validators
- [x] Make validators classmethods
- [x] Replace Config class with model_config dict
- [x] Update .dict() calls to .model_dump() (in PlayerDB and utils.py)
- [ ] Update .parse_obj() to .model_validate() in routers (if any)
- [ ] Update .dict() to .model_dump() in routers (if any)
- [ ] Install pydantic-core dependency
- [ ] Test all endpoints after migration

## Next Steps
1. ✅ All model files migrated
2. ✅ Updated utils.py `.dict()` to `.model_dump()`
3. **Install pydantic-core:**
   - The error shows `ModuleNotFoundError: No module named 'pydantic_core'`
   - This is required for Pydantic v2
4. **Search and update routers for:**
   - `.dict()` → `.model_dump()`
   - `.parse_obj()` → `.model_validate()`
   - `schema_extra` → `json_schema_extra` (if any)
5. **Test critical endpoints:**
   - User authentication
   - Match creation/updates
   - Player stats
   - Tournament/season management
6. **Run the application and check for errors**
