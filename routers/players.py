import base64
import json
import os
import urllib.parse
from datetime import datetime
from typing import Any

import aiohttp
import cloudinary
import cloudinary.uploader
from bson.objectid import ObjectId
from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from pydantic import HttpUrl

from authentication import AuthHandler, TokenPayload
from config import settings
from exceptions import (
    AuthorizationException,
    DatabaseOperationException,
    ExternalServiceException,
    ResourceNotFoundException,
    ValidationException,
)
from logging_config import logger
from models.players import (
    AssignedTeamsInput,
    LicenseInvalidReasonCode,
    PlayerBase,
    PlayerDB,
    PlayerStats,
    PlayerUpdate,
    PositionEnum,
    SexEnum,
    SourceEnum,
)
from models.responses import LicenceStats, PaginatedResponse, StandardResponse
from services.pagination import PaginationHelper
from services.performance_monitor import monitor_query
from services.player_assignment_service import PlayerAssignmentService
from services.stats_service import StatsService
from utils import DEBUG_LEVEL, configure_cloudinary, my_jsonable_encoder

router = APIRouter()
auth = AuthHandler()
configure_cloudinary()


# Helper function to get current user with roles, assumes AuthHandler is set up
def get_current_user_with_roles(required_roles: list[str]):
    async def role_checker(token_payload: TokenPayload = Depends(auth.auth_wrapper)):
        if not any(role in token_payload.roles for role in required_roles):
            raise AuthorizationException(
                message=f"Required role(s) not met. Need one of: {', '.join(required_roles)}",
                details={"user_roles": token_payload.roles},
            )
        return token_payload.sub  # Return the user subject/id

    return role_checker


# upload file
async def handle_image_upload(image: UploadFile, playerId) -> str:
    if image:
        result = cloudinary.uploader.upload(
            image.file,
            folder="players",
            public_id=playerId,
            overwrite=True,
            resource_type="image",
            format="jpg",  # Save as JPEG
            transformation=[{"width": 300, "height": 300, "crop": "thumb", "gravity": "face"}],
        )
        logger.info(f"Player image uploaded to Cloudinary: {result['public_id']}")
        return str(result["secure_url"])
    raise ValidationException(field="image", message="No image file provided for upload")


async def delete_from_cloudinary(image_url: str):
    if image_url:
        try:
            public_id = image_url.rsplit("/", 1)[-1].split(".")[0]
            result = cloudinary.uploader.destroy(f"players/{public_id}")
            logger.info(f"Document deleted from Cloudinary: players/{public_id}")
            logger.debug(f"Cloudinary deletion result: {result}")
            return result
        except Exception as e:
            raise ExternalServiceException(
                service_name="Cloudinary",
                message="Failed to delete image",
                details={"public_id": f"players/{public_id}", "error": str(e)},
            ) from e


# BOOTSTRAP PLAYER LICENCE CLASSIFICATION (heuristic classification)
# ----------------------
@router.post(
    "/bootstrap_classification",
    response_description="Bootstrap player license assignment based on passNo heuristics",
    include_in_schema=False,
)
async def bootstrap_classification(
    request: Request,
    reset: bool = Query(False, description="Reset licenseType/status before classification"),
    batch_size: int = Query(1000, description="Batch size for processing"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
):
    """
    Bootstrap license type classification for all players.

    - Classifies licenseType based on passNo suffixes (F=DEVELOPMENT, A=SECONDARY, L=LOAN)
    - Applies "single license" heuristic for PRIMARY
    - Sets initial status=VALID for classified licenses

    Args:
        reset: If True, reset licenseType/status/invalidReasonCodes before classification
        batch_size: Number of players to process in each batch

    Only accessible by admins.
    """
    mongodb = request.app.state.mongodb
    if "ADMIN" not in token_payload.roles:
        raise AuthorizationException(
            message="Admin role required for license assignment bootstrap",
            details={"user_roles": token_payload.roles},
        )

    assignment_service = PlayerAssignmentService(mongodb)
    modified_ids = await assignment_service.bootstrap_classification_for_all_players(
        reset=reset, batch_size=batch_size
    )

    # Get classification statistics
    stats = await assignment_service.get_classification_stats()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "message": "License classification bootstrap complete",
            "reset": reset,
            "modifiedPlayers": len(modified_ids),
            "modifiedPlayerIds": modified_ids[:100],  # Only return first 100 IDs
            "stats": stats,
        },
    )


# BOOTSTRAP PLAYER VALIDATION (WKO/BISHL rules)
# ----------------------
@router.post(
    "/bootstrap_validation",
    response_description="Bootstrap player license validation based on WKO/BISHL rules",
    include_in_schema=False,
)
async def bootstrap_validation(
    request: Request,
    reset: bool = Query(False, description="Reset status/invalidReasonCodes before validation"),
    batch_size: int = Query(1000, description="Batch size for processing"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
):
    """
    Bootstrap license validation for all players according to WKO/BISHL rules.

    - Validates PRIMARY consistency
    - Validates LOAN consistency
    - Validates age group compliance
    - Validates OVERAGE rules
    - Validates WKO participation limits
    - Ensures no license has status=UNKNOWN after validation

    Args:
        reset: If True, reset status/invalidReasonCodes before validation
        batch_size: Number of players to process in each batch

    Only accessible by admins.
    """
    mongodb = request.app.state.mongodb
    if "ADMIN" not in token_payload.roles:
        raise AuthorizationException(
            message="Admin role required for license validation bootstrap",
            details={"user_roles": token_payload.roles},
        )

    assignment_service = PlayerAssignmentService(mongodb)
    modified_ids = await assignment_service.bootstrap_validation_for_all_players(
        reset=reset, batch_size=batch_size
    )

    # Get validation statistics
    stats = await assignment_service.get_validation_stats()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "message": "License validation bootstrap complete",
            "reset": reset,
            "modifiedPlayers": len(modified_ids),
            "modifiedPlayerIds": modified_ids[:100],  # Only return first 100 IDs
            "stats": stats,
        },
    )


