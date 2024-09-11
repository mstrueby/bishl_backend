from fastapi import APIRouter, HTTPException, Form, Request, Body, Depends, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
import json
from typing import List, Optional, Dict
from utils import my_jsonable_encoder
from models.players import PlayerBase, PlayerDB, PlayerUpdate, AssignedClubs, AssignedTeams, AssignedTeamsInput
from authentication import AuthHandler, TokenPayload
from datetime import datetime
import os
import urllib.parse
import aiohttp, base64

router = APIRouter()
auth = AuthHandler()


# Helper function to search players
async def get_paginated_players(request,
                                q,
                                page,
                                club_alias=None,
                                team_alias=None):
  RESULTS_PER_PAGE = 25
  skip = (page - 1) * RESULTS_PER_PAGE
  #query = {}
  query = {"$and": []}
  if club_alias:
    query["$and"].append({"assigned_teams.club_alias": club_alias})
  if team_alias:
    query["$and"].append({"assigned_teams.teams.team_alias": team_alias})
  #if q and len(q) >= 3:
  if q:
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
        "assigned_teams.teams.pass_no": {
          "$regex": f".*{q}.*",
          "$options": "i"
        }
      }]
    })
  print("query", query)
  players = await request.app.mongodb["players"].find(query).sort(
    "firstname", 1).skip(skip).limit(RESULTS_PER_PAGE).to_list(None)
  return [PlayerDB(**raw_player) for raw_player in players]


# PROCESS ISHD DATA
# ----------------------
@router.get(
  "/process_ishd_data",
  response_description="Process ISHD player data to BISHL-Application")
