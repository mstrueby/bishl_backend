#!/usr/bin/env python
import csv
import os
import certifi
import argparse
import requests
from pymongo import MongoClient
from models.players import AssignedTeams, AssignedClubs, PlayerDB, AssignedTeamsInput, TeamInput, SourceEnum
from models.clubs import ClubDB, TeamDB
from datetime import datetime

# Set up argument parser
parser = argparse.ArgumentParser(description='Manage teams.')
parser.add_argument('--importAll',
  action='store_true',
  help='Import all teams.')
parser.add_argument('--prod',
  action='store_true',
  help='Import into production.')
args = parser.parse_args()

# Get environment variables
filename = "data/data_new_team_assignments.csv"
if args.prod:
  BASE_URL = os.environ['BE_API_URL_PROD']
  DB_URL = os.environ['DB_URL_PROD']
  DB_NAME = 'bishl'
else:
  BASE_URL = os.environ['BE_API_URL']
  DB_URL = os.environ['DB_URL']
  DB_NAME = 'bishl_dev'
print("BASE_URL: ", BASE_URL)
print("DB_URL: ", DB_URL)
print("DB_NAME", DB_NAME)

# MongoDB setup
client = MongoClient(DB_URL, tlsCAFile=certifi.where())
db = client[DB_NAME]
db_players = db['players']

# Login setup
login_url = f"{BASE_URL}/users/login"
login_data = {
    "email": os.environ['SYS_ADMIN_EMAIL'],
    "password": os.environ['SYS_ADMIN_PASSWORD']
}

try:
  #login user
  login_response = requests.post(login_url, json=login_data)
  if login_response.status_code != 200:
    print(f"Error logging in: {login_response.text}")
    exit(1)

  token = login_response.json()['token']
  headers = {"Authorization": f"Bearer {token}"}

  with open(filename, encoding='utf-8') as f:
    reader = csv.DictReader(f,
          delimiter=';',
          quotechar='"',
          doublequote=True,
          skipinitialspace=True)
    for row in reader:
      club_alias = row['clubAlias']
      team_alias = row['teamAlias']
      first_name = row['firstName']
      last_name = row['lastName']
      birthdate = datetime.strptime(row['birthdate'], '%d.%m.%Y')

      # check player in db
      query = {
        "firstName": first_name,
        "lastName": last_name,
        "birthdate": birthdate
      }
      exisiting_player = db_players.find_one(query)

      if exisiting_player:
        player = PlayerDB(**exisiting_player)
        print(f"Player {first_name} {last_name} already exists")
        # check assigned teams of player if a team with source ISHD already exists by looping through assignedTeams[].teams
        if player.assignedTeams is None:
          player.assignedTeams = []
        for assigned_club in player.assignedTeams:
          for team in assigned_club.teams:
            if team.source == SourceEnum.ISHD:
              print(f"Player {first_name} {last_name} already has an  ISHD-Pass! --> ignored")
              exit(1)
      
      else:
        player = PlayerDB(
          firstName=first_name,
          lastName=last_name,
          displayFirstName=first_name,
          displayLastName=last_name,
          birthdate=birthdate
        )