# BOOTSTRAP ALL (orchestrator for both services)
# ----------------------
@router.post(
    "/bootstrap_all",
    response_description="Bootstrap both assignment and validation for all players",
    include_in_schema=False,
)
async def bootstrap_all(
    request: Request,
    reset_assignment: bool = Query(False, description="Reset licenseType/status before assignment"),
    reset_validation: bool = Query(
        False, description="Reset status/invalidReasonCodes before validation"
    ),
    batch_size: int = Query(1000, description="Batch size for processing"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
):
    """
    Orchestrator endpoint to run both assignment and validation bootstrap in sequence.

    First runs PlayerAssignmentService.bootstrap_all_players,
    then runs LicenseValidationService.bootstrap_all_players.

    After completion, guarantees:
    - Every license has status=VALID or INVALID (never UNKNOWN)
    - Invalid licenses have at least one invalidReasonCode

    Args:
        reset_assignment: Reset licenseType/status before assignment classification
        reset_validation: Reset status/invalidReasonCodes before validation
        batch_size: Number of players to process in each batch

    Only accessible by admins.
    """
    mongodb = request.app.state.mongodb
    if "ADMIN" not in token_payload.roles:
        raise AuthorizationException(
            message="Admin role required for full license bootstrap",
            details={"user_roles": token_payload.roles},
        )

    assignment_service = PlayerAssignmentService(mongodb)

    # Run full orchestration (classification + validation)
    result = await assignment_service.bootstrap_all_players(
        reset_classification=reset_assignment,
        reset_validation=reset_validation,
        batch_size=batch_size,
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "message": "Full license bootstrap complete",
            "assignmentModifiedPlayers": result["classification_modified_count"],
            "validationModifiedPlayers": result["validation_modified_count"],
            "resetFlags": {
                "assignment": reset_assignment,
                "validation": reset_validation,
            },
            "stats": result["stats"],
        },
    )


# Helper function to search players
@monitor_query("get_paginated_players")
async def get_paginated_players(
    mongodb,
    q,
    page,
    club_alias=None,
    team_alias=None,
    sortby="firstName",
    get_all=False,
    active=None,
):
    RESULTS_PER_PAGE = 0 if get_all else settings.RESULTS_PER_PAGE
    skip = 0 if get_all else (page - 1) * RESULTS_PER_PAGE
    sort_field = {
        "firstName": "firstName",
        "lastName": "lastName",
        "birthdate": "birthdate",
        "displayFirstName": "displayFirstName",
        "displayLastName": "displayLastName",
    }.get(sortby, "firstName")

    # Configure German collation for proper sorting of umlauts
    collation = {
        "locale": "de",
        "strength": 1,  # Base characters and diacritics are considered primary differences
    }

    query: dict[str, Any] = {}

    if club_alias or team_alias or q or active is not None:
        query = {"$and": []}
        if club_alias:
            query["$and"].append({"assignedTeams.clubAlias": club_alias})
            if team_alias:
                query["$and"].append(
                    {
                        "assignedTeams": {
                            "$elemMatch": {"clubAlias": club_alias, "teams.teamAlias": team_alias}
                        }
                    }
                )
        if q:
            query["$and"].append(
                {
                    "$or": [
                        {"firstName": {"$regex": f".*{q}.*", "$options": "i"}},
                        {"lastName": {"$regex": f".*{q}.*", "$options": "i"}},
                        {"displayFirstName": {"$regex": f".*{q}.*", "$options": "i"}},
                        {"displayLastName": {"$regex": f".*{q}.*", "$options": "i"}},
                        {"assignedTeams.teams.passNo": {"$regex": f".*{q}.*", "$options": "i"}},
                    ]
                }
            )
        if active is not None and team_alias:
            # Use $elemMatch to ensure we're filtering the right team when team_alias is specified
            if active:
                # If we're looking for active=true, field must exist and be true for the correct team
                query["$and"].append(
                    {
                        "assignedTeams": {
                            "$elemMatch": {
                                "clubAlias": club_alias,
                                "teams": {"$elemMatch": {"teamAlias": team_alias, "active": True}},
                            }
                        }
                    }
                )
            else:
                # If we're looking for active=false for a specific team
                query["$and"].append(
                    {
                        "assignedTeams": {
                            "$elemMatch": {
                                "clubAlias": club_alias,
                                "teams": {
                                    "$elemMatch": {
                                        "teamAlias": team_alias,
                                        "$or": [{"active": False}, {"active": {"$exists": False}}],
                                    }
                                },
                            }
                        }
                    }
                )
        elif active is not None:
            # If no team_alias specified, use the original logic across all teams
            if active:
                # If we're looking for active=true, field must exist and be true
                query["$and"].append({"assignedTeams.teams.active": True})
            else:
                # If we're looking for active=false, either field doesn't exist or is false
                query["$and"].append(
                    {
                        "$or": [
                            {"assignedTeams.teams.active": False},
                            {"assignedTeams.teams.active": {"$exists": False}},
                        ]
                    }
                )
        if DEBUG_LEVEL > 10:
            print("query", query)

    total = await mongodb["players"].count_documents(query)
    players = (
        await mongodb["players"]
        .find(query)
        .collation(collation)
        .sort(sort_field, 1)
        .skip(skip)
        .limit(RESULTS_PER_PAGE)
        .to_list(None)
    )
    return {
        "total": total,
        "page": page,
        "results": [PlayerDB(**raw_player) for raw_player in players],
    }


# Helper function to create assignedTeams dict
async def build_assigned_teams_dict(assignedTeams, source, request):
    mongodb = request.app.state.mongodb
    # Deserialize the JSON string to Python objects
    assigned_teams_list = []
    try:
        assigned_teams_list = json.loads(assignedTeams)
    except json.JSONDecodeError as e:
        raise ValidationException(
            field="assignedTeams",
            message="Invalid JSON format for team assignments",
            details={"error": str(e)},
        ) from e

    print(f"assigned_teams_list: {assigned_teams_list}")
    # Validate and convert to the proper Pydantic models
    assigned_teams_objs = [AssignedTeamsInput(**team_dict) for team_dict in assigned_teams_list]

    assigned_teams_dict = []
    print("assignment_team_objs:", assigned_teams_objs)
    for club_to_assign in assigned_teams_objs:
        club_exists = await mongodb["clubs"].find_one({"_id": club_to_assign.clubId})
        if not club_exists:
            raise ResourceNotFoundException(resource_type="Club", resource_id=club_to_assign.clubId)
        teams = []
        for team_to_assign in club_to_assign.teams:
            print("team_to_assign:", club_exists["name"], "/", team_to_assign)
            team = next(
                (team for team in club_exists["teams"] if team["_id"] == team_to_assign.teamId),
                None,
            )
            if not team:
                raise ResourceNotFoundException(
                    resource_type="Team",
                    resource_id=team_to_assign.teamId,
                    details={"club_id": club_to_assign.clubId, "club_name": club_exists["name"]},
                )
            else:
                teams.append(
                    {
                        "teamId": team["_id"],
                        "teamName": team["name"],
                        "teamAlias": team["alias"],
                        "teamAgeGroup": team["ageGroup"],
                        "teamIshdId": team["ishdId"],
                        "passNo": team_to_assign.passNo,
                        "jerseyNo": team_to_assign.jerseyNo,
                        "active": team_to_assign.active,
                        "source": team_to_assign.source,
                        "licenseType": (
                            team_to_assign.licenseType
                            if hasattr(team_to_assign, "licenseType")
                            else "PRIMARY"
                        ),
                        "modifyDate": team_to_assign.modifyDate,
                    }
                )
        assigned_teams_dict.append(
            {
                "clubId": club_to_assign.clubId,
                "clubName": club_exists["name"],
                "clubAlias": club_exists["alias"],
                "clubIshdId": club_exists["ishdId"],
                "teams": teams,
            }
        )
    return assigned_teams_dict