async def process_ishd_data(request: Request,
                            mode: str = None,
                            run: int = 1,
                            token_payload: TokenPayload = Depends(
                              auth.auth_wrapper)):
  if token_payload.roles not in [["ADMIN"]]:
    raise HTTPException(status_code=403, detail="Not authorized")

  log_lines = []
  # If mode is 'test', delete all documents in 'players'
  if mode == "test" and run == 1:
    await request.app.mongodb['players'].delete_many({})
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
      'assigned_teams': 1,
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

  async with aiohttp.ClientSession() as session:
    # loop through teaam API URLs
    #for api_url in api_urls:
    for club in ishd_teams:

      log_line = f"Processing club {club.club_name} (IshdId: {club.club_ishd_id})"
      print(log_line)
      log_lines.append(log_line)

      for team in club.teams:
        print("team", team)
        club_ishd_id_str = urllib.parse.quote(str(club.club_ishd_id))
        team_id_str = urllib.parse.quote(str(team['ishdId']))

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
          else:
            log_line = f"File {test_file} does not exist. Skipping..."
            #print(log_line)
            log_lines.append(log_line)
        else:
          api_url = f"{base_url_str}/clubs/{club_ishd_id_str}/teams/{team_id_str}.json"
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
        if mode == "test":
          print("data", data)
        if data:
          # loop through players array
          for player in data['players']:
            #if player['first_name'] != "Anabel":
            #  break
            # build assigned_teams object
            assigned_team = AssignedTeams(team_id=team['_id'],
                                          team_name=team['name'],
                                          team_alias=team['alias'],
                                          team_ishd_id=team['ishdId'],
                                          pass_no=player['license_number'],
                                          source='ISHD',
                                          modify_date=datetime.strptime(
                                            player['last_modification'],
                                            '%Y-%m-%d %H:%M:%S'))
            assigned_club = AssignedClubs(club_id=club.club_id,
                                          club_name=club.club_name,
                                          club_alias=club.club_alias,
                                          club_ishd_id=club.club_ishd_id,
                                          teams=[assigned_team])
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
              # FIRST: construct Player object w/o assigned_teams
              new_player = PlayerBase(
                firstname=player['first_name'],
                lastname=player['last_name'],
                birthdate=datetime.strptime(player['date_of_birth'],
                                            '%Y-%m-%d'),
                nationality=player['nationality']
                if 'nationality' in player else None,
                assigned_teams=[assigned_club],
                full_face_req=True
                if player.get('full_face_req') == 'true' else False,
                source='ISHD')
              new_player_dict = my_jsonable_encoder(new_player)
              new_player_dict['birthdate'] = datetime.strptime(
                player['date_of_birth'], '%Y-%m-%d')
              new_player_dict['create_date'] = create_date

              # add player to exisiting players array
              existing_players.append(new_player_dict)

              # insert player into database
              result = await request.app.mongodb["players"].insert_one(
                new_player_dict)
              if result.inserted_id:
                log_line = f"Inserted player: {new_player_dict.get('firstname')} {new_player_dict.get('lastname')} {datetime.strftime(new_player_dict.get('birthdate'), '%Y-%m-%d')} -> {assigned_club.club_name} / {assigned_team.team_name}"
                print(log_line)
                log_lines.append(log_line)
                if mode == "test":
                  print("new player / existing_players", existing_players)

              else:
                raise (HTTPException(
                  status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                  detail="Failed to insert player."))

            else:
              # player already exists
              # Check if team assignment exists for player
              club_assignment_exists = False
              if mode == "test":
                print("player exists / existing_players", existing_players)
              for club_assignment in existing_player.get('assigned_teams', []):
                if mode == "test":
                  print("club_assignment", club_assignment)
                if club_assignment['club_name'] == club.club_name:
                  if mode == "test":
                    print("club_assignment exists: club_name",
                          club_assignment['club_name'])
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
                    club_assignment.get('teams').append(assigned_team)
                    # update player with new team assignment
                    existing_player['assigned_teams'] = [club_assignment] + [
                      a for a in existing_player['assigned_teams']
                      if a != club_assignment
                    ]
                    if mode == "test":
                      print("add team / existing_player", existing_player)
                    # update player in database
                    result = await request.app.mongodb["players"].update_one(
                      {"_id": existing_player['_id']}, {
                        "$set": {
                          "assigned_teams":
                          jsonable_encoder(existing_player['assigned_teams'])
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
                if mode == "test":
                  print("club assignment does not exist / existing_players")
                # add club assignment to player
                existing_player['assigned_teams'].append(
                  jsonable_encoder(assigned_club))
                if mode == "test":
                  print("add club / existing_player: ", existing_player)
                # update player with new club assignment
                result = await request.app.mongodb["players"].update_one(
                  {"_id": existing_player['_id']}, {
                    "$set": {
                      "assigned_teams":
                      jsonable_encoder(existing_player['assigned_teams'])
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

          # remove player of a team (still in team loop)
          query = {"$and": []}
          query["$and"].append({"assigned_teams.club_alias": club.club_alias})
          query["$and"].append({"assigned_teams.teams.team_alias": team['alias']})
          players = await request.app.mongodb["players"].find(query).to_list(
            length=None)
          if mode == "test":
            print("removing / players:", players)
          if players:
            for player in players:
              if mode == "test":
                print("remove player ?", player)
              # remove player from team
              if not any(
                  p['first_name'] == player['firstname'] and p['last_name'] ==
                  player['lastname'] and p['date_of_birth'] ==
                  datetime.strftime(player['birthdate'], '%Y-%m-%d')
                  for p in data['players']):
                query = {"$and": []}
                query["$and"].append({"_id": player['_id']})
                query["$and"].append(
                  {"assigned_teams.club_alias": club.club_alias})
                query["$and"].append(
                  {"assigned_teams.teams.team_alias": team['alias']})
                # print("query", query)
                result = await request.app.mongodb["players"].update_one(
                  query, {
                    "$pull": {
                      "assigned_teams.$.teams": {
                        "team_alias": team['alias']
                      }
                    }
                  })
                if result.modified_count:
                  log_line = f"Removed player: {player.get('firstname')} {player.get('lastname')} {datetime.strftime(player.get('birthdate'), '%Y-%m-%d')} -> {club.club_name} / {team.get('ishdId')}"
                  print(log_line)
                  log_lines.append(log_line)

                  # After removing team assignment, if the teams array is empty, remove the club assignment
                  result = await request.app.mongodb["players"].update_one(
                    {
                      "_id": player['_id'],
                      "assigned_teams.club_ishd_id": club.club_ishd_id
                    }, {"$pull": {
                      "assigned_teams": {
                        "teams": {
                          "$size": 0
                        }
                      }
                    }})

                  if result.modified_count:
                    log_line = f"Removed club assignment for player: {player.get('firstname')} {player.get('lastname')} {datetime.strftime(player.get('birthdate'), '%Y-%m-%d')} -> {club.club_name}"
                    print(log_line)
                    log_lines.append(log_line)
                  else:
                    print('--- No club assignment removed')

                else:
                  raise (HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to remove player."))
              else:
                if mode == "test":
                  print("player exists in team - do not remove")

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
                        assigned_teams: List[AssignedTeamsInput] = Body([]),
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

  assigned_teams_dict = []
  print("assignment_input", assigned_teams)
  for club_to_assign in assigned_teams:
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
    assigned_teams_dict.append({
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
                      assigned_teams=assigned_teams_dict,
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


# UPDATE PLAYER
# ----------------------
@router.patch("/{id}",
              response_description="Update player",
              response_model=PlayerDB)
async def update_player(
  request: Request,
  id: str,
  firstname: Optional[str] = Form(None),
  lastname: str = Form(None),
  birthdate: datetime = Form(None),
  nationality: str = Form(None),
  position: Optional[str] = Form(None),
  assigned_teams: List[AssignedTeamsInput] = Form(None),
  full_face_req: bool = Form(None),
  source: str = Form(None),
  token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> PlayerDB:
  if token_payload.roles not in [["ADMIN"]]:
    raise HTTPException(status_code=403, detail="Not authorized")
  print("assigned_teams:", assigned_teams)

  existing_player = await request.app.mongodb["players"].find_one({"_id": id})
  if not existing_player:
    raise HTTPException(status_code=404,
                        detail=f"Player with id {id} not found")
  player_data = PlayerUpdate(firstname=firstname,
                             lastname=lastname,
                             birthdate=birthdate,
                             nationality=nationality,
                             position=position,
                             assigned_teams=assigned_teams,
                             full_face_req=full_face_req,
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
    return JSONResponse(status_code=status.HTTP_200_OK,
                        content=jsonable_encoder(PlayerDB(**existing_player)))

  try:
    update_result = await request.app.mongodb["players"].update_one(
      {"_id": id}, {"$set": player_to_update}, upsert=False)
    if update_result.modified_count == 1:
      updated_player = await request.app.mongodb["players"].find_one(
        {"_id": id})
      return JSONResponse(status_code=status.HTTP_200_OK,
                          content=jsonable_encoder(PlayerDB(**updated_player)))
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Failed to update player.")
  except Exception as e:
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=str(e))


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
