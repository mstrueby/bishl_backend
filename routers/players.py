from fastapi import APIRouter, HTTPException, Form, UploadFile, File, Request, Body, Depends, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
import json
from typing import List
from utils import configure_cloudinary, my_jsonable_encoder
from pymongo import MongoClient
from bson import ObjectId
from models.players import PlayerBase, PlayerDB, PlayerUpdate, PlayerTeams, PlayerClubs
from authentication import AuthHandler, TokenPayload
from datetime import datetime, date
import os
import urllib.parse
import aiohttp, base64, asyncio

router = APIRouter()
auth = AuthHandler()


@router.post("/",
             response_description="Add new player",
             response_model=PlayerDB)
async def create_player(request: Request, player: PlayerBase = Body(...)):
  player_exists = await request.app.mongodb["players"].find_one({
    "firstname":
    player.firstname,
    "lastname":
    player.lastname,
    "birthdate":
    player.birthdate
  })
  if player_exists:
    raise HTTPException(
      status_code=400,
      detail=
      f"Player with name {player.firstname} {player.lastname} and birthdate {player.birthdate.strftime('%d.%m.%Y')} already exists."
    )
  player = my_jsonable_encoder(player)

  #player['birthdate'] = datetime.strptime(player['birthdate'], '%Y-%m-%d')
  player['modified_date'] = datetime.utcnow().replace(microsecond=0)
  player['download_date'] = None
  try:
    print("player", player)
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


@router.get(
  "/process_ishd_data",
  response_description="Process ISHD player data to BISHL-Application")
async def process_ishd_data(request: Request):

  ISHD_API_URL = os.environ.get("ISHD_API_URL")
  ISHD_API_USER = os.environ.get("ISHD_API_USER")
  ISHD_API_PASS = os.environ.get("ISHD_API_PASS")

  class IshdTeams:

    def __init__(self, club_ishd_id, club_name, team_ishd_ids):
      self.club_ishd_id = club_ishd_id
      self.club_name = club_name
      self.team_ishd_ids = team_ishd_ids

  ishd_teams = []
  download_date = datetime.utcnow().replace(microsecond=0)

  async for club in request.app.mongodb['clubs'].aggregate([
    {
      "$match": {
        "active": True,
        "ishdId": 143,
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
        "name": 1,
        "_id": 0,
        "teams.ishdId": 1
      }
    }
  ]):
    ishd_teams.append(
      IshdTeams(club['ishdId'], club['name'],
                [team['ishdId'] for team in club['teams']]))

  # get exisiting players
  existing_players = []
  async for player in request.app.mongodb['players'].find(
    {}, {
      'firstname': 1,
      'lastname': 1,
      'birthdate': 1,
      'team_assignments': 1,
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

      for team_id in club.team_ishd_ids:
        club_ishd_id_str = urllib.parse.quote(str(club.club_ishd_id))
        team_id_str = urllib.parse.quote(str(team_id))
        api_url = f"{base_url_str}/clubs/{club_ishd_id_str}/teams/{team_id_str}"

        log_line = f"Processing team (URL): {club.club_name} / {team_id} ({api_url})"
        print(log_line)
        log_lines.append(log_line)

        async with session.get(api_url, headers=headers) as response:
          if response.status == 200:
            data = await response.json()
            #print("data", data)
            # loop through players array
            player_team = PlayerTeams(name=team_id)
            player_club = PlayerClubs(club_name=club.club_name,
                                      club_ishd_id=club.club_ishd_id,
                                      teams=[player_team])
            for player in data['players']:
              # check if player already exists in players array
              player_exists = False
              for existing_player in existing_players:
                if (existing_player['firstname'] == player['first_name']
                    and existing_player['lastname'] == player['last_name'] and
                    datetime.strftime(existing_player['birthdate'],
                                      '%Y-%m-%d') == player['date_of_birth']):
                  player_exists = True
                  break
              if not player_exists:
                # FIRST: construct Player object w/o team assignments
                new_player = PlayerBase(firstname=player['first_name'],
                                        lastname=player['last_name'],
                                        birthdate=datetime.strptime(
                                          player['date_of_birth'], '%Y-%m-%d'),
                                        nationality=player['nationality']
                                        if 'nationality' in player else None,
                                        team_assignments=[player_club])
                new_player_dict = jsonable_encoder(new_player)
                new_player_dict['birthdate'] = datetime.strptime(
                  player['date_of_birth'], '%Y-%m-%d')
                new_player_dict['download_date'] = download_date
                new_player_dict['modify_date'] = datetime.strptime(
                  player['last_modification'], '%Y-%m-%d %H:%M:%S')

                # add player to exisiting players array
                existing_players.append(new_player_dict)
                # insert player into database
                result = await request.app.mongodb["players"].insert_one(
                  new_player_dict)
                if result.inserted_id:
                  log_line = f"Inserted player: {new_player_dict.get('firstname')} {new_player_dict.get('lastname')} {datetime.strftime(new_player_dict.get('birthdate'), '%Y-%m-%d')}"
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
                for club_assignment in existing_player.get(
                    'team_assignments', []):
                  if club_assignment['club_name'] == club.club_name:
                    club_assignment_exists = True
                    # club already exists
                    team_assignment_exists = False
                    for team_assignment in club_assignment.get('teams', []):
                      if team_assignment['name'] == team_id:
                        team_assignment_exists = True
                        break
                    if not team_assignment_exists:
                      # team assignment does not exist
                      # add team assignment to players existing club assignment
                      club_assignment.get('teams').append(player_team)
                      # update player with new team assignment
                      existing_player['team_assignments'] = [club_assignment]
                      # update player in database
                      result = await request.app.mongodb["players"].update_one(
                        {"_id": existing_player['_id']}, {
                          "$set": {
                            "team_assignments":
                            jsonable_encoder(
                              existing_player['team_assignments'])
                          }
                        })
                      if result.modified_count:
                        log_line = f"Updated team assignment for: {existing_player.get('firstname')} {existing_player.get('lastname')} {datetime.strftime(existing_player.get('birthdate'), '%Y-%m-%d')} -> {club.club_name} / {team_id}"
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
                    existing_player['team_assignments'].append(player_club)
                    # update player with new club assignment
                    result = await request.app.mongodb["players"].update_one(
                      {"_id": existing_player['_id']}, {
                        "$set": {
                          "team_assignments":
                          jsonable_encoder(existing_player['team_assignments'])
                        }
                      })
                    if result.modified_count:
                      log_line = f"Updated club assignment for: {existing_player.get('firstname')} {existing_player.get('lastname')} {datetime.strftime(existing_player.get('birthdate'), '%Y-%m-%d')} -> {club.club_name} / {team_id}"
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