# PLAYER LICENCE ENDPOINTS
# ----------------------
@router.get(
    "/licences/stats",
    response_model=StandardResponse[LicenceStats],
    response_description="Get license statistics overview",
)
async def get_licence_stats(request: Request):
    """
    Get license statistics including valid/invalid counts and reason breakdown.
    """
    mongodb = request.app.state.mongodb

    # Aggregate counts of valid and invalid player licenses
    # Note: A player is "invalid" if they have at least one team assignment with status=INVALID
    pipeline = [
        {"$project": {"assignedTeams": 1}},
        {"$unwind": "$assignedTeams"},
        {"$unwind": "$assignedTeams.teams"},
        {
            "$facet": {
                "player_counts": [
                    {
                        "$group": {
                            "_id": "$_id",
                            "is_invalid": {
                                "$max": {"$eq": ["$assignedTeams.teams.status", "INVALID"]}
                            },
                            "is_valid": {"$max": {"$eq": ["$assignedTeams.teams.status", "VALID"]}},
                        }
                    },
                    {
                        "$group": {
                            "_id": None,
                            "invalid_players": {"$sum": {"$cond": ["$is_invalid", 1, 0]}},
                            "valid_players": {"$sum": {"$cond": ["$is_valid", 1, 0]}},
                        }
                    },
                ],
                "reason_breakdown": [
                    {"$match": {"assignedTeams.teams.status": "INVALID"}},
                    {"$unwind": "$assignedTeams.teams.invalidReasonCodes"},
                    {
                        "$group": {
                            "_id": "$assignedTeams.teams.invalidReasonCodes",
                            "count": {"$sum": 1},
                        }
                    },
                ],
            }
        },
    ]

    cursor = mongodb["players"].aggregate(pipeline)
    result_list = await cursor.to_list(length=1)

    if not result_list:
        return StandardResponse(
            data=LicenceStats(valid_players=0, invalid_players=0, invalid_reason_breakdown={}),
            message="No player data available",
        )

    result = result_list[0]
    counts = (
        result["player_counts"][0]
        if result["player_counts"]
        else {"valid_players": 0, "invalid_players": 0}
    )
    reasons = {item["_id"]: item["count"] for item in result["reason_breakdown"]}

    stats = LicenceStats(
        valid_players=counts.get("valid_players", 0),
        invalid_players=counts.get("invalid_players", 0),
        invalid_reason_breakdown=reasons,
    )

    return StandardResponse(data=stats, message="Licence statistics retrieved successfully")


@router.get(
    "/licences/invalid/{reason_code}",
    response_model=PaginatedResponse[PlayerDB],
    response_description="Get players with invalid licenses for a specific reason",
)
async def get_players_with_invalid_licences(
    reason_code: LicenseInvalidReasonCode,
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(settings.RESULTS_PER_PAGE, ge=1, le=100),
):
    """
    Get a paginated list of players who have an invalid license with the specified reason code.
    """
    mongodb = request.app.state.mongodb

    # Query for players having at least one team assignment with the specified invalid reason code
    query = {
        "assignedTeams.teams": {
            "$elemMatch": {"status": "INVALID", "invalidReasonCodes": reason_code}
        }
    }

    items, total_count = await PaginationHelper.paginate_query(
        collection=mongodb["players"],
        query=query,
        page=page,
        page_size=page_size,
        sort=[("lastName", 1), ("firstName", 1)],
    )

    # Convert to PlayerDB models
    players = [PlayerDB(**item) for item in items]

    response_dict = PaginationHelper.create_response(
        items=players,
        page=page,
        page_size=page_size,
        total_count=total_count,
        message=f"Players with invalid license reason '{reason_code}' retrieved successfully",
    )

    return PaginatedResponse(**response_dict)


@router.get("/{id}/possible_teams", response_model=StandardResponse[list[dict]])
async def get_possible_teams(
    id: str,
    request: Request,
    club_id: str = Query(None),
    token_payload: TokenPayload = Depends(auth.auth_wrapper)
):
    """
    Get possible teams for a player based on WKO rules and current assignments.
    """
    mongodb = request.app.state.mongodb
    service = PlayerAssignmentService(mongodb)

    # Auth check
    if "CLUB_ADMIN" in token_payload.roles:
        target_club_id = token_payload.clubId
        if not target_club_id:
            raise AuthorizationException("Club ID required for CLUB_ADMIN")
        if club_id and club_id != target_club_id:
            raise AuthorizationException("Can only access own club teams")
    elif "PLAYER_ADMIN" in token_payload.roles or "ADMIN" in token_payload.roles:
        if not club_id:
            raise AuthorizationException("Club ID required for PLAYER_ADMIN or ADMIN")
        else:
            target_club_id = club_id
    else:
        raise AuthorizationException("Unauthorized access to possible teams")

    teams = await service.get_possible_teams_for_player(id, target_club_id)

    if not teams and not await mongodb["players"].find_one({"_id": id}):
         raise ResourceNotFoundException(resource_type="Player", resource_id=id)

    return StandardResponse(data=teams, message="Possible teams retrieved successfully")


# PROCESS ISHD DATA
# ----------------------
# NOTE: ISHD sync logic has been migrated to PlayerAssignmentService.process_ishd_sync()
# This endpoint now delegates to the service for better separation of concerns.

@router.get(
    "/process_ishd_data",
    response_description="Process ISHD player data to BISHL-Application",
    include_in_schema=False,
)
async def process_ishd_data(
    request: Request,
    mode: str | None = None,
    run: int = 1,
    # token_payload: TokenPayload = Depends(auth.auth_wrapper)
):
    """
    Process ISHD player data synchronization.

    Delegates to PlayerAssignmentService.process_ishd_sync() which handles:
    - Fetching player data from ISHD API
    - Comparing with existing database players
    - Adding/updating/removing player assignments
    - Applying license classification and validation
    - Logging all operations

    Args:
        mode: Sync mode - "live" (default), "test" (use JSON files), "dry" (simulate only)
        run: Run number for test mode (determines which JSON files to use)
    """
    mongodb = request.app.state.mongodb
    # if "ADMIN" not in token_payload.roles:
    #     raise AuthorizationException("Admin role required for ISHD data processing")

    # Delegate to service
    assignment_service = PlayerAssignmentService(mongodb)
    result = await assignment_service.process_ishd_sync(mode=mode or "live", run=run)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "message": "ISHD data processed successfully",
            "logs": result.get("logs", []),
            "stats": result.get("stats", {}),
        },
    )


