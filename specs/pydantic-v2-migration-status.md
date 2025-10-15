
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

## Remaining Files 🔄

### models/documents.py
- Uses old `@validator` decorator
- Has `Config` class instead of `model_config`

### models/matches.py
- Uses old `@validator` decorator
- Has `Config` class instead of `model_config`
- Import uses deprecated `BaseSettings`

### models/posts.py
- Uses old `@validator` decorator
- Has `Config` class instead of `model_config`

### models/messages.py
- Uses old `@validator` decorator
- Has `Config` class instead of `model_config`

### models/assignments.py
- Uses old `@validator` decorator
- Has `Config` class instead of `model_config`

### models/players.py
- Uses old `@validator` decorator
- Has `Config` class instead of `model_config`
- Has custom `.dict()` method that needs updating to `.model_dump()`

### models/venues.py
- Uses old `@validator` decorator
- Has `Config` class instead of `model_config`

### models/configs.py
- Already appears to be v2 compatible (no validators, simple structure)

## Migration Checklist
- [x] Update PyObjectId class to use __get_pydantic_core_schema__
- [x] Replace @validator with @field_validator
- [x] Add mode='before' to validators
- [x] Make validators classmethods
- [x] Replace Config class with model_config dict
- [ ] Update .dict() calls to .model_dump()
- [ ] Update .parse_obj() to .model_validate()
- [ ] Test all endpoints after migration

## Next Steps
1. Continue with models/documents.py
2. Then models/matches.py
3. Then models/posts.py
4. Then models/messages.py
5. Then models/assignments.py
6. Then models/players.py
7. Then models/venues.py
8. Update utils.py if needed
9. Test all routers
