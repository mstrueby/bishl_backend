from cloudinary.utils import string
from fastapi import APIRouter, HTTPException, Form, Request, Body, Depends, status, File
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
import json
from typing import List, Optional, Dict
from bson.objectid import ObjectId
from fastapi import UploadFile
from pydantic import HttpUrl, BaseModel
from pydantic.types import OptionalInt
from utils import DEBUG_LEVEL, configure_cloudinary, my_jsonable_encoder
from models.players import PlayerBase, PlayerDB, PlayerUpdate, AssignedClubs, AssignedTeams, AssignedTeamsInput, PositionEnum, SourceEnum, IshdActionEnum, IshdLogBase, IshdLogPlayer, IshdLogTeam, IshdLogClub
from authentication import AuthHandler, TokenPayload
from datetime import datetime, timezone
import os
import urllib.parse
import aiohttp
import base64
import cloudinary
import cloudinary.uploader

router = APIRouter()
auth = AuthHandler()
configure_cloudinary()


# upload file
async def handle_image_upload(image: UploadFile, playerId) -> str:
    if image:
        result = cloudinary.uploader.upload(
            image.file,
            folder="players",
            public_id=playerId,
            overwrite=True,
            resource_type="image",
            format='jpg',  # Save as JPEG
            transformation=[{
                'width': 300,
                'height': 300,
                'crop': 'thumb',
                'gravity': 'face'
            }])
        print(f"Player image uploaded to Cloudinary: {result['public_id']}")
        return result["secure_url"]
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                        detail="No image uploaded.")


async def delete_from_cloudinary(image_url: str):
    if image_url:
        try:
            public_id = image_url.rsplit('/', 1)[-1].split('.')[0]
            result = cloudinary.uploader.destroy(f"players/{public_id}")
            print("Document deleted from Cloudinary:", f"players/{public_id}")
            print("Result:", result)
            return result
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


# Helper function to search players
async def get_paginated_players(mongodb,
                                q,
                                page,
                                club_alias=None,
                                team_alias=None,
                                sortby="firstName",
                                get_all=False,
                                active=None):
    RESULTS_PER_PAGE = 0 if get_all else int(os.environ['RESULTS_PER_PAGE'])
    skip = 0 if get_all else (page - 1) * RESULTS_PER_PAGE
    sort_field = {
        "firstName": "firstName",
        "lastName": "lastName",
        "birthdate": "birthdate",
        "displayFirstName": "displayFirstName",
        "displayLastName": "displayLastName"
    }.get(sortby, "firstName")

    # Configure German collation for proper sorting of umlauts
    collation = {
        'locale': 'de',
        'strength': 1  # Base characters and diacritics are considered primary differences
    }

    if club_alias or team_alias or q or active is not None:
        query = {"$and": []}
        if club_alias:
            query["$and"].append({"assignedTeams.clubAlias": club_alias})
            if team_alias:
                query["$and"].append({
                    "assignedTeams": {
                        "$elemMatch": {
                            "clubAlias": club_alias,
                            "teams.teamAlias": team_alias
                        }
                    }
                })
        if q:
            query["$and"].append({
                "$or": [{
                    "firstName": {
                        "$regex": f".*{q}.*",
                        "$options": "i"
                    }
                }, {
                    "lastName": {
                        "$regex": f".*{q}.*",
                        "$options": "i"
                    }
                }, {
                    "displayFirstName": {
                        "$regex": f".*{q}.*",
                        "$options": "i"
                    }
                }, {
                    "displayLastName": {
                        "$regex": f".*{q}.*",
                        "$options": "i"
                    }
                }, {
                    "assignedTeams.teams.passNo": {
                        "$regex": f".*{q}.*",
                        "$options": "i"
                    }
                }]
            })
        if active is not None and team_alias:
            # Use $elemMatch to ensure we're filtering the right team when team_alias is specified
            if active:
                # If we're looking for active=true, field must exist and be true for the correct team
                query["$and"].append({
                    "assignedTeams": {
                        "$elemMatch": {
                            "clubAlias": club_alias,
                            "teams": {
                                "$elemMatch": {
                                    "teamAlias": team_alias,
                                    "active": True
                                }
                            }
                        }
                    }
                })
            else:
                # If we're looking for active=false for a specific team
                query["$and"].append({
                    "assignedTeams": {
                        "$elemMatch": {
                            "clubAlias": club_alias,
                            "teams": {
                                "$elemMatch": {
                                    "teamAlias": team_alias,
                                    "$or": [
                                        {"active": False},
                                        {"active": {"$exists": False}}
                                    ]
                                }
                            }
                        }
                    }
                })
        elif active is not None:
            # If no team_alias specified, use the original logic across all teams
            if active:
                # If we're looking for active=true, field must exist and be true
                query["$and"].append({
                    "assignedTeams.teams.active": True
                })
            else:
                # If we're looking for active=false, either field doesn't exist or is false
                query["$and"].append({
                    "$or": [
                        {"assignedTeams.teams.active": False},
                        {"assignedTeams.teams.active": {"$exists": False}}
                    ]
                })
        if DEBUG_LEVEL > 10:
            print("query", query)
    else:
        query = {}

    total = await mongodb["players"].count_documents(query)
    players = await mongodb["players"].find(query).collation(collation).sort(
        sort_field, 1).skip(skip).limit(RESULTS_PER_PAGE).to_list(None)
    return {
        "total": total,
        "page": page,
        "results": [PlayerDB(**raw_player) for raw_player in players]
    }


