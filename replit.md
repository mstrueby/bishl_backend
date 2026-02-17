# BISHL Backend API

## Overview

BISHL (Berlin Inline Skater Hockey League) is a sports league management backend API built with FastAPI and MongoDB. The system manages hockey tournaments, matches, teams, players, referees, and statistics for an inline hockey league in Berlin.

The API handles:
- Tournament and season management with rounds and matchdays
- Match scheduling, scoring, and penalty tracking
- Player registration, team assignments, and eligibility rules
- Referee assignment and scheduling
- Statistics calculation and standings aggregation
- User authentication with role-based access control
- Document and post management for league communications

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Core Framework
- **FastAPI**: Async Python web framework for the REST API
- **Motor**: Async MongoDB driver for non-blocking database operations
- **Pydantic**: Data validation and serialization with strict model definitions

### Database Design
- **MongoDB**: Document database storing all league data
- **Collections**: tournaments, matches, players, clubs, users, assignments, venues, documents, posts, configs, messages
- **Embedded Documents**: Seasons, rounds, and matchdays are embedded within tournament documents for hierarchical data access

### Authentication System
- **JWT Tokens**: Short-lived access tokens (30 min) with separate refresh tokens
- **Password Hashing**: Argon2 (new standard) with bcrypt fallback for legacy passwords
- **Role-Based Access**: Roles include ADMIN, REFEREE, PLAYER_ADMIN, CLUB_ADMIN, USER

### API Structure
- RESTful endpoints organized by resource type in `/routers/`
- Standard response format with success flag and data payload
- HATEOAS links for resource navigation
- Pagination support with configurable results per page

### Statistics Service
- Aggregates match statistics for standings and player stats
- Calculates team standings based on configurable point systems
- Tracks player performance across tournaments and seasons
- Handles "called" player logic for team eligibility assignments

### External Integrations
- **Cloudinary**: Image upload and management for player photos and club logos
- **ISHD API**: Integration with German inline hockey federation for player license verification
- **Email Service**: FastAPI-Mail for notifications (production only)
- **Genderize API**: Player gender detection from first names

### Data Import Scripts
- CSV-based import scripts for players, matches, referees, venues
- Support for both development and production database targets
- Migration scripts for data updates and password upgrades

### Roster Management (Updated February 2026)
- **Consolidated Roster Object**: All roster-related data is now nested at `match.team.roster` instead of flat fields
- **Roster Structure**: `{ players: [], status, published, eligibilityTimestamp, eligibilityValidator, coach, staff }`
- **Status Workflow**: DRAFT → SUBMITTED → APPROVED (with INVALID for reset)
- **Atomic Updates**: Single PUT endpoint updates all roster fields atomically via `RosterUpdate` model
- **Backward Compatibility**: Legacy flat structure (roster as list + rosterStatus field) is auto-converted on read
- **Migration Script**: `scripts/migrate_roster_structure.py` transforms existing documents to new structure
- **Transient Fields**: `displayFirstName`, `displayLastName`, `imageUrl`, `imageVisible` on EventPlayer are NOT persisted in roster data — they are populated from player master data on read only
- **Eligibility Reset**: When roster status changes to DRAFT or SUBMITTED, all players' `eligibilityStatus` resets to UNKNOWN, `invalidReasonCodes` clears, and roster-level `eligibilityTimestamp`/`eligibilityValidator` are set to None

### License Validation & Suspension Checking (Added January 2026)
- **Suspension Validation**: PlayerAssignmentService checks player.suspensions for active suspensions during license validation
- **Suspension Rules**: 
  - `globalLock=true`: Invalidates ALL teams
  - `globalLock=false` with `teamIds`: Only invalidates specified teams
  - `globalLock=null/missing`: Defaults to invalidating all teams (safe default)
- **CLUB_ADMIN Authorization**: PUT roster endpoint validates CLUB_ADMIN can only edit their own team; SUBMITTED rosters only editable by home team
- **Validate Endpoint**: POST `/matches/{id}/{team}/roster/validate` validates all roster players, updates eligibilityStatus and invalidReasonCodes per player, sets roster status to APPROVED (all valid) or INVALID
  - **Called Players**: Validates against origin team license (calledFromTeam), counts playUpTrackings occurrences (<=4 VALID, >=5 INVALID with CALLED_LIMIT_EXCEEDED), never modifies player DB data for called-count invalidity
  - **Regular Players**: Validates against match team assignment, propagates invalidReasonCodes from player license data
