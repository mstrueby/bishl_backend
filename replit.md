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

### Roster Management (Updated January 2026)
- **Consolidated Roster Object**: All roster-related data is now nested at `match.team.roster` instead of flat fields
- **Roster Structure**: `{ players: [], status, published, eligibilityTimestamp, eligibilityValidator, coach, staff }`
- **Status Workflow**: DRAFT → SUBMITTED → APPROVED (with INVALID for reset)
- **Atomic Updates**: Single PUT endpoint updates all roster fields atomically via `RosterUpdate` model
- **Backward Compatibility**: Legacy flat structure (roster as list + rosterStatus field) is auto-converted on read
- **Migration Script**: `scripts/migrate_roster_structure.py` transforms existing documents to new structure

## External Dependencies

### Database
- **MongoDB Atlas**: Cloud-hosted MongoDB cluster with TLS encryption via certifi

### Third-Party Services
- **Cloudinary**: Cloud image hosting (CLDY_CLOUD_NAME, CLDY_API_KEY, CLDY_API_SECRET)
- **ISHD API**: External player license verification system
- **SMTP Email**: Gmail SMTP for transactional emails

### Environment Configuration
Required environment variables:
- `DB_URL` / `DB_URL_PROD`: MongoDB connection strings
- `DB_NAME`: Database name (bishl_dev / bishl)
- `SECRET_KEY`: JWT signing key
- `BE_API_URL`: Backend API base URL for internal calls
- `MAIL_*`: SMTP configuration for email service
- `CLDY_*`: Cloudinary credentials

### Python Dependencies
Key packages: FastAPI, Motor, Pydantic, PyJWT, Argon2-cffi, Passlib, FastAPI-Mail, Cloudinary, Loguru