# Helper function to create assignedTeams dict
async def build_assigned_teams_dict(assignedTeams, source, request):
    mongodb = request.app.state.mongodb
    # Deserialize the JSON string to Python objects
    assigned_teams_list = []
    try:
        assigned_teams_list = json.loads(assignedTeams)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400,
                            detail="Invalid JSON for assignedTeams")

    print(f"assigned_teams_list: {assigned_teams_list}")
    # Validate and convert to the proper Pydantic models
    assigned_teams_objs = [
        AssignedTeamsInput(**team_dict) for team_dict in assigned_teams_list
    ]

    assigned_teams_dict = []
    print("assignment_team_objs:", assigned_teams_objs)
    for club_to_assign in assigned_teams_objs:
        club_exists = await mongodb["clubs"].find_one(
            {"_id": club_to_assign.clubId})
        if not club_exists:
            raise HTTPException(
                status_code=400,
                detail=f"Club with id {club_to_assign.clubId} does not exist.")
        teams = []
        for team_to_assign in club_to_assign.teams:
            print("team_to_assign:", club_exists['name'], '/', team_to_assign)
            team = next((team for team in club_exists['teams']
                         if team['_id'] == team_to_assign.teamId), None)
            if not team:
                raise HTTPException(
                    status_code=400,
                    detail=
                    f"Team with id {team_to_assign.teamId} does not exist in club {club_to_assign.clubId}."
                )
            else:
                teams.append({
                    "teamId":
                    team['_id'],
                    "teamName":
                    team['name'],
                    "teamAlias":
                    team['alias'],
                    "teamIshdId":
                    team['ishdId'],
                    "passNo":
                    team_to_assign.passNo,
                    "jerseyNo":
                    team_to_assign.jerseyNo,
                    "active":
                    team_to_assign.active,
                    "source":
                    team_to_assign.source,
                    "modifyDate":
                    team_to_assign.modifyDate
                })
        assigned_teams_dict.append({
            "clubId": club_to_assign.clubId,
            "clubName": club_exists['name'],
            "clubAlias": club_exists['alias'],
            "clubIshdId": club_exists['ishdId'],
            "teams": teams,
        })
    return assigned_teams_dict


# PROCESS ISHD DATA
# ----------------------
@router.get(
    "/process_ishd_data",
    response_description="Process ISHD player data to BISHL-Application",
    include_in_schema=False)
