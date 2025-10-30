#!/usr/bin/env python
import traceback
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

import certifi
from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from motor.motor_asyncio import AsyncIOMotorClient

from config import settings

# Import custom exceptions and logging
from exceptions import BISHLException
from logging_config import logger
from routers.assignments import router as assignments_router
from routers.clubs import router as clubs_router
from routers.configs import router as configs_router
from routers.documents import router as documents_router
from routers.matchdays import router as matchdays_router
from routers.matches import router as matches_router
from routers.messages import router as messages_router
from routers.penalties import router as penalties_router
from routers.players import router as players_router
from routers.posts import router as posts_router

# import uvicorn
from routers.root import router as root_router
from routers.roster import router as roster_router
from routers.rounds import router as rounds_router
from routers.scores import router as scores_router
from routers.seasons import router as seasons_router
from routers.teams import router as teams_router
from routers.tournaments import router as tournaments_router
from routers.users import router as users_router
from routers.venues import router as venues_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting BISHL API server...")
    logger.info(f"Connecting to MongoDB: {settings.DB_NAME}")
    app.state.client = AsyncIOMotorClient(settings.DB_URL, tlsCAFile=certifi.where())
    app.state.mongodb_client = app.state.client  # Keep backward compatibility
    app.state.mongodb = app.state.client[settings.DB_NAME]
    logger.info("MongoDB connection established")
    
    yield
    
    # Shutdown
    logger.info("Shutting down BISHL API server...")
    app.state.client.close()
    logger.info("MongoDB connection closed")