# VERIFY ISHD DATA
# ----------------------
@router.get(
    "/verify_ishd_data",
    response_description="Verify player assignments against ISHD data",
    include_in_schema=False,
)
async def verify_ishd_data(
    request: Request,
    mode: str | None = None,
    # token_payload: TokenPayload = Depends(auth.auth_wrapper)
):
    mongodb = request.app.state.mongodb
    # if "ADMIN" not in token_payload.roles:
    #    raise AuthorizationException("Admin role required for ISHD verification")

    ISHD_API_URL = os.environ.get("ISHD_API_URL")
    ISHD_API_USER = os.environ.get("ISHD_API_USER")
    ISHD_API_PASS = os.environ.get("ISHD_API_PASS")

    verification_results: dict[str, list[Any]] = {
        "missing_in_ishd": [],
        "missing_in_db": [],
        "team_mismatches": [],
        "club_mismatches": [],
    }

    # Get all active clubs with ISHD teams
    ishd_teams = []
    async for club in mongodb["clubs"].aggregate(
        [{"$match": {"active": True, "teams.ishdId": {"$ne": None}, "teams": {"$ne": []}}}]
    ):
        for team in club["teams"]:
            if team.get("ishdId"):
                ishd_teams.append(
                    {
                        "club_id": club["_id"],
                        "club_name": club["name"],
                        "club_alias": club["alias"],
                        "club_ishd_id": club["ishdId"],
                        "team_id": team["_id"],
                        "team_name": team["name"],
                        "team_alias": team["alias"],
                        "team_ishd_id": team["ishdId"],
                    }
                )

    headers = {
        "Authorization": f"Basic {base64.b64encode(f'{ISHD_API_USER}:{ISHD_API_PASS}'.encode()).decode('utf-8')}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    # Get all players from database
    db_players = {}
    async for player in mongodb["players"].find({}):
        key = f"{player['firstName']}_{player['lastName']}_{datetime.strftime(player['birthdate'], '%Y-%m-%d')}"
        db_players[key] = {"player": player, "assignments": []}
        for club in player.get("assignedTeams", []):
            for team in club.get("teams", []):
                db_players[key]["assignments"].append(
                    {
                        "clubId": club["clubId"],
                        "clubName": club["clubName"],
                        "teamId": team["teamId"],
                        "teamName": team["teamName"],
                    }
                )

    # Create SSL context with certificate verification
    import ssl

    ssl_context = ssl.create_default_context()
    timeout = aiohttp.ClientTimeout(total=60)
    connector = aiohttp.TCPConnector(ssl=ssl_context)

    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        ishd_players: dict[str, Any] = {}

        for team_info in ishd_teams:
            club_ishd_id_str = urllib.parse.quote(str(team_info["club_ishd_id"]))
            team_id_str = urllib.parse.quote(str(team_info["team_ishd_id"]))
            api_url = f"{ISHD_API_URL}/clubs/{club_ishd_id_str}/teams/{team_id_str}.json"

            if mode == "test":
                test_file = f"ishd_test1_{club_ishd_id_str}_{team_info['team_alias']}.json"
                if os.path.exists(test_file):
                    with open(test_file) as file:
                        data = json.load(file)
                else:
                    continue
            else:
                async with session.get(api_url, headers=headers) as response:
                    if response.status != 200:
                        try:
                            error_detail = await response.json()
                        except json.JSONDecodeError:
                            error_detail = await response.text()
                        raise ExternalServiceException(
                            service_name="ISHD_API",
                            message=f"Failed to verify team data (status {response.status})",
                            details={
                                "url": api_url,
                                "status_code": response.status,
                                "error_detail": error_detail,
                            },
                        )
                    data = await response.json()

            for player in data["players"]:
                key = f"{player['first_name']}_{player['last_name']}_{player['date_of_birth']}"
                if key not in ishd_players:
                    ishd_players[key] = []
                ishd_players[key].append(
                    {
                        "clubId": team_info["club_id"],
                        "clubName": team_info["club_name"],
                        "teamId": team_info["team_id"],
                        "teamName": team_info["team_name"],
                    }
                )

        # Compare players
        for key, ishd_data in ishd_players.items():
            if key not in db_players:
                # Player exists in ISHD but not in DB
                player_name = key.split("_")
                # Group assignments by club
                club_assignments = {}
                for assignment in ishd_data:
                    club_id = assignment["clubId"]
                    if club_id not in club_assignments:
                        club_assignments[club_id] = {
                            "clubId": club_id,
                            "clubName": assignment["clubName"],
                            "teams": [],
                        }
                    club_assignments[club_id]["teams"].append(
                        {"teamId": assignment["teamId"], "teamName": assignment["teamName"]}
                    )

                verification_results["missing_in_db"].append(
                    {
                        "firstName": player_name[0],
                        "lastName": player_name[1],
                        "birthdate": player_name[2],
                        "ishd_assignments": list(club_assignments.values()),
                    }
                )
            else:
                db_data = db_players[key]
                # Create lookup dictionaries for efficient comparison
                db_assignments_by_club = {}
                for assignment in db_data["assignments"]:
                    club_id = assignment["clubId"]
                    if club_id not in db_assignments_by_club:
                        db_assignments_by_club[club_id] = {
                            "clubName": assignment["clubName"],
                            "teams": set(),
                        }
                    db_assignments_by_club[club_id]["teams"].add(assignment["teamId"])

                ishd_assignments_by_club = {}
                for assignment in ishd_data:
                    club_id = assignment["clubId"]
                    if club_id not in ishd_assignments_by_club:
                        ishd_assignments_by_club[club_id] = {
                            "clubName": assignment["clubName"],
                            "teams": set(),
                        }
                    ishd_assignments_by_club[club_id]["teams"].add(assignment["teamId"])

                # Compare assignments
                for club_id, ishd_club_data in ishd_assignments_by_club.items():
                    if club_id not in db_assignments_by_club:
                        # Club assignment missing in DB
                        verification_results["club_mismatches"].append(
                            {
                                "player": {
                                    "firstName": db_data["player"]["firstName"],
                                    "lastName": db_data["player"]["lastName"],
                                    "birthdate": datetime.strftime(
                                        db_data["player"]["birthdate"], "%Y-%m-%d"
                                    ),
                                },
                                "ishd_assignment": {
                                    "clubId": club_id,
                                    "clubName": ishd_club_data["clubName"],
                                    "teams": [{"teamId": t} for t in ishd_club_data["teams"]],
                                },
                                "db_assignments": db_data["assignments"],
                            }
                        )
                    else:
                        # Compare team assignments within club
                        db_club_data = db_assignments_by_club[club_id]
                        team_differences = ishd_club_data["teams"] - db_club_data["teams"]
                        if team_differences:
                            # Teams missing in DB for this club
                            for team_id in team_differences:
                                team_data = next(
                                    (t for t in ishd_data if t["teamId"] == team_id), None
                                )
                                if team_data:
                                    verification_results["team_mismatches"].append(
                                        {
                                            "player": {
                                                "firstName": db_data["player"]["firstName"],
                                                "lastName": db_data["player"]["lastName"],
                                                "birthdate": datetime.strftime(
                                                    db_data["player"]["birthdate"], "%Y-%m-%d"
                                                ),
                                            },
                                            "ishd_team": {
                                                "clubId": club_id,
                                                "clubName": ishd_club_data["clubName"],
                                                "teamId": team_id,
                                                "teamName": team_data["teamName"],
                                            },
                                            "db_assignments": [
                                                a
                                                for a in db_data["assignments"]
                                                if a["clubId"] == club_id
                                            ],
                                        }
                                    )

        # Check for players in DB but not in ISHD
        for key, db_data in db_players.items():
            if key not in ishd_players:
                # Group assignments by club for better readability
                club_assignments = {}
                for assignment in db_data["assignments"]:
                    club_id = assignment["clubId"]
                    if club_id not in club_assignments:
                        club_assignments[club_id] = {
                            "clubId": club_id,
                            "clubName": assignment["clubName"],
                            "teams": [],
                        }
                    club_assignments[club_id]["teams"].append(
                        {"teamId": assignment["teamId"], "teamName": assignment["teamName"]}
                    )

                verification_results["missing_in_ishd"].append(
                    {
                        "player": {
                            "firstName": db_data["player"]["firstName"],
                            "lastName": db_data["player"]["lastName"],
                            "birthdate": datetime.strftime(
                                db_data["player"]["birthdate"], "%Y-%m-%d"
                            ),
                        },
                        "db_assignments": list(club_assignments.values()),
                    }
                )

    return JSONResponse(
        status_code=status.HTTP_200_OK, content=jsonable_encoder(verification_results)
    )


@router.post("/{id}/revalidate", response_model=StandardResponse[PlayerDB])
async def revalidate_player(
    id: str,
    request: Request,
    resetClassification: bool = Query(False, description="Reset classification before running"),
    resetValidation: bool = Query(False, description="Reset validation before running"),
    current_user: dict = Depends(get_current_user_with_roles(["ADMIN", "CLUB_ADMIN", "PLAYER_ADMIN"])),
) -> JSONResponse:
    """
    Re-run classification and validation for a single player.
    Only accessible by ADMIN, CLUB_ADMIN, or PLAYER_ADMIN.
    """
    mongodb = request.app.state.mongodb

    # Load existing player
    player_data = await mongodb["players"].find_one({"_id": id})
    if not player_data:
        raise ResourceNotFoundException(resource_type="Player", resource_id=id)

    assignment_service = PlayerAssignmentService(mongodb)

    try:
        # Classification step
        class_modified = await assignment_service._update_player_classification_in_db(
            id, reset=resetClassification
        )

        # Validation step
        val_modified = await assignment_service._update_player_validation_in_db(
            id, reset=resetValidation
        )

        # Reload updated player
        updated_player_data = await mongodb["players"].find_one({"_id": id})
        if not updated_player_data:
             raise ResourceNotFoundException(resource_type="Player", resource_id=id)
        
        updated_player = PlayerDB(**updated_player_data)

        # Build message
        if class_modified or val_modified:
            message = "Player license classification and validation complete, changes applied"
        else:
            message = "Player license classification and validation complete, no changes needed"

        logger.info(
            f"Revalidation for player {id}: {updated_player.firstName} {updated_player.lastName} - "
            f"class_modified: {class_modified}, val_modified: {val_modified}"
        )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=jsonable_encoder(
                StandardResponse[PlayerDB](
                    success=True,
                    data=updated_player,
                    message=message,
                )
            ),
        )

    except Exception as e:
        logger.error(f"Error during player revalidation: {str(e)}")
        if isinstance(e, (ResourceNotFoundException, AuthorizationException)):
            raise e
        raise DatabaseOperationException(
            operation="revalidate",
            collection="players",
            details={"player_id": id, "error": str(e)},
        ) from e


