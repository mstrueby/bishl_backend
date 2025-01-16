from fastapi import APIRouter, HTTPException, Form, Request, Body, Depends, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
import json
from typing import List, Optional, Dict

from pydantic.types import OptionalInt
from utils import my_jsonable_encoder
from models.players import PlayerBase, PlayerDB, PlayerUpdate, AssignedClubs, AssignedTeams, AssignedTeamsInput, PositionEnum, SourceEnum, IshdActionEnum, IshdLogBase, IshdLogPlayer, IshdLogTeam, IshdLogClub
from authentication import AuthHandler, TokenPayload
from datetime import datetime
import os
import urllib.parse
import aiohttp, base64

router = APIRouter()
auth = AuthHandler()


# Helper function to search players
async def get_paginated_players(mongodb,
                                q,
                                page,
                                club_alias=None,
                                team_alias=None):
  RESULTS_PER_PAGE = int(os.environ['RESULTS_PER_PAGE'])
  skip = (page - 1) * RESULTS_PER_PAGE
  #query = {}
  #{ "assignedTeams": { "$elemMatch": { "clubAlias": "spreewoelfe-berlin", "teams.teamAlias": "1-herren" } } }
  if club_alias or team_alias or q:
    query = {"$and": []}
    if club_alias:
      query["$and"].append({"assignedTeams.clubAlias": club_alias})
      if team_alias:
        query["$and"].append({"assignedTeams": {"$elemMatch": {"clubAlias": club_alias, "teams.teamAlias": team_alias}}})
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
            "assignedTeams.teams.passNo": {
                "$regex": f".*{q}.*",
                "$options": "i"
            }
        }]
    })
    print("query", query)
  else:
    query = {}
  players = await mongodb["players"].find(query).sort(
      "firstName", 1).skip(skip).limit(RESULTS_PER_PAGE).to_list(None)
  return [PlayerDB(**raw_player) for raw_player in players]


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
                   if team['_id'] == team_to_assign['teamId']), None)
      if not team:
        raise HTTPException(
            status_code=400,
            detail=
            f"Team with id {team_to_assign['teamId']} does not exist in club {club_to_assign.clubId}."
        )
      else:
        teams.append({
            "teamId": team['_id'],
            "teamName": team['name'],
            "teamAlias": team['alias'],
            "teamIshdId": team['ishdId'],
            "passNo": team_to_assign['passNo'],
            "source": source,
            "modifyate": datetime.now().replace(microsecond=0),
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
    response_description="Process ISHD player data to BISHL-Application")
async def process_ishd_data(request: Request,
                            mode: Optional[str] = None,
                            run: int = 1,
                            token_payload: TokenPayload = Depends(
                                auth.auth_wrapper)):
  mongodb = request.app.state.mongodb
  if token_payload.roles not in [["ADMIN"]]:
    raise HTTPException(status_code=403, detail="Not authorized")

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

    def __init__(self, club_id, club_ishd_id, club_name, club_alias, teams):
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
              #"ishdId": 39,
              "teams.ishdId": {
                  "$ne": None
              },
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
  current_timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
  file_name = f'ishd_processing_{current_timestamp}.log'

  # Keep only the 10 most recent log files, delete older ones
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

  async with aiohttp.ClientSession() as session:
    # loop through teaam API URLs
    #for api_url in api_urls:

    ishd_log_base = IshdLogBase(
      processDate=datetime.now().replace(microsecond=0),
      clubs=[],
    )
    
    for club in ishd_teams:

      log_line = f"Processing club {club.club_name} (IshdId: {club.club_ishd_id})"
      print(log_line)
      log_lines.append(log_line)
      ishd_log_club = IshdLogClub(
        clubName = club.club_name,
        ishdId = club.club_ishd_id,
        teams = [],
      )

      for team in club.teams:
        print("team", team)
        club_ishd_id_str = urllib.parse.quote(str(club.club_ishd_id))
        team_id_str = urllib.parse.quote(str(team['ishdId']))
        api_url = f"{base_url_str}/clubs/{club_ishd_id_str}/teams/{team_id_str}.json"
        ishd_log_team = IshdLogTeam(
          teamIshdId = team['ishdId'],
          url = api_url,
          players = [],
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
          
          async with session.get(api_url, headers=headers) as response:
            if response.status == 200:
              data = await response.json()
            elif response.status == 404:
              log_line = f"API URL {api_url} returned a 404 status code."
              print(log_line)
              log_lines.append(log_line)
            else:
              raise HTTPException(status_code=response.status,
                                  detail=f"Error fetching data from {api_url}")
        if data:
          # loop through players array
          for player in data['players']:
            ishd_log_player = IshdLogPlayer(
              firstName=player['first_name'],
              lastName=player['last_name'],
              birthdate= datetime.strptime(
                player['date_of_birth'], '%Y-%m-%d')             
            )
            #if player['first_name'] != "Anabel":
            #  break
            # build assignedTeams object
            assigned_team = AssignedTeams(teamId=team['_id'],
                                          teamName=team['name'],
                                          teamAlias=team['alias'],
                                          teamIshdId=team['ishdId'],
                                          passNo=player['license_number'],
                                          source=SourceEnum.ISHD,
                                          modifyDate=datetime.strptime(
                                              player['last_modification'],
                                              '%Y-%m-%d %H:%M:%S'))
            assigned_club = AssignedClubs(clubId=club.club_id,
                                          clubName=club.club_name,
                                          clubAlias=club.club_alias,
                                          clubIshdId=club.club_ishd_id,
                                          teams=[assigned_team])
            # check if player already exists in existing_players array
            player_exists = False
            existing_player = None
            for existing_player in existing_players:
              if (existing_player['firstName'] == player['first_name']
                  and existing_player['lastName'] == player['last_name'] and
                  datetime.strftime(existing_player['birthdate'],
                                    '%Y-%m-%d') == player['date_of_birth']):
                player_exists = True
                break

            if player_exists and existing_player is not None:
              # player already exists
              # Check if team assignment exists for player
              club_assignment_exists = False
              if mode == "test":
                print("player exists / existing_players", existing_players)
              for club_assignment in existing_player.get('assignedTeams', []):
                if mode == "test":
                  print("club_assignment", club_assignment)
                if club_assignment['clubName'] == club.club_name:
                  if mode == "test":
                    print("club_assignment exists: club_name",
                          club_assignment['clubName'])
                  club_assignment_exists = True
                  # club already exists
                  team_assignment_exists = False
                  for team_assignment in club_assignment.get('teams', []):
                    if team_assignment['teamId'] == team['_id']:
                      team_assignment_exists = True
                      break
                  if not team_assignment_exists:
                    # team assignment does not exist
                    # add team assignment to players existing club assignment
                    club_assignment.get('teams').append(assigned_team)
                    # update player with new team assignment
                    existing_player['assignedTeams'] = [club_assignment] + [
                        a for a in existing_player['assignedTeams']
                        if a != club_assignment
                    ]
                    if mode == "test":
                      print("add team / existing_player", existing_player)
                    # update player in database
                    result = await mongodb["players"].update_one(
                        {"_id": existing_player['_id']}, {
                            "$set": {
                                "assignedTeams":
                                jsonable_encoder(
                                    existing_player['assignedTeams'])
                            }
                        })
                    if result.modified_count:
                      log_line = f"Updated team assignment for: {existing_player.get('firstName')} {existing_player.get('lastName')} {datetime.strftime(existing_player.get('birthdate'), '%Y-%m-%d')} -> {club.club_name} / {team['ishdId']}"
                      print(log_line)
                      log_lines.append(log_line)
                      ishd_log_player.action = IshdActionEnum.ADD_TEAM
                    else:
                      raise (HTTPException(
                          status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                          detail="Failed to update player."))
                  break
              if not club_assignment_exists:
                # club assignment does not exist
                if mode == "test":
                  print("club assignment does not exist / existing_players")
                # add club assignment to player
                existing_player['assignedTeams'].append(
                    jsonable_encoder(assigned_club))
                if mode == "test":
                  print("add club / existing_player: ", existing_player)
                # update player with new club assignment
                result = await mongodb["players"].update_one(
                    {"_id": existing_player['_id']}, {
                        "$set": {
                            "assignedTeams":
                            jsonable_encoder(existing_player['assignedTeams'])
                        }
                    })
                if result.modified_count:
                  log_line = f"New club assignment for: {existing_player.get('firstName')} {existing_player.get('lastName')} {datetime.strftime(existing_player.get('birthdate'), '%Y-%m-%d')} -> {club.club_name} / {team.get('ishdId')}"
                  print(log_line)
                  log_lines.append(log_line)
                  ishd_log_player.action = IshdActionEnum.ADD_CLUB

                else:
                  raise (HTTPException(
                      status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                      detail="Failed to update player."))

            else:
              # NEW PLAYER
              # FIRST: construct Player object w/o assignedTeams
              new_player = PlayerBase(
                  firstName=player['first_name'],
                  lastName=player['last_name'],
                  birthdate=datetime.strptime(player['date_of_birth'],
                                              '%Y-%m-%d'),
                  displayFirstName=player['first_name'],
                  displayLastName=player['last_name'],
                  nationality=player['nationality']
                  if 'nationality' in player else None,
                  assignedTeams=[assigned_club],
                  fullFaceReq=True
                  if player.get('full_face_req') == 'true' else False,
                  source=SourceEnum.ISHD)
              new_player_dict = my_jsonable_encoder(new_player)
              new_player_dict['birthdate'] = datetime.strptime(
                  player['date_of_birth'], '%Y-%m-%d')
              new_player_dict['createDate'] = create_date

              # add player to exisiting players array
              existing_players.append(new_player_dict)

              # insert player into database
              result = await mongodb["players"].insert_one(new_player_dict)
              if result.inserted_id:
                birthdate = new_player_dict.get('birthdate')
                birthdate_str = birthdate.strftime('%Y-%m-%d') if isinstance(
                    birthdate, datetime) else 'Unknown'
                log_line = f"Inserted player: {new_player_dict.get('firstName')} {new_player_dict.get('lastName')} {birthdate_str} -> {assigned_club.clubName} / {assigned_team.teamName}"
                print(log_line)
                log_lines.append(log_line)
                if mode == "test":
                  print("new player / existing_players", existing_players)
                ishd_log_player.action = IshdActionEnum.ADD_PLAYER

              else:
                raise (HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to insert player."))

            if ishd_log_player.action is not None:
              ishd_log_team.players.append(ishd_log_player)
          
          ishd_data.append(data)

          # remove player of a team (still in team loop)
          query = {"$and": []}
          query["$and"].append({"assignedTeams.clubAlias": club.club_alias})
          query["$and"].append(
              {"assignedTeams.teams.teamAlias": team['alias']})
          players = await mongodb["players"].find(query).to_list(length=None)
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
              # remove player from team
              if not any(
                  p['first_name'] == player['firstName'] and p['last_name'] ==
                  player['lastName'] and p['date_of_birth'] ==
                  datetime.strftime(player['birthdate'], '%Y-%m-%d')
                  for p in data['players']):
                query = {"$and": []}
                query["$and"].append({"_id": player['_id']})
                query["$and"].append(
                    {"assignedTeams.clubAlias": club.club_alias})
                query["$and"].append(
                    {"assignedTeams.teams.teamAlias": team['alias']})
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
                  log_line = f"Removed player from team: {player.get('firstName')} {player.get('lastName')} {datetime.strftime(player.get('birthdate'), '%Y-%m-%d')} -> {club.club_name} / {team.get('ishdId')}"
                  print(log_line)
                  log_lines.append(log_line)
                  ishd_log_player_remove.action =IshdActionEnum.DEL_TEAM                  

                  # After removing team assignment, if the teams array is empty, remove the club assignment
                  result = await mongodb["players"].update_one(
                      {
                          "_id": player['_id'],
                          "assignedTeams.clubIshdId": club.club_ishd_id
                      },
                      {"$pull": {
                          "assignedTeams": {
                              "teams": {
                                  "$size": 0
                              }
                          }
                      }})

                  if result.modified_count:
                    log_line = f"Removed club assignment for player: {player.get('firstName')} {player.get('lastName')} {datetime.strftime(player.get('birthdate'), '%Y-%m-%d')} -> {club.club_name}"
                    print(log_line)
                    log_lines.append(log_line)
                    ishd_log_player_remove.action = IshdActionEnum.DEL_CLUB
                  else:
                    print('--- No club assignment removed')

                else:
                  raise (HTTPException(
                      status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                      detail="Failed to remove player."))
              else:
                if mode == "test":
                  print("player exists in team - do not remove")

              if ishd_log_player_remove.action is not None:
                print("--- ishd_log_player", ishd_log_player_remove)
                ishd_log_team.players.append(ishd_log_player_remove)

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
    token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> JSONResponse:
  mongodb = request.app.state.mongodb
  if token_payload.roles not in [["ADMIN"]]:
    raise HTTPException(status_code=403, detail="Not authorized")
  # get club
  club = await mongodb["clubs"].find_one({"alias": club_alias})
  if not club:
    raise HTTPException(status_code=404,
                        detail=f"Club with alias {club_alias} not found")
  players = await get_paginated_players(mongodb, q, page, club_alias)
  return JSONResponse(status_code=status.HTTP_200_OK,
                      content=jsonable_encoder(players))


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
    token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> JSONResponse:
  mongodb = request.app.state.mongodb
  if token_payload.roles not in [["ADMIN"]]:
    raise HTTPException(status_code=403, detail="Not authorized")
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
        detail=f"Team with alias {team_alias} not found in club {club_alias}")
  players = await get_paginated_players(mongodb, q, page, club_alias,
                                        team_alias)
  return JSONResponse(status_code=status.HTTP_200_OK,
                      content=jsonable_encoder(players))


# GET ALL PLAYERS
# -------------------
@router.get("/",
            response_description="Get all players",
            response_model=List[PlayerDB])
async def get_players(
    request: Request,
    page: int = 1,
    q: Optional[str] = None,
    token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> JSONResponse:
  mongodb = request.app.state.mongodb
  if token_payload.roles not in [["ADMIN"]]:
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                        detail="Not authorized")
  #RESULTS_PER_PAGE = int(os.environ.get("RESULTS_PER_PAGE", 25))

  players = await get_paginated_players(mongodb, q, page)
  return JSONResponse(status_code=status.HTTP_200_OK,
                      content=jsonable_encoder(players))


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
    token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> JSONResponse:
  mongodb = request.app.state.mongodb
  if token_payload.roles not in [["ADMIN"]]:
    raise HTTPException(status_code=403, detail="Not authorized")

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
                      legacyId=legacyId)
  player = my_jsonable_encoder(player)
  player['create_date'] = datetime.now().replace(microsecond=0)

  #player['birthdate'] = datetime.strptime(player['birthdate'], '%Y-%m-%d')
  try:
    #print("new player", player)
    new_player = await mongodb["players"].insert_one(player)
    created_player = await mongodb["players"].find_one(
        {"_id": new_player.inserted_id})
    if created_player:
      return JSONResponse(status_code=status.HTTP_201_CREATED,
                          content=jsonable_encoder(PlayerDB(**created_player)))
    else:
      raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
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
                        fullFaceReq: Optional[bool] = Form(None),
                        source: Optional[SourceEnum] = Form(None),
                        token_payload: TokenPayload = Depends(
                            auth.auth_wrapper)):
  mongodb = request.app.state.mongodb
  if token_payload.roles not in [["ADMIN"]]:
    raise HTTPException(status_code=403, detail="Not authorized")

  existing_player = await mongodb["players"].find_one({"_id": id})
  if not existing_player:
    raise HTTPException(status_code=404,
                        detail=f"Player with id {id} not found")

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
                             fullFaceReq=fullFaceReq,
                             source=source).dict(exclude_none=True)

  player_data.pop('id', None)
  print("player_data", player_data)

  player_to_update: Dict[str, Optional[str]] = {}
  for field, value in player_data.items():
    if value is not None and existing_player.get(field) != value:
      player_to_update[field] = value
      #setattr(existing_player, field, value)

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
                          content=jsonable_encoder(PlayerDB(**updated_player)))
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
  if token_payload.roles not in [["ADMIN"]]:
    raise HTTPException(status_code=403, detail="Not authorized")

  delete_result = await mongodb["players"].delete_one({"_id": id})
  if delete_result.deleted_count == 1:
    return Response(status_code=status.HTTP_204_NO_CONTENT)
  else:
    raise HTTPException(status_code=404,
                        detail=f"Player with ID {id} not found.")
