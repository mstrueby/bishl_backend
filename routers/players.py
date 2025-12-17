import base64
import json
import os
import urllib.parse
from datetime import datetime
from typing import Any, List

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
    AssignedClubs,
    AssignedTeams,
    AssignedTeamsInput,
    IshdActionEnum,
    IshdLogBase,
    IshdLogClub,
    IshdLogPlayer,
    IshdLogTeam,
    PlayerBase,
    PlayerDB,
    PlayerStats,
    PlayerUpdate,
    PositionEnum,
    SexEnum,
    SourceEnum,
)
from models.responses import PaginatedResponse, StandardResponse
from services.pagination import PaginationHelper
from services.performance_monitor import monitor_query
from services.stats_service import StatsService
from services.license_validation_service import LicenseValidationService, LicenseValidationReport
from services.player_assignment_service import PlayerAssignmentService
from utils import DEBUG_LEVEL, configure_cloudinary, my_jsonable_encoder

router = APIRouter()
auth = AuthHandler()
configure_cloudinary()

# Helper function to get current user with roles, assumes AuthHandler is set up
def get_current_user_with_roles(required_roles: List[str]):
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


# RECLASSIFY ALL PLAYER LICENSES (one-time migration)
# ----------------------
@router.post(
    "/reclassify_licenses",
    response_description="Reclassify all player licenses based on passNo heuristics",
    include_in_schema=False,
)
async def reclassify_all_player_licenses(
    request: Request,
    batch_size: int = Query(1000, description="Batch size for processing"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
):
    """
    One-time migration endpoint to classify all existing player licenses
    based on passNo suffix heuristics and PRIMARY detection.
    
    This should be run once after deploying the license classification system.
    Only accessible by admins.
    """
    mongodb = request.app.state.mongodb
    if "ADMIN" not in token_payload.roles:
        raise AuthorizationException(
            message="Admin role required for license reclassification",
            details={"user_roles": token_payload.roles},
        )
    
    assignment_service = PlayerAssignmentService(mongodb)
    modified_ids = await assignment_service.bootstrap_all_players(batch_size=batch_size)
    
    # Get classification statistics
    stats = await assignment_service.get_classification_stats()
    
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "message": "License reclassification complete",
            "modifiedPlayers": len(modified_ids),
            "modifiedPlayerIds": modified_ids[:100],  # Only return first 100 IDs
            "stats": stats,
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
                        "licenseType": team_to_assign.licenseType if hasattr(team_to_assign, 'licenseType') else "PRIMARY",
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


# PROCESS ISHD DATA
# ----------------------
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
    mongodb = request.app.state.mongodb
    # if "ADMIN" not in token_payload.roles:
    #  raise AuthorizationException("Admin role required for ISHD data processing")

    log_lines = []
    # If mode is 'test', delete all documents in 'players'
    if mode == "test" and run == 1:
        await mongodb["players"].delete_many({})
        log_line = "Deleted all documents in players."
        logger.warning(log_line)
        log_lines.append(log_line)

    ISHD_API_URL = os.environ.get("ISHD_API_URL")
    ISHD_API_USER = os.environ.get("ISHD_API_USER")
    ISHD_API_PASS = os.environ.get("ISHD_API_PASS")

    class IshdTeams:

        def __init__(self, club_id, club_ishd_id, club_name, club_alias, teams):
            self.club_id = club_id
            self.club_ishd_id = club_ishd_id
            self.club_name = club_name
            self.club_alias = club_alias
            self.teams = teams

    ishd_teams = []
    create_date = datetime.now().replace(microsecond=0)

    async for club in mongodb["clubs"].aggregate(
        [
            {
                "$match": {
                    "active": True,
                    # "ishdId": 143,
                    # "teams.ishdId": {
                    #    "$ne": None
                    # },
                    "teams": {"$ne": []},
                }
            },
            {"$project": {"ishdId": 1, "_id": 1, "name": 1, "alias": 1, "teams": 1}},
            {"$sort": {"ishdId": 1}},
        ]
    ):
        ishd_teams.append(
            IshdTeams(club["_id"], club["ishdId"], club["name"], club["alias"], club["teams"])
        )

    # get exisiting players
    existing_players = []
    async for player in mongodb["players"].find(
        {},
        {
            "firstName": 1,
            "lastName": 1,
            "birthdate": 1,
            "assignedTeams": 1,
            "managedByISHD": 1,
        },
    ):
        existing_players.append(player)

    # api_urls = []
    base_url_str = str(ISHD_API_URL)

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
    """
  response:

  "players": [
    {
      "player_id": 34893,
      "last_name": "Apel",
      "first_name": "Chris Tim",
      "date_of_birth": "1995-05-03",
      "full_face_req": true,
      "license_number": "5754",
      "approved": true,
      "nationality": "deutsch",
      "last_modification": "2017-05-16 18:20:17"
    },

  """

    ishd_data = []
    # current_timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    # file_name = f'ishd_processing_{current_timestamp}.log'

    # Keep only the 10 most recent log files, delete older ones
    """
  log_files = sorted([
      f for f in os.listdir('.')
      if f.startswith('ishd_processing_') and f.endswith('.log')
  ])
  if len(log_files) > 10:
    for old_log in log_files[:-10]:
      try:
        os.remove(old_log)
        log_line = f"Deleted old log file: {old_log}"
        print(log_line)
        log_lines.append(log_line)
      except OSError as e:
        log_line = f"Error deleting file {old_log}: {e.strerror}"
        print(log_line)
        log_lines.append(log_line)
  """

    timeout = aiohttp.ClientTimeout(total=60)

    # Create SSL context with certificate verification
    import ssl

    ssl_context = ssl.create_default_context()
    # ssl_context.check_hostname = False  # Uncomment if hostname verification fails
    # ssl_context.verify_mode = ssl.CERT_NONE  # Uncomment to disable SSL verification entirely

    connector = aiohttp.TCPConnector(ssl=ssl_context, limit=10, limit_per_host=5)
    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        # loop through team API URLs
        # for api_url in api_urls:

        ishd_log_base = IshdLogBase(
            processDate=datetime.now().replace(microsecond=0),
            clubs=[],
        )

        for club in ishd_teams:
            # Skip clubs with no ISHD ID
            if club.club_ishd_id is None:
                log_line = f"Skipping club {club.club_name} (no ISHD ID)"
                print(log_line)
                log_lines.append(log_line)
                continue

            log_line = f"Processing club {club.club_name} (IshdId: {club.club_ishd_id})"
            print(log_line)
            log_lines.append(log_line)
            ishd_log_club = IshdLogClub(
                clubName=club.club_name,
                ishdId=club.club_ishd_id,
                teams=[],
            )

            for team in club.teams:
                if not team["ishdId"]:
                    continue
                club_ishd_id_str = urllib.parse.quote(str(club.club_ishd_id))
                team_id_str = urllib.parse.quote(str(team["ishdId"]))
                # if team_id_str != '1.%20Herren' and team_id_str != '2.%20Herren':
                #  break
                api_url = f"{base_url_str}/clubs/{club_ishd_id_str}/teams/{team_id_str}.json"
                ishd_log_team = IshdLogTeam(
                    teamIshdId=team["ishdId"],
                    url=api_url,
                    players=[],
                )

                # get data
                data = {}
                if mode == "test":
                    test_file = f"ishd_test{run}_{club_ishd_id_str}_{team['alias']}.json"
                    if os.path.exists(test_file):
                        log_line = (
                            f"Processing team {club.club_name} / {team['ishdId']} / {test_file}"
                        )
                        # print(log_line)
                        log_lines.append(log_line)
                        with open(test_file) as file:
                            data = json.load(file)
                            print("data", data)
                    else:
                        log_line = f"File {test_file} does not exist. Skipping..."
                        # print(log_line)
                        log_lines.append(log_line)
                else:
                    log_line = (
                        f"Processing team (URL): {club.club_name} / {team['ishdId']} / {api_url}"
                    )
                    print(log_line)
                    log_lines.append(log_line)

                    async with session.get(api_url, headers=headers) as response:
                        if response.status == 200:
                            data = await response.json()
                        elif response.status == 404:
                            log_line = f"API URL {api_url} returned a 404 status code."
                            print(log_line)
                            log_lines.append(log_line)
                        else:
                            # Catch other potential errors and raise HTTPException
                            try:
                                error_detail = await response.json()
                            except json.JSONDecodeError:
                                try:
                                    error_detail = await response.text()
                                except Exception:
                                    error_detail = "Unable to parse error response"

                            # Check for SSL-related errors
                            if response.status in [525, 526, 530]:
                                error_detail = f"SSL/TLS error - Status {response.status}. The server may have SSL certificate issues."

                            raise ExternalServiceException(
                                service_name="ISHD_API",
                                message=f"Failed to fetch team data (status {response.status})",
                                details={
                                    "url": api_url,
                                    "status_code": response.status,
                                    "error_detail": error_detail,
                                },
                            )
                if data:
                    # loop through players array
                    for player in data["players"]:
                        # check if player['date_of_birth'] is valid date
                        try:
                            birthdate = datetime.strptime(player["date_of_birth"], "%Y-%m-%d")
                        except ValueError:
                            log_line = (
                                f"ERROR: Invalid date format for player "
                                f"{player['first_name']} {player['last_name']} "
                                f"from club {club.club_name} and team {team['name']}"
                            )
                            print(log_line)
                            log_lines.append(log_line)
                            continue

                        # Check if player exists and has managedByISHD=false
                        existing_player_check = None
                        for existing_player in existing_players:
                            if (
                                existing_player["firstName"] == player["first_name"]
                                and existing_player["lastName"] == player["last_name"]
                                and datetime.strftime(existing_player["birthdate"], "%Y-%m-%d")
                                == player["date_of_birth"]
                            ):
                                existing_player_check = existing_player
                                break

                        if (
                            existing_player_check
                            and existing_player_check.get("managedByISHD", True) is False
                        ):
                            log_line = f"Skipping player (managedByISHD=false): {player['first_name']} {player['last_name']} {player['date_of_birth']}"
                            print(log_line)
                            log_lines.append(log_line)
                            continue
                        ishd_log_player = IshdLogPlayer(
                            firstName=player["first_name"],
                            lastName=player["last_name"],
                            birthdate=datetime.strptime(player["date_of_birth"], "%Y-%m-%d"),
                        )
                        # if player['first_name'] != "Leonid":
                        #  break
                        # build assignedTeams object
                        assigned_team = AssignedTeams(
                            teamId=team["_id"],
                            teamName=team["name"],
                            teamAlias=team["alias"],
                            teamAgeGroup=team["ageGroup"],
                            teamIshdId=team["ishdId"],
                            passNo=player["license_number"],
                            source=SourceEnum.ISHD,
                            modifyDate=datetime.strptime(
                                player["last_modification"], "%Y-%m-%d %H:%M:%S"
                            ),
                        )
                        assigned_club = AssignedClubs(
                            clubId=club.club_id,
                            clubName=club.club_name,
                            clubAlias=club.club_alias,
                            clubIshdId=club.club_ishd_id,
                            teams=[assigned_team],
                        )

                        # print("assigned_club", assigned_club)
                        # check if player already exists in existing_players array
                        player_exists = False
                        existing_player = None
                        for existing_player_loop in existing_players:
                            if (
                                existing_player_loop["firstName"] == player["first_name"]
                                and existing_player_loop["lastName"] == player["last_name"]
                                and datetime.strftime(existing_player_loop["birthdate"], "%Y-%m-%d")
                                == player["date_of_birth"]
                            ):
                                player_exists = True
                                existing_player = existing_player_loop
                                break

                        if player_exists and existing_player is not None:
                            # player already exists
                            # Check if team assignment exists for player
                            club_assignment_exists = False
                            if mode == "test":
                                print("player exists / existing_players", existing_players)
                            for club_assignment in existing_player.get("assignedTeams", []):
                                if mode == "test":
                                    print("club_assignment", club_assignment)
                                if club_assignment["clubName"] == club.club_name:
                                    if mode == "test":
                                        print(
                                            "club_assignment exists: club_name",
                                            club_assignment["clubName"],
                                        )
                                    club_assignment_exists = True
                                    # club already exists
                                    team_assignment_exists = False
                                    for team_assignment in club_assignment.get("teams", []):
                                        if team_assignment["teamId"] == team["_id"]:
                                            team_assignment_exists = True
                                            break
                                    if not team_assignment_exists:
                                        # team assignment does not exist
                                        # add team assignment to players existing club assignment
                                        club_assignment.get("teams").append(
                                            jsonable_encoder(assigned_team)
                                        )
                                        # update player with new team assignment
                                        existing_player["assignedTeams"] = [club_assignment] + [
                                            a
                                            for a in existing_player["assignedTeams"]
                                            if a != club_assignment
                                        ]
                                        if mode == "test":
                                            print("add team / existing_player", existing_player)
                                        
                                        # Apply license classification heuristics
                                        assignment_service = PlayerAssignmentService(mongodb)
                                        existing_player = await assignment_service.apply_heuristics_for_imported_player(existing_player)
                                        
                                        # update player in database
                                        result = await mongodb["players"].update_one(
                                            {"_id": existing_player["_id"]},
                                            {
                                                "$set": {
                                                    "assignedTeams": jsonable_encoder(
                                                        existing_player["assignedTeams"]
                                                    )
                                                }
                                            },
                                        )
                                        if result.modified_count:
                                            log_line = f"Updated team assignment for: {existing_player.get('firstName')} {existing_player.get('lastName')} {datetime.strftime(existing_player.get('birthdate'), '%Y-%m-%d')} -> {club.club_name} / {team['ishdId']}"
                                            print(log_line)
                                            log_lines.append(log_line)
                                            ishd_log_player.action = IshdActionEnum.ADD_TEAM
                                        else:
                                            raise DatabaseOperationException(
                                                operation="update_one",
                                                collection="players",
                                                details={
                                                    "player_id": existing_player["_id"],
                                                    "reason": "Failed to update team assignment",
                                                },
                                            )
                                    break
                            if not club_assignment_exists:
                                # club assignment does not exist
                                if mode == "test":
                                    print("club assignment does not exist / existing_players")
                                # add club assignment to player
                                existing_player["assignedTeams"].append(
                                    jsonable_encoder(assigned_club)
                                )
                                if mode == "test":
                                    print("add club / existing_player: ", existing_player)
                                
                                # Apply license classification heuristics
                                assignment_service = PlayerAssignmentService(mongodb)
                                existing_player = await assignment_service.apply_heuristics_for_imported_player(existing_player)
                                
                                # update player with new club assignment
                                result = await mongodb["players"].update_one(
                                    {"_id": existing_player["_id"]},
                                    {
                                        "$set": {
                                            "source": SourceEnum.ISHD,
                                            "assignedTeams": jsonable_encoder(
                                                existing_player["assignedTeams"]
                                            ),
                                        }
                                    },
                                )
                                if result.modified_count:
                                    log_line = f"New club assignment for: {existing_player.get('firstName')} {existing_player.get('lastName')} {datetime.strftime(existing_player.get('birthdate'), '%Y-%m-%d')} -> {club.club_name} / {team.get('ishdId')}"
                                    print(log_line)
                                    log_lines.append(log_line)
                                    ishd_log_player.action = IshdActionEnum.ADD_CLUB

                                else:
                                    raise DatabaseOperationException(
                                        operation="update_one",
                                        collection="players",
                                        details={
                                            "player_id": existing_player["_id"],
                                            "reason": "Failed to add club assignment",
                                        },
                                    )

                        else:
                            # NEW PLAYER
                            # FIRST: construct Player object w/o assignedTeams
                            new_player = PlayerBase(
                                firstName=player["first_name"],
                                lastName=player["last_name"],
                                birthdate=datetime.strptime(player["date_of_birth"], "%Y-%m-%d"),
                                displayFirstName=player["first_name"],
                                displayLastName=player["last_name"],
                                nationality=(
                                    player["nationality"] if "nationality" in player else None
                                ),
                                assignedTeams=[assigned_club],
                                fullFaceReq=(
                                    True if player.get("full_face_req") == "true" else False
                                ),
                                source=SourceEnum.ISHD,
                            )
                            new_player_dict = my_jsonable_encoder(new_player)
                            new_player_dict["birthdate"] = datetime.strptime(
                                player["date_of_birth"], "%Y-%m-%d"
                            )
                            new_player_dict["createDate"] = create_date

                            # Apply license classification heuristics
                            assignment_service = PlayerAssignmentService(mongodb)
                            new_player_dict = await assignment_service.apply_heuristics_for_imported_player(new_player_dict)

                            # add player to exisiting players array
                            existing_players.append(new_player_dict)

                            # insert player into database
                            result = await mongodb["players"].insert_one(new_player_dict)
                            if result.inserted_id:
                                birthdate = new_player_dict.get("birthdate")
                                birthdate_str = (
                                    birthdate.strftime("%Y-%m-%d")
                                    if isinstance(birthdate, datetime)
                                    else "Unknown"
                                )
                                log_line = f"Inserted player: {new_player_dict.get('firstName')} {new_player_dict.get('lastName')} {birthdate_str} -> {assigned_club.clubName} / {assigned_team.teamName}"
                                print(log_line)
                                log_lines.append(log_line)
                                if mode == "test":
                                    print("new player / existing_players", existing_players)
                                ishd_log_player.action = IshdActionEnum.ADD_PLAYER

                            else:
                                raise DatabaseOperationException(
                                    operation="insert_one",
                                    collection="players",
                                    details={
                                        "player_name": f"{new_player_dict.get('firstName')} {new_player_dict.get('lastName')}",
                                        "reason": "Insert operation did not return inserted_id",
                                    },
                                )

                        if ishd_log_player.action is not None:
                            ishd_log_team.players.append(ishd_log_player)

                    ishd_data.append(data)

                    # remove player of a team (still in team loop)
                    query = {
                        "assignedTeams": {
                            "$elemMatch": {
                                "clubAlias": club.club_alias,
                                "teams.teamAlias": team["alias"],
                            }
                        }
                    }
                    players = await mongodb["players"].find(query).to_list(length=None)
                    if mode == "test":
                        print("removing / players:", players)
                    if players:
                        for player in players:
                            ishd_log_player_remove = IshdLogPlayer(
                                firstName=player["firstName"],
                                lastName=player["lastName"],
                                birthdate=player["birthdate"],
                            )
                            if mode == "test":
                                print("remove player ?", player)
                            # remove player from team only if source is ISHD
                            team_source_is_ishd = False
                            for club_assignment in player.get("assignedTeams", []):
                                if club_assignment.get("clubAlias") == club.club_alias:
                                    for team_assignment in club_assignment.get("teams", []):
                                        if (
                                            team_assignment.get("teamAlias") == team["alias"]
                                            and team_assignment.get("source") == "ISHD"
                                        ):
                                            team_source_is_ishd = True
                                            break

                            # Skip players with managedByISHD=false
                            if player.get("managedByISHD", True) is False:
                                log_line = f"Skipping player (managedByISHD=false): {player.get('firstName')} {player.get('lastName')} {datetime.strftime(player.get('birthdate'), '%Y-%m-%d')}"
                                print(log_line)
                                log_lines.append(log_line)
                                continue

                            if team_source_is_ishd and not any(
                                p["first_name"] == player["firstName"]
                                and p["last_name"] == player["lastName"]
                                and p["date_of_birth"]
                                == datetime.strftime(player["birthdate"], "%Y-%m-%d")
                                for p in data["players"]
                            ):
                                query = {
                                    "$and": [
                                        {"_id": player["_id"]},
                                        {
                                            "assignedTeams": {
                                                "$elemMatch": {
                                                    "clubAlias": club.club_alias,
                                                    "teams": {
                                                        "$elemMatch": {"teamAlias": team["alias"]}
                                                    },
                                                }
                                            }
                                        },
                                    ]
                                }
                                # print("query", query)
                                result = await mongodb["players"].update_one(
                                    query,
                                    {
                                        "$pull": {
                                            "assignedTeams.$.teams": {"teamAlias": team["alias"]}
                                        }
                                    },
                                )
                                if result.modified_count:
                                    # Update existing_players array to remove team assignment
                                    for existing_player in existing_players:
                                        if existing_player["_id"] == player["_id"]:
                                            for club_assignment in existing_player.get(
                                                "assignedTeams", []
                                            ):
                                                if club_assignment["clubAlias"] == club.club_alias:
                                                    club_assignment["teams"] = [
                                                        t
                                                        for t in club_assignment["teams"]
                                                        if t["teamAlias"] != team["alias"]
                                                    ]
                                                    break

                                    log_line = f"Removed player from team: {player.get('firstName')} {player.get('lastName')} {datetime.strftime(player.get('birthdate'), '%Y-%m-%d')} -> {club.club_name} / {team.get('ishdId')}"
                                    print(log_line)
                                    log_lines.append(log_line)
                                    ishd_log_player_remove.action = IshdActionEnum.DEL_TEAM

                                    # After removing team assignment, if the teams array is empty, remove the club assignment
                                    result = await mongodb["players"].update_one(
                                        {
                                            "_id": player["_id"],
                                            "assignedTeams.clubIshdId": club.club_ishd_id,
                                        },
                                        {"$pull": {"assignedTeams": {"teams": {"$size": 0}}}},
                                    )
                                    if result.modified_count:
                                        # Update existing_players array to remove club assignment
                                        for existing_player in existing_players:
                                            if existing_player["_id"] == player["_id"]:
                                                existing_player["assignedTeams"] = [
                                                    a
                                                    for a in existing_player.get(
                                                        "assignedTeams", []
                                                    )
                                                    if a["clubIshdId"] != club.club_ishd_id
                                                ]
                                                break

                                        log_line = f"Removed club assignment for player: {player.get('firstName')} {player.get('lastName')} {datetime.strftime(player.get('birthdate'), '%Y-%m-%d')} -> {club.club_name}"
                                        print(log_line)
                                        log_lines.append(log_line)
                                        ishd_log_player_remove.action = IshdActionEnum.DEL_CLUB
                                    else:
                                        print("--- No club assignment removed")

                                else:
                                    raise DatabaseOperationException(
                                        operation="update_one",
                                        collection="players",
                                        details={
                                            "player_id": player["_id"],
                                            "reason": "Failed to remove player from team",
                                        },
                                    )
                            else:
                                if mode == "test":
                                    print("player exists in team - do not remove")

                            if ishd_log_player_remove.action is not None:
                                # print("--- ishd_log_player", ishd_log_player_remove)
                                ishd_log_team.players.append(ishd_log_player_remove)

                # print(f"--- ishd_log_team", ishd_log_team)
                if ishd_log_team:
                    ishd_log_club.teams.append(ishd_log_team)

            # print(f"--- ishd_log_club", ishd_log_club)
            if ishd_log_club:
                ishd_log_base.clubs.append(ishd_log_club)

    await session.close()

    # with open(file_name, 'w') as logfile:
    #  logfile.write('\n'.join(log_lines))

    ishd_log_base_enc = my_jsonable_encoder(ishd_log_base)
    # ishd_log_base_enc['processDate'] = create_date
    result = await mongodb["ishdLogs"].insert_one(ishd_log_base_enc)
    if result.inserted_id:
        log_line = "Inserted ISHD log into ishdLogs collection."
        print(log_line)
        log_lines.append(log_line)
    else:
        raise DatabaseOperationException(
            operation="insert_one",
            collection="ishdLogs",
            details={"reason": "Insert operation did not return inserted_id"},
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "message": "ISHD data processed successfully",
            "logs": log_lines,
            # "data": ishd_data
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


# Add POST endpoint for license validation
@router.post("/{id}/validate-licenses", response_model=LicenseValidationReport)
async def validate_player_licenses(
    id: str,
    request: Request,
    current_user: dict = Depends(get_current_user_with_roles(["ADMIN"]))
) -> LicenseValidationReport:
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

    Returns a report with validation results and persists changes.
    """
    mongodb = request.app.state.mongodb

    # Get player
    player_data = await mongodb["players"].find_one({"_id": id})
    if not player_data:
        raise ResourceNotFoundException(resource_type="Player", resource_id=id)

    player = PlayerDB(**player_data)

    # Run validation
    license_service = LicenseValidationService(mongodb)
    report = await license_service.revalidate_player_licenses(player)

    return report


@router.get("/{id}/stats", response_model=List[PlayerStats])
async def get_player_stats(id: str, request: Request) -> List[PlayerStats]:
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