app = FastAPI(
    lifespan=lifespan,
    title="BISHL API",
    version="1.0.0",
    description="""
## Berlin Inline Skater Hockey League API

This API provides comprehensive management for ice and street hockey leagues in Belgium.

### Key Features

* **Match Management** - Create, update, and track matches with real-time scoring
* **Player Statistics** - Track player performance, cards, and goals
* **Tournament Organization** - Manage tournaments, seasons, rounds, and matchdays
* **Referee Assignment** - Assign and manage referee schedules
* **Club & Team Management** - Organize clubs, teams, and rosters
* **Authentication** - Secure JWT-based authentication with refresh tokens

### Authentication

Most endpoints require authentication. Include the access token in the Authorization header:

```
Authorization: Bearer <your_access_token>
```

Access tokens expire after 15 minutes. Use the `/users/refresh` endpoint to get a new token.

### Pagination

List endpoints support pagination with query parameters:
- `page` (default: 1) - Page number
- `page_size` (default: 10-20, max: 100) - Items per page

### Error Handling

All errors return a standardized format with correlation IDs for debugging:

```json
{
  "error": {
    "message": "Resource not found",
    "status_code": 404,
    "correlation_id": "uuid",
    "timestamp": "ISO-8601",
    "path": "/api/endpoint"
  }
}
```
    """,
    version_info={"version": "1.0.0", "build": "production", "last_updated": "2025-01-22"},
    contact={"name": "BISHL Development Team", "url": "https://bishl.be", "email": "tech@bishl.be"},
    license_info={
        "name": "Proprietary",
    },
    openapi_tags=[
        {
            "name": "matches",
            "description": "Operations for managing matches, including creation, updates, scoring, and statistics",
        },
        {"name": "players", "description": "Player management, statistics, and roster operations"},
        {
            "name": "tournaments",
            "description": "Tournament, season, round, and matchday organization",
        },
        {"name": "clubs", "description": "Club and team management"},
        {
            "name": "users",
            "description": "User authentication, registration, and referee management",
        },
        {"name": "assignments", "description": "Referee assignment and scheduling"},
        {"name": "posts", "description": "News posts and announcements"},
        {"name": "documents", "description": "Document management and downloads"},
        {"name": "venues", "description": "Venue and location management"},
    ],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception Handlers
@app.exception_handler(BISHLException)
async def bishl_exception_handler(request: Request, exc: BISHLException):
    """Handle all BISHL custom exceptions"""
    correlation_id = str(uuid.uuid4())

    error_response = {
        "error": {
            "message": exc.message,
            "status_code": exc.status_code,
            "correlation_id": correlation_id,
            "timestamp": datetime.utcnow().isoformat(),
            "path": request.url.path,
            "details": exc.details,
        }
    }

    # Log the error with correlation ID
    logger.error(
        f"[{correlation_id}] {exc.__class__.__name__}: {exc.message}",
        extra={
            "correlation_id": correlation_id,
            "status_code": exc.status_code,
            "path": request.url.path,
            "details": exc.details,
        },
    )

    return JSONResponse(status_code=exc.status_code, content=error_response)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle FastAPI HTTPExceptions with consistent format"""
    correlation_id = str(uuid.uuid4())

    error_response = {
        "error": {
            "message": exc.detail,
            "status_code": exc.status_code,
            "correlation_id": correlation_id,
            "timestamp": datetime.utcnow().isoformat(),
            "path": request.url.path,
        }
    }

    logger.error(
        f"[{correlation_id}] HTTPException: {exc.detail}",
        extra={
            "correlation_id": correlation_id,
            "status_code": exc.status_code,
            "path": request.url.path,
        },
    )

    return JSONResponse(status_code=exc.status_code, content=error_response)


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Catch-all handler for unexpected exceptions"""
    correlation_id = str(uuid.uuid4())

    # Log full traceback for unexpected errors
    logger.error(
        f"[{correlation_id}] Unhandled exception: {str(exc)}",
        extra={
            "correlation_id": correlation_id,
            "path": request.url.path,
            "traceback": traceback.format_exc(),
        },
    )

    error_response = {
        "error": {
            "message": "An unexpected error occurred",
            "status_code": 500,
            "correlation_id": correlation_id,
            "timestamp": datetime.utcnow().isoformat(),
            "path": request.url.path,
        }
    }

    return JSONResponse(status_code=500, content=error_response)


app.include_router(root_router, prefix="", tags=["root"])
app.include_router(configs_router, prefix="/configs", tags=["configs"])

app.include_router(users_router, prefix="/users", tags=["users"])
app.include_router(messages_router, prefix="/messages", tags=["messages"])

app.include_router(venues_router, prefix="/venues", tags=["venues"])
app.include_router(clubs_router, prefix="/clubs", tags=["clubs"])
app.include_router(teams_router, prefix="/clubs/{club_alias}/teams", tags=["teams"])
app.include_router(tournaments_router, prefix="/tournaments", tags=["tournaments"])

app.include_router(
    seasons_router, prefix="/tournaments/{tournament_alias}/seasons", tags=["seasons"]
)
app.include_router(
    rounds_router,
    prefix="/tournaments/{tournament_alias}/seasons/{season_alias}/rounds",
    tags=["rounds"],
)
app.include_router(
    matchdays_router,
    prefix="/tournaments/{tournament_alias}/seasons/{season_alias}/rounds/{round_alias}/matchdays",
    tags=["matchdays"],
)

app.include_router(matches_router, prefix="/matches", tags=["matches"])
app.include_router(assignments_router, prefix="/assignments", tags=["assignments"])
app.include_router(roster_router, prefix="/matches/{match_id}/{team_flag}/roster", tags=["roster"])
app.include_router(scores_router, prefix="/matches/{match_id}/{team_flag}/scores", tags=["scores"])
app.include_router(
    penalties_router, prefix="/matches/{match_id}/{team_flag}/penalties", tags=["penalties"]
)
app.include_router(posts_router, prefix="/posts", tags=["posts"])
app.include_router(documents_router, prefix="/documents", tags=["documents"])
app.include_router(players_router, prefix="/players", tags=["players"])

# if __name__ == "__main__":
#    uvicorn.run("main:app", reload=True)