# Add POST endpoint for license assignment classification
@router.post("/{id}/classify-licenses", response_model=StandardResponse[PlayerDB])
async def classify_player_licenses(
    id: str,
    request: Request,
    reset: bool = Query(False, description="Reset licenseType/status before classification"),
    current_user: dict = Depends(get_current_user_with_roles(["ADMIN"])),
) -> JSONResponse:
    """
    Classify license types for a single player based on passNo heuristics.
    Only accessible by admins.

    This endpoint:
    - Classifies licenseType based on passNo suffixes (F=DEVELOPMENT, A=SECONDARY, L=LOAN)
    - Applies "single license" heuristic for PRIMARY
    - Sets initial status=VALID for classified licenses

    Args:
        reset: If True, reset licenseType/status/invalidReasonCodes before classification

    Returns the updated player with classification applied.
    """
    mongodb = request.app.state.mongodb

    # Get player
    player_data = await mongodb["players"].find_one({"_id": id})
    if not player_data:
        raise ResourceNotFoundException(resource_type="Player", resource_id=id)

    # Run classification
    assignment_service = PlayerAssignmentService(mongodb)
    was_modified = await assignment_service._update_player_classification_in_db(id, reset=reset)

    # Get updated player
    updated_player_data = await mongodb["players"].find_one({"_id": id})
    updated_player = PlayerDB(**updated_player_data)

    message = "Player license classification complete"
    if was_modified:
        message += " (changes applied)"
    else:
        message += " (no changes needed)"

    logger.info(
        f"License classification for player {id}: {updated_player.firstName} {updated_player.lastName} - modified: {was_modified}"
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=jsonable_encoder(
            StandardResponse(
                success=True,
                data=updated_player.model_dump(by_alias=True),
                message=message,
            )
        ),
    )


