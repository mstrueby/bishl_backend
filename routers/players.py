from fastapi import APIRouter, HTTPException, Form, UploadFile, File, Request, Body, Depends, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
import json
from typing import List
from utils import configure_cloudinary, my_jsonable_encoder
from pymongo import MongoClient
from bson import ObjectId
from models.players import PlayerBase, PlayerDB, PlayerUpdate
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

  async for club in request.app.mongodb['clubs'].aggregate([{
      "$match": {
        "active": True,
        "ishdId": {
          "$ne": None
        },
        "teams.ishdId": {
          "$ne": None
        },
        "teams": {
          "$ne": []
        }
      }
  }, {
      "$project": {
        "ishdId": 1,
        "name": 1,
        "_id": 0,
        "teams.ishdId": 1
      }
  }]):
    ishd_teams.append(
      IshdTeams(club['ishdId'], club['name'],
                [team['ishdId'] for team in club['teams']]))

  api_urls = []
  base_url_str = str(ISHD_API_URL)

  for club in ishd_teams:
    for team_id in club.team_ishd_ids:
      club_ishd_id_str = urllib.parse.quote(str(club.club_ishd_id))
      team_id_str = urllib.parse.quote(str(team_id))

      # Construct the URL with encoded components
      api_url = f"{base_url_str}/clubs/{club_ishd_id_str}/teams/{team_id_str}"
      api_urls.append(api_url)

  #api_urls = ['https://www.ishd.de/api/licenses/clubs/103/teams/1.%20Herren']
  #print("API URLs:", api_urls)

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
  players = []
  async for player in request.app.mongodb['players'].find({}, {
      'firstname': 1,
      'lastname': 1,
      'birthdate': 1
  }):
    players.append(player)

  ishd_data = []
  async with aiohttp.ClientSession() as session:
    # loop through teaam API URLs
    for api_url in api_urls:
      print("process URL: ", api_url)
      async with session.get(api_url, headers=headers) as response:
        if response.status == 200:
          data = await response.json()
          #print("data", data)
          # loop through players array
          for player in data['players']:
            # check if player already exists in players array
            player_exists = False
            for existing_player in players:
              if (existing_player['firstname'] == player['first_name']
                  and existing_player['lastname'] == player['last_name'] and
                  datetime.strftime(existing_player['birthdate'],
                                    '%Y-%m-%d') == player['date_of_birth']):
                player_exists = True
                break
            if not player_exists:
              # insert player into database
              new_player = PlayerBase(
                firstname=player['first_name'],
                lastname=player['last_name'],
                birthdate=datetime.strptime(player['date_of_birth'],
                                            '%Y-%m-%d'),
                nationality=player['nationality']
                if 'nationality' in player else None,
              )
              new_player_dict = jsonable_encoder(new_player)
              new_player_dict['birthdate'] = datetime.strptime(
                player['date_of_birth'], '%Y-%m-%d')
              new_player_dict['download_date'] = download_date
              new_player_dict['modify_date'] = datetime.strptime(
                player['last_modification'], '%Y-%m-%d %H:%M:%S')
              result = await request.app.mongodb["players"].insert_one(
                new_player_dict)
              if result.inserted_id:
                print("Inserted player:", new_player_dict.get('firstname'),
                      new_player_dict.get('lastname'),
                      new_player_dict.get('birthdate'))
              else:
                raise (HTTPException(
                  status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                  detail="Failed to insert player."))
            else:
              print(
                f"Player already exists: {player.get('first_name')} {player.get('last_name')}, {player.get('date_of_birth')}"
              )

          ishd_data.append(data)
        elif response.status == 404:
          print(f"API URL {api_url} returned a 404 status code.")
        else:
          raise HTTPException(status_code=response.status,
                              detail=f"Error fetching data from {api_url}")
  await session.close()

  current_timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
  file_name = f'ishd_data_{current_timestamp}.json'
  with open(file_name, 'w') as json_file:
    json.dump(ishd_data, json_file, indent=2)

  return Response(
    status_code=status.HTTP_200_OK,
    content=json.dumps(
      f"ISHD data processed successfully, see filename {file_name}"))