- **Auto-Reset**: When roster.players is updated, status resets to DRAFT and eligibility metadata is cleared
- **Auto-Validation on Player Read**: 
  - GET `/players/{id}` always triggers fresh license validation before returning
  - GET `/players` has optional `validate` query parameter (default: false) for opt-in validation
  - Roster reads do NOT trigger validation (as required)

### MatchSettings Hierarchy Inheritance (Added February 2026)
- **MatchSettings Model**: `{ numOfPeriods, periodLengthMin, overtime, numOfPeriodsOvertime, periodLengthMinOvertime, shootout, refereePoints }`
- **Hierarchy Levels**: tournament → season → round → matchday → match
- **Season-Level Default**: `matchSettings` added to `SeasonBase`/`SeasonUpdate` as the baseline default for all matches in a season
- **Match-Level Override**: `matchSettings` added to `MatchBase`/`MatchDB`/`MatchUpdate`/`MatchListBase` for per-match overrides
- **Inheritance Resolution**: On read, if a level has no `matchSettings`, it inherits from the nearest parent: match → matchday → round → season
- **matchSettingsSource Field**: Every response includes `matchSettingsSource` (string: "season", "round", "matchday", "match", or null) indicating where the settings came from
- **Full Replace**: Match-level overrides replace the entire MatchSettings object (no field-by-field merging)
- **No Database Migration**: All fields remain Optional. Null means "inherit from parent." Past seasons are untouched.
- **Batch Resolution**: List endpoints use `resolve_match_settings_batch()` in `services/match_settings_service.py` to batch tournament lookups and avoid N+1 queries
- **Affected Endpoints**: All GET match endpoints (single, list, calendar, today, upcoming, rest-of-week), GET rounds, GET matchdays, GET seasons
- **Service File**: `services/match_settings_service.py` contains `resolve_match_settings()` (single match) and `resolve_match_settings_batch()` (list of matches)

### Play-Up Tracking System (Added January 2026)
- **CalledFromTeam Field**: `RosterPlayer` now has optional `calledFromTeam` with teamId, teamName, teamAlias
  - Set during roster creation when a player is called up from a lower team
  - Must be set alongside `called: true` for play-up tracking to work
- **PlayUpTrackings Population**: When a match finishes:
  - StatsService extracts play-up occurrences from roster data
  - Updates player's `playUpTrackings` array with fromTeamId, toTeamId, and occurrence details
  - Duplicate matchId entries are prevented
  - Validates fromTeamId and toTeamId presence before storing
- **PlayUpTracking Structure**: 
  - `tournamentAlias`, `seasonAlias`: Context for the play-up
  - `fromTeamId`: Player's original/lower team
  - `toTeamId`: Team player played up to
  - `occurrences`: List of `{ matchId, matchStartDate, counted }`
- **5 Called Matches Rule**: After 5 called matches (hardcoded), player gets auto-assigned to higher team with `source: CALLED`

## External Dependencies

### Database
- **MongoDB Atlas**: Cloud-hosted MongoDB cluster with TLS encryption via certifi

### Third-Party Services
- **Cloudinary**: Cloud image hosting (CLDY_CLOUD_NAME, CLDY_API_KEY, CLDY_API_SECRET)
- **ISHD API**: External player license verification system
- **SMTP Email**: Gmail SMTP for transactional emails

### Environment Configuration
Required environment variables:
- `DB_URL` / `DB_URL_PROD` / `DB_URL_DEMO`: MongoDB connection strings (dev / prod / demo)
- `DB_NAME`: Database name (bishl_dev / bishl / bishl_demo)
- `SECRET_KEY`: JWT signing key
- `BE_API_URL`: Backend API base URL for internal calls
- `MAIL_*`: SMTP configuration for email service
- `CLDY_*`: Cloudinary credentials

### Python Dependencies
Key packages: FastAPI, Motor, Pydantic (v2), pydantic-settings, PyJWT, Argon2-cffi, Passlib, FastAPI-Mail, Cloudinary, Loguru, httpx, aiohttp, isodate, python-multipart

### Render.com Deployment (Updated February 2026)
- `.python-version` file pins Python to 3.12.0 (Render defaults to Python 3.14 which is incompatible with some dependencies)
- Start command: `uvicorn main:app --host 0.0.0.0 --port 5000`
- All dependencies must be listed in `requirements.txt` with upper-bound version constraints to prevent breaking changes