# Add POST endpoint for license validation
@router.post("/{id}/validate-licenses", response_model=StandardResponse[PlayerDB])
async def validate_player_licenses(
    id: str,
    request: Request,
    reset: bool = Query(False, description="Reset status/invalidReasonCodes before validation"),
    current_user: dict = Depends(get_current_user_with_roles(["ADMIN"])),
) -> JSONResponse:
    """
    Validate all licenses for a player according to WKO/BISHL rules.
    Only accessible by admins.

    This endpoint:
    - Checks PRIMARY consistency (only one PRIMARY allowed)
    - Checks LOAN consistency (max one LOAN)
    - Validates age group compliance
    - Validates OVERAGE rules
    - Validates WKO participation limits
    - Checks club consistency for SECONDARY/OVERAGE
    - Handles ISHD vs BISHL import conflicts

    Args:
        reset: If True, reset status/invalidReasonCodes before validation

    Returns the updated player with validation applied.
    """
    mongodb = request.app.state.mongodb

    # Get player
    player_data = await mongodb["players"].find_one({"_id": id})
    if not player_data:
        raise ResourceNotFoundException(resource_type="Player", resource_id=id)

    # Run validation
    assignment_service = PlayerAssignmentService(mongodb)
    was_modified = await assignment_service._update_player_validation_in_db(id, reset=reset)

    # Get updated player
    updated_player_data = await mongodb["players"].find_one({"_id": id})
    updated_player = PlayerDB(**updated_player_data)

    message = "Player license validation complete"
    if was_modified:
        message += " (changes applied)"
    else:
        message += " (no changes needed)"

    logger.info(
        f"License validation for player {id}: {updated_player.firstName} {updated_player.lastName} - modified: {was_modified}"
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=jsonable_encoder(
            StandardResponse(
                success=True,
                data=updated_player.model_dump(by_alias=True),
                message=message,
            )
        ),
    )


@router.get("/{id}/stats", response_model=list[PlayerStats])
async def get_player_stats(id: str, request: Request) -> list[PlayerStats]:
    mongodb = request.app.state.mongodb
    player = await mongodb["players"].find_one({"_id": id})
    if not player:
        raise ResourceNotFoundException(resource_type="Player", resource_id=id)

    player_obj = PlayerDB(**player)
    stats_service = StatsService(mongodb)
    player_stats = await stats_service.get_player_stats(player_obj)
    return player_stats


# GET ALL PLAYERS FOR ONE CLUB
# --------
@router.get(
    "/clubs/{club_alias}",
    response_description="Get all players for a club",
    response_model=PaginatedResponse[PlayerDB],
)
async def get_players_for_club(
    request: Request,
    club_alias: str,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    q: str | None = Query(None, description="Search by name"),
    sortby: str = "firstName",
    all: bool = False,
    active: bool | None = None,
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    if not any(role in token_payload.roles for role in ["ADMIN", "CLUB_ADMIN", "LEAGUE_ADMIN"]):
        raise AuthorizationException(
            message="Admin, Club Admin, or League Admin role required",
            details={"user_roles": token_payload.roles},
        )
    # get club
    club = await mongodb["clubs"].find_one({"alias": club_alias})
    if not club:
        raise ResourceNotFoundException(resource_type="Club", resource_id=club_alias)
    result = await get_paginated_players(mongodb, q, page, club_alias, None, sortby, all, active)

    # Use PaginationHelper to create the response
    paginated_result = PaginationHelper.create_response(
        items=[player.model_dump(by_alias=True) for player in result["results"]],
        page=result["page"],
        page_size=settings.RESULTS_PER_PAGE if not all else result["total"],
        total_count=result["total"],
        message=f"Retrieved {len(result['results'])} players for club {club_alias}",
    )
    return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(paginated_result))


# GET ALL PLAYERS FOR ONE CLUB/TEAM
# --------
@router.get(
    "/clubs/{club_alias}/teams/{team_alias}",
    response_description="Get all players for a team",
    response_model=PaginatedResponse[PlayerDB],
)
async def get_players_for_team(
    request: Request,
    club_alias: str,
    team_alias: str,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    q: str | None = Query(None, description="Search by name"),
    sortby: str = "firstName",
    all: bool = False,
    active: bool | None = None,
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    logger.debug(f"User roles: {token_payload.roles}")
    if not any(role in token_payload.roles for role in ["ADMIN", "CLUB_ADMIN", "LEAGUE_ADMIN"]):
        raise AuthorizationException(
            message="Admin, Club Admin, or League Admin role required",
            details={"user_roles": token_payload.roles},
        )
    # get club
    club = await mongodb["clubs"].find_one({"alias": club_alias})
    if not club:
        raise ResourceNotFoundException(resource_type="Club", resource_id=club_alias)
    # get team
    team = None
    for t in club.get("teams", []):
        if t["alias"] == team_alias:
            team = t
            break
    if not team:
        raise ResourceNotFoundException(
            resource_type="Team", resource_id=team_alias, details={"club_alias": club_alias}
        )
    result = await get_paginated_players(
        mongodb, q, page, club_alias, team_alias, sortby, all, active
    )

    # Use PaginationHelper to create the response
    paginated_result = PaginationHelper.create_response(
        items=[player.model_dump(by_alias=True) for player in result["results"]],
        page=result["page"],
        page_size=settings.RESULTS_PER_PAGE if not all else result["total"],
        total_count=result["total"],
        message=f"Retrieved {len(result['results'])} players for team {team_alias} in club {club_alias}",
    )
    return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(paginated_result))