async def process_ishd_data(
    request: Request,
    mode: Optional[str] = None,
    run: int = 1,
    #token_payload: TokenPayload = Depends(auth.auth_wrapper)
):
    mongodb = request.app.state.mongodb
    #if "ADMIN" not in token_payload.roles:
    #  raise HTTPException(status_code=403, detail="Nicht authorisiert")

    log_lines = []
    # If mode is 'test', delete all documents in 'players'
    if mode == "test" and run == 1:
        await mongodb['players'].delete_many({})
        log_line = "Deleted all documents in players."
        print(log_line)
        log_lines.append(log_line)

    ISHD_API_URL = os.environ.get("ISHD_API_URL")
    ISHD_API_USER = os.environ.get("ISHD_API_USER")
    ISHD_API_PASS = os.environ.get("ISHD_API_PASS")

    class IshdTeams:

        def __init__(self, club_id, club_ishd_id, club_name, club_alias,
                     teams):
            self.club_id = club_id
            self.club_ishd_id = club_ishd_id
            self.club_name = club_name
            self.club_alias = club_alias
            self.teams = teams

    ishd_teams = []
    create_date = datetime.now().replace(microsecond=0)

    async for club in mongodb['clubs'].aggregate([
        {
            "$match": {
                "active": True,
                #"ishdId": 143,
                #"teams.ishdId": {
                #    "$ne": None
                #},
                "teams": {
                    "$ne": []
                }
            }
        },
        {
            "$project": {
                "ishdId": 1,
                "_id": 1,
                "name": 1,
                "alias": 1,
                "teams": 1
            }
        },
        {
            "$sort": {
                "ishdId": 1
            }
        }
    ]):
        ishd_teams.append(
            IshdTeams(club['_id'], club['ishdId'], club['name'], club['alias'],
                      club['teams']))

    # get exisiting players
    existing_players = []
    async for player in mongodb['players'].find({}, {
            'firstName': 1,
            'lastName': 1,
            'birthdate': 1,
            'assignedTeams': 1,
    }):
        existing_players.append(player)

    #api_urls = []
    base_url_str = str(ISHD_API_URL)

    headers = {
        "Authorization":
        f"Basic {base64.b64encode(f'{ISHD_API_USER}:{ISHD_API_PASS}'.encode('utf-8')).decode('utf-8')}",
        "Connection": "close"
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
    #current_timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    #file_name = f'ishd_processing_{current_timestamp}.log'

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

    async with aiohttp.ClientSession() as session:
        # loop through team API URLs
        # for api_url in api_urls:

        ishd_log_base = IshdLogBase(
            processDate=datetime.now().replace(microsecond=0),
            clubs=[],
        )

        for club in ishd_teams:

            log_line = f"Processing club {club.club_name} (IshdId: {club.club_ishd_id})"
            print(log_line)
            log_lines.append(log_line)
            ishd_log_club = IshdLogClub(
                clubName=club.club_name,
                ishdId=club.club_ishd_id,
                teams=[],
            )

            for team in club.teams:
                if not team['ishdId']:
                    continue
                club_ishd_id_str = urllib.parse.quote(str(club.club_ishd_id))
                team_id_str = urllib.parse.quote(str(team['ishdId']))
                #if team_id_str != '1.%20Herren' and team_id_str != '2.%20Herren':
                #  break
                api_url = f"{base_url_str}/clubs/{club_ishd_id_str}/teams/{team_id_str}.json"
                ishd_log_team = IshdLogTeam(
                    teamIshdId=team['ishdId'],
                    url=api_url,
                    players=[],
                )

                # get data
                data = {}
                if mode == "test":
                    test_file = f"ishd_test{run}_{club_ishd_id_str}_{team['alias']}.json"
                    if os.path.exists(test_file):
                        log_line = f"Processing team {club.club_name} / {team['ishdId']} / {test_file}"
                        #print(log_line)
                        log_lines.append(log_line)
                        with open(test_file, 'r') as file:
                            data = json.load(file)
                            print("data", data)
                    else:
                        log_line = f"File {test_file} does not exist. Skipping..."
                        #print(log_line)
                        log_lines.append(log_line)
                else:
                    log_line = f"Processing team (URL): {club.club_name} / {team['ishdId']} / {api_url}"
                    print(log_line)
                    log_lines.append(log_line)

                    async with session.get(api_url,
                                           headers=headers) as response:
                        if response.status == 200:
                            data = await response.json()
                        elif response.status == 404:
                            log_line = f"API URL {api_url} returned a 404 status code."
                            print(log_line)
                            log_lines.append(log_line)
                        else:
                            raise HTTPException(
                                status_code=response.status,
                                detail=f"Error fetching data from {api_url}")
                if data:
                    # loop through players array
                    for player in data['players']:
                        # check ifplayer['date_of_birth'] is valid date
                        try:
                            birthdate = datetime.strptime(
                                player['date_of_birth'], '%Y-%m-%d')
                        except ValueError:
                            log_line = (f"ERROR: Invalid date format for player "
                                        f"{player['first_name']} {player['last_name']} "
                                        f"from club {club.club_name} and team {team['name']}")
                            print(log_line)
                            log_lines.append(log_line)
                            continue
                        ishd_log_player = IshdLogPlayer(
                            firstName=player['first_name'],
                            lastName=player['last_name'],
                            birthdate=datetime.strptime(
                                player['date_of_birth'], '%Y-%m-%d'))
                        #if player['first_name'] != "Leonid":
                        #  break
                        # build assignedTeams object
                        assigned_team = AssignedTeams(
                            teamId=team['_id'],
                            teamName=team['name'],
                            teamAlias=team['alias'],
                            teamIshdId=team['ishdId'],
                            passNo=player['license_number'],
                            source=SourceEnum.ISHD,
                            modifyDate=datetime.strptime(
                                player['last_modification'],
                                '%Y-%m-%d %H:%M:%S'))
                        assigned_club = AssignedClubs(
                            clubId=club.club_id,
                            clubName=club.club_name,
                            clubAlias=club.club_alias,
                            clubIshdId=club.club_ishd_id,
                            teams=[assigned_team])

                        # print("assigned_club", assigned_club)
                        # check if player already exists in existing_players array
                        player_exists = False
                        existing_player = None
                        for existing_player in existing_players:
                            if (existing_player['firstName']
                                    == player['first_name']
                                    and existing_player['lastName']
                                    == player['last_name']
                                    and datetime.strftime(
                                        existing_player['birthdate'],
                                        '%Y-%m-%d')
                                    == player['date_of_birth']):
                                player_exists = True
                                break

                        if player_exists and existing_player is not None:
                            # player already exists
                            # Check if team assignment exists for player
                            club_assignment_exists = False
                            if mode == "test":
                                print("player exists / existing_players",
                                      existing_players)
                            for club_assignment in existing_player.get(
                                    'assignedTeams', []):
                                if mode == "test":
                                    print("club_assignment", club_assignment)
                                if club_assignment[
                                        'clubName'] == club.club_name:
                                    if mode == "test":
                                        print(
                                            "club_assignment exists: club_name",
                                            club_assignment['clubName'])
                                    club_assignment_exists = True
                                    # club already exists
                                    team_assignment_exists = False
                                    for team_assignment in club_assignment.get(
                                            'teams', []):
                                        if team_assignment['teamId'] == team[
                                                '_id']:
                                            team_assignment_exists = True
                                            break
                                    if not team_assignment_exists:
                                        # team assignment does not exist
                                        # add team assignment to players existing club assignment
                                        club_assignment.get('teams').append(
                                            jsonable_encoder(assigned_team))
                                        # update player with new team assignment
                                        existing_player['assignedTeams'] = [
                                            club_assignment
                                        ] + [
                                            a for a in
                                            existing_player['assignedTeams']
                                            if a != club_assignment
                                        ]
                                        if mode == "test":
                                            print("add team / existing_player",
                                                  existing_player)
                                        # update player in database
                                        result = await mongodb[
                                            "players"
                                        ].update_one(
                                            {"_id": existing_player['_id']}, {
                                                "$set": {
                                                    "assignedTeams":
                                                    jsonable_encoder(
                                                        existing_player[
                                                            'assignedTeams'])
                                                }
                                            })
                                        if result.modified_count:
                                            log_line = f"Updated team assignment for: {existing_player.get('firstName')} {existing_player.get('lastName')} {datetime.strftime(existing_player.get('birthdate'), '%Y-%m-%d')} -> {club.club_name} / {team['ishdId']}"
                                            print(log_line)
                                            log_lines.append(log_line)
                                            ishd_log_player.action = IshdActionEnum.ADD_TEAM
                                        else:
                                            raise (HTTPException(
                                                status_code=status.
                                                HTTP_500_INTERNAL_SERVER_ERROR,
                                                detail=
                                                "Failed to update player."))
                                    break
                            if not club_assignment_exists:
                                # club assignment does not exist
                                if mode == "test":
                                    print(
                                        "club assignment does not exist / existing_players"
                                    )
                                # add club assignment to player
                                existing_player['assignedTeams'].append(
                                    jsonable_encoder(assigned_club))
                                if mode == "test":
                                    print("add club / existing_player: ",
                                          existing_player)
                                # update player with new club assignment
                                result = await mongodb["players"].update_one(
                                    {"_id": existing_player['_id']}, {
                                        "$set": {
                                            "source": SourceEnum.ISHD,
                                            "assignedTeams":
                                            jsonable_encoder(existing_player[
                                                'assignedTeams'])
                                        }
                                    })
                                if result.modified_count:
                                    log_line = f"New club assignment for: {existing_player.get('firstName')} {existing_player.get('lastName')} {datetime.strftime(existing_player.get('birthdate'), '%Y-%m-%d')} -> {club.club_name} / {team.get('ishdId')}"
                                    print(log_line)
                                    log_lines.append(log_line)
                                    ishd_log_player.action = IshdActionEnum.ADD_CLUB

                                else:
                                    raise (HTTPException(
                                        status_code=status.
                                        HTTP_500_INTERNAL_SERVER_ERROR,
                                        detail="Failed to update player."))

                        else:
                            # NEW PLAYER
                            # FIRST: construct Player object w/o assignedTeams
                            new_player = PlayerBase(
                                firstName=player['first_name'],
                                lastName=player['last_name'],
                                birthdate=datetime.strptime(
                                    player['date_of_birth'], '%Y-%m-%d'),
                                displayFirstName=player['first_name'],
                                displayLastName=player['last_name'],
                                nationality=player['nationality']
                                if 'nationality' in player else None,
                                assignedTeams=[assigned_club],
                                fullFaceReq=True if player.get('full_face_req')
                                == 'true' else False,
                                source=SourceEnum.ISHD)
                            new_player_dict = my_jsonable_encoder(new_player)
                            new_player_dict['birthdate'] = datetime.strptime(
                                player['date_of_birth'], '%Y-%m-%d')
                            new_player_dict['createDate'] = create_date

                            # add player to exisiting players array
                            existing_players.append(new_player_dict)

                            # insert player into database
                            result = await mongodb["players"].insert_one(
                                new_player_dict)
                            if result.inserted_id:
                                birthdate = new_player_dict.get('birthdate')
                                birthdate_str = birthdate.strftime(
                                    '%Y-%m-%d') if isinstance(
                                        birthdate, datetime) else 'Unknown'
                                log_line = f"Inserted player: {new_player_dict.get('firstName')} {new_player_dict.get('lastName')} {birthdate_str} -> {assigned_club.clubName} / {assigned_team.teamName}"
                                print(log_line)
                                log_lines.append(log_line)
                                if mode == "test":
                                    print("new player / existing_players",
                                          existing_players)
                                ishd_log_player.action = IshdActionEnum.ADD_PLAYER

                            else:
                                raise (HTTPException(
                                    status_code=status.
                                    HTTP_500_INTERNAL_SERVER_ERROR,
                                    detail="Failed to insert player."))

                        if ishd_log_player.action is not None:
                            ishd_log_team.players.append(ishd_log_player)

                    ishd_data.append(data)

                    # remove player of a team (still in team loop)
                    query = {
                        "assignedTeams": {
                            "$elemMatch": {
                                "clubAlias": club.club_alias,
                                "teams.teamAlias": team['alias']
                            }
                        }
                    }
                    players = await mongodb["players"].find(query).to_list(
                        length=None)
                    if mode == "test":
                        print("removing / players:", players)
                    if players:
                        for player in players:
                            ishd_log_player_remove = IshdLogPlayer(
                                firstName=player['firstName'],
                                lastName=player['lastName'],
                                birthdate=player['birthdate'],
                            )
                            if mode == "test":
                                print("remove player ?", player)
                            # remove player from team only if source is ISHD
                            team_source_is_ishd = False
                            for club_assignment in player.get('assignedTeams', []):
                                if club_assignment.get('clubAlias') == club.club_alias:
                                    for team_assignment in club_assignment.get('teams', []):
                                        if team_assignment.get('teamAlias') == team['alias'] and team_assignment.get('source') == 'ISHD':
                                            team_source_is_ishd = True
                                            break

                            if team_source_is_ishd and not any(
                                    p['first_name'] == player['firstName']
                                    and p['last_name'] == player['lastName']
                                    and p['date_of_birth'] == datetime.
                                    strftime(player['birthdate'], '%Y-%m-%d')
                                    for p in data['players']):
                                query = {
                                    "$and": [{
                                        "_id": player['_id']
                                    }, {
                                        "assignedTeams": {
                                            "$elemMatch": {
                                                "clubAlias": club.club_alias,
                                                "teams": {
                                                    "$elemMatch": {
                                                        "teamAlias":
                                                        team['alias']
                                                    }
                                                }
                                            }
                                        }
                                    }]
                                }
                                # print("query", query)
                                result = await mongodb["players"].update_one(
                                    query, {
                                        "$pull": {
                                            "assignedTeams.$.teams": {
                                                "teamAlias": team['alias']
                                            }
                                        }
                                    })
                                if result.modified_count:
                                    # Update existing_players array to remove team assignment
                                    for existing_player in existing_players:
                                        if existing_player['_id'] == player[
                                                '_id']:
                                            for club_assignment in existing_player.get(
                                                    'assignedTeams', []):
                                                if club_assignment[
                                                        'clubAlias'] == club.club_alias:
                                                    club_assignment['teams'] = [
                                                        t for t in
                                                        club_assignment['teams']
                                                        if t['teamAlias'] !=
                                                        team['alias']
                                                    ]
                                                    break

                                    log_line = f"Removed player from team: {player.get('firstName')} {player.get('lastName')} {datetime.strftime(player.get('birthdate'), '%Y-%m-%d')} -> {club.club_name} / {team.get('ishdId')}"
                                    print(log_line)
                                    log_lines.append(log_line)
                                    ishd_log_player_remove.action = IshdActionEnum.DEL_TEAM

                                    # After removing team assignment, if the teams array is empty, remove the club assignment
                                    result = await mongodb[
                                        "players"].update_one(
                                            {
                                                "_id":
                                                player['_id'],
                                                "assignedTeams.clubIshdId":
                                                club.club_ishd_id
                                            }, {
                                                "$pull": {
                                                    "assignedTeams": {
                                                        "teams": {
                                                            "$size": 0
                                                        }
                                                    }
                                                }
                                            })
                                    if result.modified_count:
                                        # Update existing_players array to remove club assignment
                                        for existing_player in existing_players:
                                            if existing_player[
                                                    '_id'] == player['_id']:
                                                existing_player[
                                                    'assignedTeams'] = [
                                                        a for a in
                                                        existing_player.get(
                                                            'assignedTeams',
                                                            [])
                                                        if a['clubIshdId'] !=
                                                        club.club_ishd_id
                                                    ]
                                                break

                                        log_line = f"Removed club assignment for player: {player.get('firstName')} {player.get('lastName')} {datetime.strftime(player.get('birthdate'), '%Y-%m-%d')} -> {club.club_name}"
                                        print(log_line)
                                        log_lines.append(log_line)
                                        ishd_log_player_remove.action = IshdActionEnum.DEL_CLUB
                                    else:
                                        print('--- No club assignment removed')

                                else:
                                    raise (HTTPException(
                                        status_code=status.
                                        HTTP_500_INTERNAL_SERVER_ERROR,
                                        detail="Failed to remove player."))
                            else:
                                if mode == "test":
                                    print(
                                        "player exists in team - do not remove"
                                    )

                            if ishd_log_player_remove.action is not None:
                                #print("--- ishd_log_player", ishd_log_player_remove)
                                ishd_log_team.players.append(
                                    ishd_log_player_remove)

                #print(f"--- ishd_log_team", ishd_log_team)
                if ishd_log_team:
                    ishd_log_club.teams.append(ishd_log_team)

            #print(f"--- ishd_log_club", ishd_log_club)
            if ishd_log_club:
                ishd_log_base.clubs.append(ishd_log_club)

    await session.close()

    #with open(file_name, 'w') as logfile:
    #  logfile.write('\n'.join(log_lines))

    ishd_log_base_enc = my_jsonable_encoder(ishd_log_base)
    #ishd_log_base_enc['processDate'] = create_date
    result = await mongodb["ishdLogs"].insert_one(ishd_log_base_enc)
    if result.inserted_id:
        log_line = "Inserted ISHD log into ishdLogs collection."
        print(log_line)
        log_lines.append(log_line)
    else:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to insert ISHD log.")

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "message": "ISHD data processed successfully",
            "logs": log_lines,
            #"data": ishd_data
        })


