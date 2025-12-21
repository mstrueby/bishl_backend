# BISHL Backend API

## Overview

This is a FastAPI-based backend application for BISHL (Berlin Inline Skater Hockey League), a sports league management system. The application manages tournaments, matches, teams, players, referees, and related sports league operations. It provides a comprehensive REST API for a frontend application to consume.

The system handles:
- Tournament and season management with rounds and matchdays
- Match scheduling, scoring, penalties, and roster management
- Club and team administration
- Player registration and license management (integrating with ISHD - German inline hockey federation)
- Referee assignments and scheduling
- User authentication and role-based access control
- Document and post/content management

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Backend Framework
- **FastAPI** for the REST API framework with automatic OpenAPI documentation
- **Uvicorn** as the ASGI server
- Async-first design using Python's asyncio capabilities

### Database
- **MongoDB** as the primary database
- **Motor** (async MongoDB driver) for production API operations
- **PyMongo** (sync driver) for utility/migration scripts
- Uses a document-based schema with nested subdocuments (tournaments contain seasons, which contain rounds, which contain matchdays)
- Environment-based database selection (dev vs prod via `DB_URL` and `DB_NAME` environment variables)

### Authentication & Security
- **JWT-based authentication** with configurable token expiration
- Password hashing using **Argon2** (primary) with **bcrypt** fallback for legacy passwords
- Role-based access control with roles: ADMIN, REF_ADMIN, AUTHOR, PUBLISHER, REFEREE, DOC_ADMIN, CLUB_ADMIN, LEAGUE_ADMIN, PLAYER_ADMIN
- Custom `AuthHandler` class managing token encoding/decoding and password verification

### API Structure
The API follows RESTful conventions with nested resource routing:
- `/tournaments/{alias}/seasons/{alias}/rounds/{alias}/matchdays/{alias}`
- `/clubs/{alias}/teams/{alias}`
- `/matches/{id}/home|away/roster|scores|penalties`

Main routers:
- `tournaments`, `seasons`, `rounds`, `matchdays` - League structure
- `matches`, `roster`, `scores`, `penalties` - Match operations
- `clubs`, `teams`, `players` - Organization management
- `users`, `assignments` - User and referee management
- `posts`, `documents` - Content management
- `venues`, `configs`, `messages` - Supporting features

### File Storage
- **Cloudinary** for image and document storage (logos, player photos, venue images, documents)
- Automatic image transformations (resizing, cropping, format conversion)

### Email Service
- **FastAPI-Mail** for sending emails
- Configurable SMTP settings via environment variables

### Data Models
- Pydantic models for request/response validation
- Custom `PyObjectId` class for MongoDB ObjectId handling
- Base models (`*Base`), database models (`*DB`), and update models (`*Update`) pattern

### Utility Scripts
Located in the root directory, these are standalone scripts for:
- Data import from CSV files (`import_*.py`)
- Database backups (`backup_db.py`)
- Data migrations and updates (`update_*.py`, `migrate_*.py`)
- Player merging and data cleanup

## External Dependencies

### Database
- **MongoDB Atlas** - Cloud-hosted MongoDB instance
- Connection via `DB_URL` environment variable with TLS/SSL (using certifi)
- Separate dev (`bishl_dev`) and production (`bishl`) databases

### Third-Party APIs
- **ISHD API** - German Inline Hockey Federation for player license data synchronization
- **Genderize.io** - API for determining gender from first names (used in player data)

### Cloud Services
- **Cloudinary** - Image and document CDN/storage
  - Environment variables: `CLDY_CLOUD_NAME`, `CLDY_API_KEY`, `CLDY_API_SECRET`
  - Folders: `logos/`, `logos/teams/`, `players/`, `posts/`, `venues/`, `docs/`

### Email
- SMTP email service configured via:
  - `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`
  - `MAIL_FROM`, `MAIL_FROM_NAME`
  - TLS/SSL configuration options

### Key Environment Variables Required
- `DB_URL`, `DB_NAME` - MongoDB connection
- `SECRET_KEY` - JWT signing key
- `API_TIMEOUT_MIN` - Token expiration
- `BE_API_URL` - Backend API base URL
- `CURRENT_SEASON` - Active season identifier
- Cloudinary credentials
- Mail server credentials
- Admin user credentials for scripts (`ADMIN_USER`, `ADMIN_PASSWORD`, `SYS_ADMIN_EMAIL`, `SYS_ADMIN_PASSWORD`)