# GET ALL PLAYERS
# -------------------
@router.get("", response_description="Get all players", response_model=PaginatedResponse[PlayerDB])
async def get_players(
    request: Request,
    search: str | None = Query(None, description="Search by name"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    sortby: str = "firstName",
    all: bool = False,
    active: bool | None = None,
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    if not any(role in token_payload.roles for role in ["ADMIN", "LEAGUE_ADMIN"]):
        raise AuthorizationException(
            message="Admin or League Admin role required",
            details={"user_roles": token_payload.roles},
        )

    # Use PaginationHelper to create the query
    search_query: dict[str, Any] = {}
    if search:
        search_query["$or"] = [
            {"firstName": {"$regex": search, "$options": "i"}},
            {"lastName": {"$regex": search, "$options": "i"}},
            {"displayFirstName": {"$regex": search, "$options": "i"}},
            {"displayLastName": {"$regex": search, "$options": "i"}},
            {"assignedTeams.teams.passNo": {"$regex": search, "$options": "i"}},
        ]
    if active is not None:
        # This part needs to be adapted if 'active' is a field within 'assignedTeams.teams'
        # For now, assuming 'active' is a top-level field for filtering players
        search_query["active"] = (
            active  # This line might need adjustment based on how 'active' is used
        )

    # Add club and team filtering if necessary (e.g., if passed as query parameters)
    # if club_alias:
    #     search_query["assignedTeams.clubAlias"] = club_alias
    # if team_alias:
    #     search_query["assignedTeams.teams.teamAlias"] = team_alias

    # Configure German collation for proper sorting of umlauts
    collation = {
        "locale": "de",
        "strength": 1,
    }

    # Determine actual page_size to use
    actual_page_size = 0 if all else page_size
    skip = 0 if all else (page - 1) * page_size

    # Get total count
    total_count = await mongodb["players"].count_documents(search_query)

    # Get paginated items with collation
    cursor = mongodb["players"].find(search_query).collation(collation).sort(sortby, 1).skip(skip)

    if actual_page_size > 0:
        cursor = cursor.limit(actual_page_size)

    items = await cursor.to_list(length=None)

    # Create the paginated response
    paginated_result = PaginationHelper.create_response(
        items=[PlayerDB(**item).model_dump(by_alias=True) for item in items],
        page=page,
        page_size=page_size if not all else total_count,
        total_count=total_count,
        message=f"Retrieved {len(items)} players",
    )
    return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(paginated_result))


# GET ONE PLAYER
# --------------------
@router.get(
    "/{id}", response_description="Get a player by ID", response_model=StandardResponse[PlayerDB]
)
async def get_player(
    id: str, request: Request, token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    player = await mongodb["players"].find_one({"_id": id})
    if player is None:
        raise ResourceNotFoundException(resource_type="Player", resource_id=id)

    player_obj = PlayerDB(**player)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=jsonable_encoder(
            StandardResponse(
                success=True,
                data=player_obj.model_dump(by_alias=True),
                message="Player retrieved successfully",
            )
        ),
    )


# CREATE NEW PLAYER
# ----------------------
@router.post("", response_description="Add new player", response_model=StandardResponse[PlayerDB])
async def create_player(
    request: Request,
    firstName: str = Form(...),
    lastName: str = Form(...),
    birthdate: datetime = Form(...),
    displayFirstName: str = Form(...),
    displayLastName: str = Form(...),
    nationality: str = Form(None),
    position: PositionEnum = Form(default=PositionEnum.SKATER),
    assignedTeams: str = Form(None),  # JSON string
    suspensions: str = Form(None),  # JSON string
    playUpTrackings: str = Form(None),  # JSON string
    fullFaceReq: bool = Form(False),
    managedByISHD: bool = Form(False),
    source: SourceEnum = Form(default=SourceEnum.BISHL),
    sex: SexEnum = Form(default=SexEnum.MALE),
    legacyId: int = Form(None),
    image: UploadFile = File(None),
    imageVisible: bool = Form(False),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    if not any(role in token_payload.roles for role in ["ADMIN", "PLAYER_ADMIN"]):
        raise AuthorizationException(
            message="Admin or Player Admin role required",
            details={"user_roles": token_payload.roles},
        )

    player_exists = await mongodb["players"].find_one(
        {"firstName": firstName, "lastName": lastName, "birthdate": birthdate}
    )
    if player_exists:
        raise ValidationException(
            field="player",
            message=f"Player with name {firstName} {lastName} and birthdate {birthdate.strftime('%d.%m.%Y')} already exists",
            details={
                "firstName": firstName,
                "lastName": lastName,
                "birthdate": birthdate.strftime("%d.%m.%Y"),
            },
        )

    if assignedTeams:
        assigned_teams_dict = await build_assigned_teams_dict(assignedTeams, source, request)
    else:
        assigned_teams_dict = []

    # Parse suspensions if provided
    suspensions_list = []
    if suspensions:
        try:
            suspensions_list = json.loads(suspensions)
        except json.JSONDecodeError as e:
            raise ValidationException(
                field="suspensions",
                message="Invalid JSON format for suspensions",
                details={"error": str(e)},
            ) from e

    # Parse playUpTrackings if provided
    play_up_trackings_list = []
    if playUpTrackings:
        try:
            play_up_trackings_list = json.loads(playUpTrackings)
        except json.JSONDecodeError as e:
            raise ValidationException(
                field="playUpTrackings",
                message="Invalid JSON format for playUpTrackings",
                details={"error": str(e)},
            ) from e

    # Generate a new ID for the player
    player_id = str(ObjectId())

    player = PlayerBase(
        firstName=firstName,
        lastName=lastName,
        birthdate=birthdate,
        displayFirstName=displayFirstName,
        displayLastName=displayLastName,
        nationality=nationality,
        position=position,
        assignedTeams=assigned_teams_dict,
        suspensions=suspensions_list,
        playUpTrackings=play_up_trackings_list,
        fullFaceReq=fullFaceReq,
        managedByISHD=managedByISHD,
        source=SourceEnum[source],
        sex=sex if isinstance(sex, SexEnum) else SexEnum(sex),
        imageVisible=imageVisible,
        legacyId=legacyId,
    )
    player = my_jsonable_encoder(player)
    player["create_date"] = datetime.now().replace(microsecond=0)
    player["_id"] = player_id

    if image:
        player["imageUrl"] = await handle_image_upload(image, player_id)

    try:
        logger.info(
            f"Creating new player: {firstName} {lastName} ({birthdate.strftime('%Y-%m-%d')})"
        )
        await mongodb["players"].insert_one(player)
        created_player = await mongodb["players"].find_one({"_id": player_id})
        if created_player:
            logger.info(f"Player created successfully: {player_id}")
            return JSONResponse(
                status_code=status.HTTP_201_CREATED,
                content=jsonable_encoder(
                    StandardResponse(
                        success=True,
                        data=PlayerDB(**created_player).model_dump(by_alias=True),
                        message="Player created successfully",
                    )
                ),
            )
        else:
            raise DatabaseOperationException(
                operation="insert_one",
                collection="players",
                details={"player_id": player_id, "reason": "Player not found after insertion"},
            )
    except Exception as e:
        logger.error(f"Error creating player: {str(e)}")
        raise DatabaseOperationException(
            operation="insert_one", collection="players", details={"error": str(e)}
        ) from e


# UPDATE PLAYER
# ----------------------
@router.patch(
    "/{id}", response_description="Update player", response_model=StandardResponse[PlayerDB]
)
async def update_player(
    request: Request,
    id: str,
    firstName: str | None = Form(None),
    lastName: str | None = Form(None),
    birthdate: datetime | None = Form(None),
    displayFirstName: str | None = Form(None),
    displayLastName: str | None = Form(None),
    nationality: str | None = Form(None),
    position: PositionEnum | None = Form(None),
    assignedTeams: str | None = Form(None),
    suspensions: str | None = Form(None),
    playUpTrackings: str | None = Form(None),
    stats: str | None = Form(None),
    fullFaceReq: bool | None = Form(None),
    managedByISHD: bool | None = Form(None),
    source: SourceEnum | None = Form(None),
    sex: SexEnum | None = Form(None),
    image: UploadFile | None = File(None),
    imageUrl: str | None = Form(None),
    imageVisible: bool | None = Form(None),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
):
    mongodb = request.app.state.mongodb
    if not any(role in token_payload.roles for role in ["ADMIN", "CLUB_ADMIN", "PLAYER_ADMIN"]):
        raise AuthorizationException(
            message="Admin, Club Admin, or Player Admin role required",
            details={"user_roles": token_payload.roles},
        )
    existing_player = await mongodb["players"].find_one({"_id": id})
    if not existing_player:
        raise ResourceNotFoundException(resource_type="Player", resource_id=id)

    # Validate imageUrl as HttpUrl if it's a non-empty string
    validated_image_url: HttpUrl | None = None
    if imageUrl and imageUrl != "":
        try:
            validated_image_url = HttpUrl(imageUrl)
        except Exception as e:
            raise ValidationException(
                field="imageUrl",
                message="Invalid URL format",
                details={"provided_value": imageUrl, "error": str(e)},
            ) from e

    current_first_name = firstName or existing_player.get("firstName")
    current_last_name = lastName or existing_player.get("lastName")
    current_birthdate = birthdate or existing_player.get("birthdate")
    player_exists = await mongodb["players"].find_one(
        {
            "firstName": current_first_name,
            "lastName": current_last_name,
            "birthdate": current_birthdate,
            "_id": {"$ne": id},  # Checking for a different _id
        }
    )
    if player_exists:
        raise ValidationException(
            field="player",
            message=f"Player with name {current_first_name} {current_last_name} and birthdate {current_birthdate.strftime('%d.%m.%Y')} already exists",
            details={
                "firstName": current_first_name,
                "lastName": current_last_name,
                "birthdate": current_birthdate.strftime("%d.%m.%Y"),
            },
        )

    if assignedTeams:
        assigned_teams_dict = await build_assigned_teams_dict(assignedTeams, source, request)
    else:
        assigned_teams_dict = None

    # Parse suspensions if provided
    suspensions_list = None
    if suspensions:
        try:
            suspensions_list = json.loads(suspensions)
        except json.JSONDecodeError as e:
            raise ValidationException(
                field="suspensions",
                message="Invalid JSON format for suspensions",
                details={"error": str(e)},
            ) from e

    # Parse playUpTrackings if provided
    play_up_trackings_list = None
    if playUpTrackings:
        try:
            play_up_trackings_list = json.loads(playUpTrackings)
        except json.JSONDecodeError as e:
            raise ValidationException(
                field="playUpTrackings",
                message="Invalid JSON format for playUpTrackings",
                details={"error": str(e)},
            ) from e

    player_data = PlayerUpdate(
        firstName=firstName,
        lastName=lastName,
        birthdate=birthdate,
        displayFirstName=displayFirstName,
        displayLastName=displayLastName,
        nationality=nationality,
        position=position,
        assignedTeams=assigned_teams_dict,
        suspensions=suspensions_list,
        playUpTrackings=play_up_trackings_list,
        stats=json.loads(stats) if stats else None,
        fullFaceReq=fullFaceReq,
        managedByISHD=managedByISHD,
        imageVisible=imageVisible,
        source=source,
        sex=sex,
    ).model_dump(exclude_none=True)

    player_data.pop("id", None)

    # Debug: Log what was received for image handling
    logger.debug(f"Image upload handling - image file provided: {image is not None}")
    logger.debug(f"Image upload handling - imageUrl value: {repr(imageUrl)}")
    logger.debug(f"Image upload handling - existing imageUrl: {existing_player.get('imageUrl')}")

    # Handle image upload/deletion/keeping
    if image:
        # Case 1: New file uploaded - always replace/set image
        logger.debug("Image handling: Uploading new image file")
        if existing_player.get("imageUrl"):
            logger.debug(f"Image handling: Deleting existing image: {existing_player['imageUrl']}")
            await delete_from_cloudinary(existing_player["imageUrl"])
        player_data["imageUrl"] = await handle_image_upload(image, id)
        logger.debug(f"Image handling: New image uploaded: {player_data['imageUrl']}")
    elif imageUrl == "":
        # Case 2: Empty string means delete the image
        logger.debug("Image handling: Deleting image (empty string received)")
        if existing_player.get("imageUrl"):
            await delete_from_cloudinary(existing_player["imageUrl"])
            logger.debug(f"Image handling: Deleted existing image: {existing_player['imageUrl']}")
        player_data["imageUrl"] = None
    elif imageUrl is not None:
        # Case 3: imageUrl has a value (URL string) - keep/update URL
        logger.debug(f"Image handling: Setting imageUrl to provided value: {imageUrl}")
        # Use the validated URL if it's valid, otherwise keep the provided string (which might be invalid but was passed)
        player_data["imageUrl"] = validated_image_url or imageUrl
    else:
        # Case 4: imageUrl not in FormData - don't include in update (keep existing)
        logger.debug("Image handling: imageUrl not provided, removing from update data")
        player_data.pop("imageUrl", None)

    logger.debug(f"player_data: {player_data}")

    # exclude unchanged data
    player_to_update = {
        k: v
        for k, v in player_data.items()
        if (
            k == "birthdate"
            and v.strftime("%Y-%m-%d") != existing_player.get(k, None).strftime("%Y-%m-%d")
        )
        or (k != "birthdate" and v != existing_player.get(k, None))
    }

    logger.debug(f"player_to_update: {player_to_update}")
    if not player_to_update:
        logger.debug("No changes to update")
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=jsonable_encoder(
                StandardResponse(
                    success=True,
                    data=PlayerDB(**existing_player).model_dump(by_alias=True),
                    message="No changes detected",
                )
            ),
        )

    try:
        update_result = await mongodb["players"].update_one(
            {"_id": id}, {"$set": player_to_update}, upsert=False
        )
        if update_result.modified_count == 1:
            updated_player = await mongodb["players"].find_one({"_id": id})
            logger.info(f"Player updated successfully: {id}")
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=jsonable_encoder(
                    StandardResponse(
                        success=True,
                        data=PlayerDB(**updated_player).model_dump(by_alias=True),
                        message="Player updated successfully",
                    )
                ),
            )
        raise DatabaseOperationException(
            operation="update_one",
            collection="players",
            details={"player_id": id, "reason": "Update operation did not modify any documents"},
        )
    except Exception as e:
        logger.error(f"Error updating player {id}: {str(e)}")
        raise DatabaseOperationException(
            operation="update_one", collection="players", details={"player_id": id, "error": str(e)}
        ) from e


# DELETE PLAYER
# ----------------------
@router.delete(
    "/{id}",
    response_description="Delete a player by ID",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        204: {"description": "Player deleted successfully"},
        404: {"description": "Player not found"},
        403: {"description": "Not authorized"},
    },
)
async def delete_player(
    request: Request, id: str, token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> Response:
    mongodb = request.app.state.mongodb
    if "ADMIN" not in token_payload.roles:
        raise AuthorizationException(
            message="Admin role required", details={"user_roles": token_payload.roles}
        )
    existing_player = await mongodb["players"].find_one({"_id": id})
    if not existing_player:
        raise ResourceNotFoundException(resource_type="Player", resource_id=id)
    delete_result = await mongodb["players"].delete_one({"_id": id})
    if delete_result.deleted_count == 1:
        await delete_from_cloudinary(existing_player["imageUrl"])
        logger.info(f"Player deleted successfully: {id}")
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    raise ResourceNotFoundException(resource_type="Player", resource_id=id)