# VERIFY ISHD DATA
# ----------------------
@router.get("/verify_ishd_data",
            response_description="Verify player assignments against ISHD data",
            include_in_schema=False)
async def verify_ishd_data(
    request: Request,
    mode: Optional[str] =None,
    #token_payload: TokenPayload = Depends(auth.auth_wrapper)
):
    mongodb = request.app.state.mongodb
    #if "ADMIN" not in token_payload.roles:
    #    raise HTTPException(status_code=403, detail="Nicht authorisiert")

    ISHD_API_URL = os.environ.get("ISHD_API_URL")
    ISHD_API_USER = os.environ.get("ISHD_API_USER")
    ISHD_API_PASS = os.environ.get("ISHD_API_PASS")

    verification_results = {
        "missing_in_ishd": [],
        "missing_in_db": [],
        "team_mismatches": [],
        "club_mismatches": []
    }

    # Get all active clubs with ISHD teams
    ishd_teams = []
    async for club in mongodb['clubs'].aggregate([{
            "$match": {
                "active": True,
                "teams.ishdId": {
                    "$ne": None
                },
                "teams": {
                    "$ne": []
                }
            }
    }]):
        for team in club['teams']:
            if team.get('ishdId'):
                ishd_teams.append({
                    'club_id': club['_id'],
                    'club_name': club['name'],
                    'club_alias': club['alias'],
                    'club_ishd_id': club['ishdId'],
                    'team_id': team['_id'],
                    'team_name': team['name'],
                    'team_alias': team['alias'],
                    'team_ishd_id': team['ishdId']
                })

    headers = {
        "Authorization":
        f"Basic {base64.b64encode(f'{ISHD_API_USER}:{ISHD_API_PASS}'.encode('utf-8')).decode('utf-8')}",
        "Connection": "close"
    }

    # Get all players from database
    db_players = {}
    async for player in mongodb['players'].find({}):
        key = f"{player['firstName']}_{player['lastName']}_{datetime.strftime(player['birthdate'], '%Y-%m-%d')}"
        db_players[key] = {'player': player, 'assignments': []}
        for club in player.get('assignedTeams', []):
            for team in club.get('teams', []):
                db_players[key]['assignments'].append({
                    'clubId':
                    club['clubId'],
                    'clubName':
                    club['clubName'],
                    'teamId':
                    team['teamId'],
                    'teamName':
                    team['teamName']
                })

    async with aiohttp.ClientSession() as session:
        ishd_players = {}

        for team_info in ishd_teams:
            club_ishd_id_str = urllib.parse.quote(
                str(team_info['club_ishd_id']))
            team_id_str = urllib.parse.quote(str(team_info['team_ishd_id']))
            api_url = f"{ISHD_API_URL}/clubs/{club_ishd_id_str}/teams/{team_id_str}.json"

            if mode == "test":
                test_file = f"ishd_test1_{club_ishd_id_str}_{team_info['team_alias']}.json"
                if os.path.exists(test_file):
                    with open(test_file, 'r') as file:
                        data = json.load(file)
                else:
                    continue
            else:
                async with session.get(api_url, headers=headers) as response:
                    if response.status != 200:
                        continue
                    data = await response.json()

            for player in data['players']:
                key = f"{player['first_name']}_{player['last_name']}_{player['date_of_birth']}"
                if key not in ishd_players:
                    ishd_players[key] = []
                ishd_players[key].append({
                    'clubId': team_info['club_id'],
                    'clubName': team_info['club_name'],
                    'teamId': team_info['team_id'],
                    'teamName': team_info['team_name']
                })

        # Compare players
        for key, ishd_data in ishd_players.items():
            if key not in db_players:
                # Player exists in ISHD but not in DB
                player_name = key.split('_')
                # Group assignments by club
                club_assignments = {}
                for assignment in ishd_data:
                    club_id = assignment['clubId']
                    if club_id not in club_assignments:
                        club_assignments[club_id] = {
                            'clubId': club_id,
                            'clubName': assignment['clubName'],
                            'teams': []
                        }
                    club_assignments[club_id]['teams'].append({
                        'teamId':
                        assignment['teamId'],
                        'teamName':
                        assignment['teamName']
                    })

                verification_results['missing_in_db'].append({
                    'firstName':
                    player_name[0],
                    'lastName':
                    player_name[1],
                    'birthdate':
                    player_name[2],
                    'ishd_assignments':
                    list(club_assignments.values())
                })
            else:
                db_data = db_players[key]
                # Create lookup dictionaries for efficient comparison
                db_assignments_by_club = {}
                for assignment in db_data['assignments']:
                    club_id = assignment['clubId']
                    if club_id not in db_assignments_by_club:
                        db_assignments_by_club[club_id] = {
                            'clubName': assignment['clubName'],
                            'teams': set()
                        }
                    db_assignments_by_club[club_id]['teams'].add(
                        assignment['teamId'])

                ishd_assignments_by_club = {}
                for assignment in ishd_data:
                    club_id = assignment['clubId']
                    if club_id not in ishd_assignments_by_club:
                        ishd_assignments_by_club[club_id] = {
                            'clubName': assignment['clubName'],
                            'teams': set()
                        }
                    ishd_assignments_by_club[club_id]['teams'].add(
                        assignment['teamId'])

                # Compare assignments
                for club_id, ishd_club_data in ishd_assignments_by_club.items(
                ):
                    if club_id not in db_assignments_by_club:
                        # Club assignment missing in DB
                        verification_results['club_mismatches'].append({
                            'player': {
                                'firstName':
                                db_data['player']['firstName'],
                                'lastName':
                                db_data['player']['lastName'],
                                'birthdate':
                                datetime.strftime(
                                    db_data['player']['birthdate'], '%Y-%m-%d')
                            },
                            'ishd_assignment': {
                                'clubId':
                                club_id,
                                'clubName':
                                ishd_club_data['clubName'],
                                'teams': [{
                                    'teamId': t
                                } for t in ishd_club_data['teams']]
                            },
                            'db_assignments':
                            db_data['assignments']
                        })
                    else:
                        # Compare team assignments within club
                        db_club_data = db_assignments_by_club[club_id]
                        team_differences = ishd_club_data[
                            'teams'] - db_club_data['teams']
                        if team_differences:
                            # Teams missing in DB for this club
                            for team_id in team_differences:
                                team_data = next((t for t in ishd_data
                                                  if t['teamId'] == team_id),
                                                 None)
                                if team_data:
                                    verification_results[
                                        'team_mismatches'].append({
                                            'player': {
                                                'firstName':
                                                db_data['player']['firstName'],
                                                'lastName':
                                                db_data['player']['lastName'],
                                                'birthdate':
                                                datetime.strftime(
                                                    db_data['player']
                                                    ['birthdate'], '%Y-%m-%d')
                                            },
                                            'ishd_team': {
                                                'clubId':
                                                club_id,
                                                'clubName':
                                                ishd_club_data['clubName'],
                                                'teamId':
                                                team_id,
                                                'teamName':
                                                team_data['teamName']
                                            },
                                            'db_assignments': [
                                                a
                                                for a in db_data['assignments']
                                                if a['clubId'] == club_id
                                            ]
                                        })

        # Check for players in DB but not in ISHD
        for key, db_data in db_players.items():
            if key not in ishd_players:
                # Group assignments by club for better readability
                club_assignments = {}
                for assignment in db_data['assignments']:
                    club_id = assignment['clubId']
                    if club_id not in club_assignments:
                        club_assignments[club_id] = {
                            'clubId': club_id,
                            'clubName': assignment['clubName'],
                            'teams': []
                        }
                    club_assignments[club_id]['teams'].append({
                        'teamId':
                        assignment['teamId'],
                        'teamName':
                        assignment['teamName']
                    })

                verification_results['missing_in_ishd'].append({
                    'player': {
                        'firstName':
                        db_data['player']['firstName'],
                        'lastName':
                        db_data['player']['lastName'],
                        'birthdate':
                        datetime.strftime(db_data['player']['birthdate'],
                                          '%Y-%m-%d')
                    },
                    'db_assignments':
                    list(club_assignments.values())
                })

    return JSONResponse(status_code=status.HTTP_200_OK,
                        content=jsonable_encoder(verification_results))


