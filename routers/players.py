from fastapi import APIRouter, HTTPException, Form, UploadFile, File, Request, Body, Depends, status, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
import json
from typing import List, Any, Coroutine
from utils import configure_cloudinary, my_jsonable_encoder
from pymongo import MongoClient
from bson import ObjectId
from models.players import PlayerBase, PlayerDB, PlayerUpdate, PlayerTeams, PlayerClubs, AssignmentInput
from authentication import AuthHandler, TokenPayload
from datetime import datetime, date
import os
import urllib.parse
import aiohttp, base64, asyncio

router = APIRouter()
auth = AuthHandler()


# PROCESS ISHD DATA
# ----------------------
@router.get(
  "/process_ishd_data",
  response_description="Process ISHD player data to BISHL-Application")
async def process_ishd_data(request: Request):

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
  create_date = datetime.utcnow().replace(microsecond=0)

  async for club in request.app.mongodb['clubs'].aggregate([
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
  async for player in request.app.mongodb['players'].find({}, {
      'firstname': 1,
      'lastname': 1,
      'birthdate': 1,
      'assignments': 1,
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
  log_lines = []
  current_timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
  file_name = f'ishd_processing_{current_timestamp}.log'

  async with aiohttp.ClientSession() as session:
    # loop through teaam API URLs
    #for api_url in api_urls:
    for club in ishd_teams:

      log_line = f"Processing club {club.club_name} (IshdId: {club.club_ishd_id})"
      print(log_line)
      log_lines.append(log_line)

      for team in club.teams:
        #print("team", team)
        club_ishd_id_str = urllib.parse.quote(str(club.club_ishd_id))
        team_id_str = urllib.parse.quote(str(team['ishdId']))
        api_url = f"{base_url_str}/clubs/{club_ishd_id_str}/teams/{team_id_str}"

        log_line = f"Processing team (URL): {club.club_name} / {team['ishdId']} ({api_url})"
        print(log_line)
        #log_lines.append(log_line)
        async with session.get(api_url, headers=headers) as response:
          if response.status == 200:
            data = await response.json()
            #print("data", data)
            # loop through players array
            for player in data['players']:
              #if player['first_name'] != "Anabel":
              #  break
              # build assignments object
              player_team = PlayerTeams(team_id=team['_id'],
                                        team_name=team['name'],
                                        team_alias=team['alias'],
                                        team_ishd_id=team['ishdId'],
                                        pass_no=player['license_number'],
                                        source='ISHD',
                                        modify_date=datetime.strptime(
                                          player['last_modification'],
                                          '%Y-%m-%d %H:%M:%S'))
              player_club = PlayerClubs(club_id=club.club_id,
                                        club_name=club.club_name,
                                        club_alias=club.club_alias,
                                        club_ishd_id=club.club_ishd_id,
                                        teams=[player_team])
              # check if player already exists in existing_players array
              player_exists = False
              for existing_player in existing_players:
                if (existing_player['firstname'] == player['first_name']
                    and existing_player['lastname'] == player['last_name'] and
                    datetime.strftime(existing_player['birthdate'],
                                      '%Y-%m-%d') == player['date_of_birth']):
                  player_exists = True
                  break
              if not player_exists:
                # NEW PLAYER
                # FIRST: construct Player object w/o team assignments
                new_player = PlayerBase(
                  firstname=player['first_name'],
                  lastname=player['last_name'],
                  birthdate=datetime.strptime(player['date_of_birth'],
                                              '%Y-%m-%d'),
                  nationality=player['nationality']
                  if 'nationality' in player else None,
                  assignments=[player_club],
                  full_face_req=True
                  if player.get('full_face_req') == 'true' else False,
                  source='ISHD')
                new_player_dict = my_jsonable_encoder(new_player)
                new_player_dict['birthdate'] = datetime.strptime(
                  player['date_of_birth'], '%Y-%m-%d')
                new_player_dict['create_date'] = create_date

                # add player to exisiting players array
                existing_players.append(new_player_dict)
                #print("existing_players", existing_players)

                # insert player into database
                result = await request.app.mongodb["players"].insert_one(
                  new_player_dict)
                if result.inserted_id:
                  log_line = f"Inserted player: {new_player_dict.get('firstname')} {new_player_dict.get('lastname')} {datetime.strftime(new_player_dict.get('birthdate'), '%Y-%m-%d')} -> {player_club.club_name} / {player_team.team_name}"
                  print(log_line)
                  log_lines.append(log_line)

                else:
                  raise (HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to insert player."))

              else:
                # player already exists
                # Check if team assignment exists for player
                club_assignment_exists = False
                for club_assignment in existing_player.get('assignments', []):
                  #print("club_assignment", club_assignment)
                  if club_assignment['club_name'] == club.club_name:
                    #print("club_assignment club_name",
                    #      club_assignment['club_name'])
                    club_assignment_exists = True
                    # club already exists
                    team_assignment_exists = False
                    for team_assignment in club_assignment.get('teams', []):
                      if team_assignment['team_id'] == team['_id']:
                        team_assignment_exists = True
                        break
                    if not team_assignment_exists:
                      # team assignment does not exist
                      # add team assignment to players existing club assignment
                      club_assignment.get('teams').append(player_team)
                      # update player with new team assignment
                      existing_player['assignments'] = [club_assignment]
                      # update player in database
                      result = await request.app.mongodb["players"].update_one(
                        {"_id": existing_player['_id']}, {
                          "$set": {
                            "assignments":
                            jsonable_encoder(existing_player['assignments'])
                          }
                        })
                      if result.modified_count:
                        log_line = f"Updated team assignment for: {existing_player.get('firstname')} {existing_player.get('lastname')} {datetime.strftime(existing_player.get('birthdate'), '%Y-%m-%d')} -> {club.club_name} / {team['ishdId']}"
                        print(log_line)
                        log_lines.append(log_line)

                      else:
                        raise (HTTPException(
                          status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                          detail="Failed to update player."))
                    break
                if not club_assignment_exists:
                  # club assignment does not exist
                  # add club assignment to player
                  existing_player['assignments'].append(player_club)
                  # update player with new club assignment
                  result = await request.app.mongodb["players"].update_one(
                    {"_id": existing_player['_id']}, {
                      "$set": {
                        "assignments":
                        jsonable_encoder(existing_player['assignments'])
                      }
                    })
                  if result.modified_count:
                    log_line = f"New club assignment for: {existing_player.get('firstname')} {existing_player.get('lastname')} {datetime.strftime(existing_player.get('birthdate'), '%Y-%m-%d')} -> {club.club_name} / {team.get('ishdId')}"
                    print(log_line)
                    log_lines.append(log_line)

                  else:
                    raise (HTTPException(
                      status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                      detail="Failed to update player."))

            ishd_data.append(data)
          elif response.status == 404:
            log_line = f"API URL {api_url} returned a 404 status code."
            print(log_line)
            log_lines.append(log_line)

          else:
            raise HTTPException(status_code=response.status,
                                detail=f"Error fetching data from {api_url}")
  await session.close()

  with open(file_name, 'w') as logfile:
    logfile.write('\n'.join(log_lines))

  return JSONResponse(
    status_code=status.HTTP_200_OK,
    content={
      "message": "ISHD data processed successfully",
      "logs": log_lines,
      #"data": ishd_data
    })


# Helper function to search players
async def get_paginated_players(request,
                                q,
                                page,
                                club_alias=None,
                                team_alias=None):
  RESULTS_PER_PAGE = 25
  skip = (page - 1) * RESULTS_PER_PAGE
  query = {"$and": []}
  if club_alias:
    query["$and"].append({"assignments.club_alias": club_alias})
  if team_alias:
    query["$and"].append({"assignments.teams.team_alias": team_alias})
  if q and len(q) >= 3:
    query["$and"].append({
      "$or": [{
        "firstname": {
          "$regex": f".*{q}.*",
          "$options": "i"
        }
      }, {
        "lastname": {
          "$regex": f".*{q}.*",
          "$options": "i"
        }
      }, {
        "assignments.teams.pass_no": {
          "$regex": f".*{q}.*",
          "$options": "i"
        }
      }]
    })
  print("query", query)
  players = await request.app.mongodb["players"].find(query).sort(
    "firstname", 1).skip(skip).limit(RESULTS_PER_PAGE).to_list(None)
  return [PlayerDB(**raw_player) for raw_player in players]


# GET ALL PLAYERS FOR ONE CLUB
# --------
@router.get("/clubs/{club_alias}",
            response_description="Get all players for a club",
            response_model=List[PlayerDB])
async def get_players_for_club(
  request: Request,
  club_alias: str,
  page: int = 1,
  q: str = None,
  token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> List[PlayerDB]:
  if token_payload.roles not in [["ADMIN"]]:
    raise HTTPException(status_code=403, detail="Not authorized")
  # get club
  club = await request.app.mongodb["clubs"].find_one({"alias": club_alias})
  if not club:
    raise HTTPException(status_code=404,
                        detail=f"Club with alias {club_alias} not found")
  players = await get_paginated_players(request, q, page, club_alias)
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
  q: str = None,
  token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> List[PlayerDB]:
  if token_payload.roles not in [["ADMIN"]]:
    raise HTTPException(status_code=403, detail="Not authorized")
  # get club
  club = await request.app.mongodb["clubs"].find_one({"alias": club_alias})
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
  players = await get_paginated_players(request, q, page, club_alias,
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
  q: str = None,
  token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> List[PlayerDB]:
  if token_payload.roles not in [["ADMIN"]]:
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                        detail="Not authorized")
  #RESULTS_PER_PAGE = int(os.environ.get("RESULTS_PER_PAGE", 25))

  players = await get_paginated_players(request, q, page)
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
) -> PlayerDB:
  player = await request.app.mongodb["players"].find_one({"_id": id})
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
async def create_player(request: Request,
                        firstname: str = Body(...),
                        lastname: str = Body(...),
                        birthdate: datetime = Body(...),
                        nationality: str = Body(None),
                        assignments: List[AssignmentInput] = Body([]),
                        full_face_req: bool = Body(False),
                        source: str = Body('BISHL'),
                        token_payload: TokenPayload = Depends(
                          auth.auth_wrapper)):
  if token_payload.roles not in [["ADMIN"]]:
    raise HTTPException(status_code=403, detail="Not authorized")

  player_exists = await request.app.mongodb["players"].find_one({
    "firstname":
    firstname,
    "lastname":
    lastname,
    "birthdate":
    birthdate
  })
  if player_exists:
    raise HTTPException(
      status_code=400,
      detail=
      f"Player with name {firstname} {lastname} and birthdate {birthdate.strftime('%d.%m.%Y')} already exists."
    )

  assignments_dict = []
  print("assignment_input", assignments)
  for club_to_assign in assignments:
    club_exists = await request.app.mongodb["clubs"].find_one(
      {"_id": club_to_assign.club_id})
    if not club_exists:
      raise HTTPException(
        status_code=400,
        detail=f"Club with id {club_to_assign.club_id} does not exist.")
    teams = []
    for team_to_assign in club_to_assign.teams:
      print("team_to_assign", club_exists['name'], '/', team_to_assign)
      team = next((team for team in club_exists['teams']
                   if team['_id'] == team_to_assign['team_id']), None)
      if not team:
        raise HTTPException(
          status_code=400,
          detail=
          f"Team with id {team_to_assign['team_id']} does not exist in club {club_to_assign.club_id}."
        )
      else:
        # build teams object
        #print("team", team)
        teams.append({
          "team_id": team['_id'],
          "team_name": team['name'],
          "team_alias": team['alias'],
          "team_ishd_id": team['ishdId'],
          "pass_no": team_to_assign['pass_no'],
          "source": source,
          "modify_date": datetime.utcnow().replace(microsecond=0),
        })
    assignments_dict.append({
      "club_id": club_to_assign.club_id,
      "club_name": club_exists['name'],
      "club_alias": club_exists['alias'],
      "club_ishd_id": club_exists['ishdId'],
      "teams": teams,
    })

  player = PlayerBase(firstname=firstname,
                      lastname=lastname,
                      birthdate=birthdate,
                      nationality=nationality,
                      assignments=assignments_dict,
                      full_face_req=full_face_req,
                      source=source)
  player = my_jsonable_encoder(player)
  player['create_date'] = datetime.utcnow().replace(microsecond=0)

  #player['birthdate'] = datetime.strptime(player['birthdate'], '%Y-%m-%d')
  try:
    #print("new player", player)
    new_player = await request.app.mongodb["players"].insert_one(player)
    created_player = await request.app.mongodb["players"].find_one(
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


# SEARCH PLAYERS by Name or PassNo
# ----------------------------------------
@router.get("/search",
            response_description="Search players",
            response_model=List[PlayerDB])
async def search_players(
  request: Request, q: str = Query(..., min_length=3)) -> List[PlayerDB]:
  search_query = {
    "$or": [
      {
        "firstname": {
          "$regex": f".*{q}.*",
          "$options": "i"
        }
      },
      {
        "lastname": {
          "$regex": f".*{q}.*",
          "$options": "i"
        }
      },
    ]
  }
  cursor = request.app.mongodb["players"].find(search_query).sort(
    "firstname", 1)
  return JSONResponse(status_code=status.HTTP_200_OK,
                      content=jsonable_encoder(cursor))


# DELETE PLAYER
# ----------------------
@router.delete("/{id}", response_description="Delete a player by ID")
async def delete_player(request: Request,
                        id: str,
                        token_payload: TokenPayload = Depends(
                          auth.auth_wrapper)):
  if token_payload.roles not in [["ADMIN"]]:
    raise HTTPException(status_code=403, detail="Not authorized")

  delete_result = await request.app.mongodb["players"].delete_one({"_id": id})
  if delete_result.deleted_count == 1:
    return Response(status_code=status.HTTP_204_NO_CONTENT)
  else:
    raise HTTPException(status_code=404,
                        detail=f"Player with ID {id} not found.")