# GET ALL PLAYERS FOR ONE CLUB
# --------
@router.get("/clubs/{club_alias}",
            response_description="Get all players for a club",
            response_model=List[PlayerDB])
async def get_players_for_club(
    request: Request,
    club_alias: str,
    page: int = 1,
    q: Optional[str] = None,
    sortby: str = "firstName",
    all: bool = False,
    active: Optional[bool] = None,
    token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    if not any(role in token_payload.roles
               for role in ["ADMIN", "CLUB_ADMIN", "LEAGUE_ADMIN"]):
        raise HTTPException(status_code=403, detail="Nicht authorisiert")
    # get club
    club = await mongodb["clubs"].find_one({"alias": club_alias})
    if not club:
        raise HTTPException(status_code=404,
                            detail=f"Club with alias {club_alias} not found")
    result = await get_paginated_players(mongodb, q, page, club_alias, None, sortby, all, active)
    return JSONResponse(status_code=status.HTTP_200_OK,
                        content=jsonable_encoder(result))


# GET ALL PLAYERS FOR ONE CLUB/TEAM
# --------
@router.get("/clubs/{club_alias}/teams/{team_alias}",
            response_description="Get all players for a team",
            response_model=List[PlayerDB])
async def get_players_for_team(
    request: Request,
    club_alias: str,
    team_alias: str,
    page: int = 1,
    q: Optional[str] = None,
    sortby: str = "firstName",
    all: bool = False,
    active: Optional[bool] = None,
    token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    print(token_payload.roles)
    if not any(role in token_payload.roles
               for role in ["ADMIN", "CLUB_ADMIN", "LEAGUE_ADMIN"]):
        raise HTTPException(status_code=403, detail="Nicht authorisiert")
    # get club
    club = await mongodb["clubs"].find_one({"alias": club_alias})
    if not club:
        raise HTTPException(status_code=404,
                            detail=f"Club with alias {club_alias} not found")
    # get team
    team = None
    for t in club.get("teams", []):
        if t["alias"] == team_alias:
            team = t
            break
    if not team:
        raise HTTPException(
            status_code=404,
            detail=
            f"Team with alias {team_alias} not found in club {club_alias}")
    result = await get_paginated_players(mongodb, q, page, club_alias,
                                         team_alias, sortby, all, active)
    return JSONResponse(status_code=status.HTTP_200_OK,
                        content=jsonable_encoder(result))


# GET ALL PLAYERS
# -------------------
class PaginatedPlayerResponse(BaseModel):
    total: int
    page: int
    results: List[PlayerDB]


@router.get("/",
            response_description="Get all players",
            response_model=PaginatedPlayerResponse)
async def get_players(
    request: Request,
    page: int = 1,
    q: Optional[str] = None,
    sortby: str = "firstName",
    all: bool = False,
    active: Optional[bool] = None,
    token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    if not any(role in token_payload.roles
               for role in ["ADMIN", "LEAGUE_ADMIN"]):
        raise HTTPException(status_code=403, detail="Nicht authorisiert")

    result = await get_paginated_players(mongodb, q, page, None, None, sortby, all, active)
    return JSONResponse(status_code=status.HTTP_200_OK,
                        content=jsonable_encoder(result))


# GET ONE PLAYER
# --------------------
@router.get("/{id}",
            response_description="Get a player by ID",
            response_model=PlayerDB)
async def get_player(
    id: str,
    request: Request,
    token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    player = await mongodb["players"].find_one({"_id": id})
    if player is None:
        raise HTTPException(status_code=404,
                            detail=f"Player with id {id} not found")
    return JSONResponse(status_code=status.HTTP_200_OK,
                        content=jsonable_encoder(PlayerDB(**player)))


# CREATE NEW PLAYER
# ----------------------
@router.post("/",
             response_description="Add new player",
             response_model=PlayerDB)
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
    fullFaceReq: bool = Form(False),
    source: SourceEnum = Form(default=SourceEnum.BISHL),
    legacyId: int = Form(None),
    image: UploadFile = File(None),
    imageVisible: bool = Form(False),
    token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    if not any(role in token_payload.roles
               for role in ["ADMIN", "PLAYER_ADMIN"]):
        raise HTTPException(status_code=403, detail="Nicht authorisiert")

    player_exists = await mongodb["players"].find_one({
        "firstName": firstName,
        "lastName": lastName,
        "birthdate": birthdate
    })
    if player_exists:
        raise HTTPException(
            status_code=400,
            detail=
            f"Player with name {firstName} {lastName} and birthdate {birthdate.strftime('%d.%m.%Y')} already exists."
        )

    if assignedTeams:
        assigned_teams_dict = await build_assigned_teams_dict(
            assignedTeams, source, request)
    else:
        assigned_teams_dict = []

    # Generate a new ID for the player
    player_id = str(ObjectId())

    player = PlayerBase(firstName=firstName,
                        lastName=lastName,
                        birthdate=birthdate,
                        displayFirstName=displayFirstName,
                        displayLastName=displayLastName,
                        nationality=nationality,
                        position=position,
                        assignedTeams=assigned_teams_dict,
                        fullFaceReq=fullFaceReq,
                        source=SourceEnum[source],
                        imageVisible=imageVisible,
                        legacyId=legacyId)
    player = my_jsonable_encoder(player)
    player['create_date'] = datetime.now().replace(microsecond=0)
    player['_id'] = player_id

    if image:
        player['imageUrl'] = await handle_image_upload(image, player_id)

    try:
        print("insert player:", player)
        new_player = await mongodb["players"].insert_one(player)
        created_player = await mongodb["players"].find_one({"_id": player_id})
        if created_player:
            return JSONResponse(status_code=status.HTTP_201_CREATED,
                                content=jsonable_encoder(
                                    PlayerDB(**created_player)))
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create player.")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=str(e))


# UPDATE PLAYER
# ----------------------
@router.patch("/{id}",
              response_description="Update player",
              response_model=PlayerDB)
async def update_player(request: Request,
                        id: str,
                        firstName: Optional[str] = Form(None),
                        lastName: Optional[str] = Form(None),
                        birthdate: Optional[datetime] = Form(None),
                        displayFirstName: Optional[str] = Form(None),
                        displayLastName: Optional[str] = Form(None),
                        nationality: Optional[str] = Form(None),
                        position: Optional[PositionEnum] = Form(None),
                        assignedTeams: Optional[str] = Form(None),
                        stats: Optional[str] = Form(None),
                        fullFaceReq: Optional[bool] = Form(None),
                        source: Optional[SourceEnum] = Form(None),
                        image: Optional[UploadFile] = File(None),
                        imageUrl: Optional[HttpUrl] = Form(None),
                        imageVisible: Optional[bool] = Form(None),
                        token_payload: TokenPayload = Depends(
                            auth.auth_wrapper)):
    mongodb = request.app.state.mongodb
    if not any(role in token_payload.roles
               for role in ["ADMIN", "CLUB_ADMIN", "PLAYER_ADMIN"]):
        raise HTTPException(status_code=403, detail="Nicht authorisiert")
    existing_player = await mongodb["players"].find_one({"_id": id})
    if not existing_player:
        raise HTTPException(status_code=404,
                            detail=f"Player with id {id} not found")

    current_first_name = firstName or existing_player.get("firstName")
    current_last_name = lastName or existing_player.get("lastName")
    current_birthdate = birthdate or existing_player.get("birthdate")
    player_exists = await mongodb["players"].find_one({
        "firstName": current_first_name,
        "lastName": current_last_name,
        "birthdate": current_birthdate,
        "_id": {
            "$ne": id
        }  # Checking for a different _id
    })
    if player_exists:
        raise HTTPException(
            status_code=400,
            detail=
            f"Player with name {current_first_name} {current_last_name} and birthdate {current_birthdate.strftime('%d.%m.%Y')} already exists."
        )

    if assignedTeams:
        assigned_teams_dict = await build_assigned_teams_dict(
            assignedTeams, source, request)
    else:
        assigned_teams_dict = None
    player_data = PlayerUpdate(firstName=firstName,
                               lastName=lastName,
                               birthdate=birthdate,
                               displayFirstName=displayFirstName,
                               displayLastName=displayLastName,
                               nationality=nationality,
                               position=position,
                               assignedTeams=assigned_teams_dict,
                               stats=json.loads(stats) if stats else None,
                               fullFaceReq=fullFaceReq,
                               imageVisible=imageVisible,
                               source=source).dict(exclude_none=True)

    player_data.pop('id', None)
    if image:
        player_data['imageUrl'] = await handle_image_upload(image, id)
    elif imageUrl:
        player_data['imageUrl'] = imageUrl
    elif existing_player.get('imageUrl'):
        await delete_from_cloudinary(existing_player['imageUrl'])
        player_data['imageUrl'] = None
    else:
        player_data['imageUrl'] = None
    print("player_data", player_data)

    # exclude unchanged data
    player_to_update = {
        k: v
        for k, v in player_data.items()
        if (k == 'birthdate' and v.strftime('%Y-%m-%d') != existing_player.get(
            k, None).strftime('%Y-%m-%d')) or (
                k != 'birthdate' and v != existing_player.get(k, None))
    }

    print("player_to_update", player_to_update)
    if not player_to_update:
        print("No changes to update")
        return Response(status_code=status.HTTP_304_NOT_MODIFIED)

    try:
        update_result = await mongodb["players"].update_one(
            {"_id": id}, {"$set": player_to_update}, upsert=False)
        if update_result.modified_count == 1:
            updated_player = await mongodb["players"].find_one({"_id": id})
            return JSONResponse(status_code=status.HTTP_200_OK,
                                content=jsonable_encoder(
                                    PlayerDB(**updated_player)))
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            content="Failed to update player.")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=str(e))


# DELETE PLAYER
# ----------------------
@router.delete("/{id}", response_description="Delete a player by ID")
async def delete_player(
    request: Request,
    id: str,
    token_payload: TokenPayload = Depends(auth.auth_wrapper)) -> Response:
    mongodb = request.app.state.mongodb
    if "ADMIN" not in token_payload.roles:
        raise HTTPException(status_code=403, detail="Nicht authorisiert")
    existing_player = await mongodb["players"].find_one({"_id": id})
    if not existing_player:
        raise HTTPException(status_code=404,
                            detail=f"Player with id {id} not found")
    delete_result = await mongodb["players"].delete_one({"_id": id})
    if delete_result.deleted_count == 1:
        await delete_from_cloudinary(existing_player['imageUrl'])
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    raise HTTPException(status_code=404,
                        detail=f"Player with ID {id} not found.")