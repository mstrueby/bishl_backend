#!/usr/bin/env python
import csv
import os
import certifi
import argparse
import requests
from pymongo import MongoClient
from models.players import AssignedClubs, PlayerDB, AssignedTeamsInput, TeamInput, SourceEnum
from models.clubs import ClubDB
from datetime import datetime

# Set up argument parser
parser = argparse.ArgumentParser(description='Manage teams.')
parser.add_argument('--importAll',
                    action='store_true',
                    help='Import all teams.')
parser.add_argument('--prod', action='store_true', help='Import into production.')
args = parser.parse_args()

# Get environment variables
filename = "data/data_new_team_assignments.csv"
if args.prod:
  BASE_URL = os.environ['BE_API_URL_PROD']
else:
  BASE_URL = os.environ['BE_API_URL']
print("BASE_URL: ", BASE_URL)

# MongoDB setup
client = MongoClient(os.environ['DB_URL'], tlsCAFile=certifi.where())
db = client[os.environ['DB_NAME']]

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
      club_alias=row['clubAlias']
      first_name=row['firstName']
      last_name=row['lastName']
      year_of_birth=row['yearOfBirth']
      date_string = row.get('modifyDate', '')
      modify_date = None
      if date_string:
          modify_date = datetime.strptime(date_string, '%Y-%m-%dT%H:%M:%S%z')

      # get player from db#
#      existing_player = db.players.find_one({"firstName": first_name, "lastName": last_name, "birthdate": {"$regex": f"^{year_of_birth}"}})
      query = {"firstName": first_name, "lastName": last_name}
      existing_player = db.players.find(query)

      # Use count_documents method to get the number of matching documents
      count = db.players.count_documents(query)
      if count > 1:
        print(f"More than one player found for {first_name} {last_name} ({year_of_birth})")

      if existing_player is None:
        print(f"Player {first_name} {last_name} ({year_of_birth}) not found in db")
        continue
      else:
        player = PlayerDB(**existing_player)

      # get club from db
      club_res = db.clubs.find_one({"alias": club_alias})
      if club_res is None:
        print(f"Club {club_alias} not found in db")
        continue
      else:
        club = ClubDB(**club_res)

      # Ensure that 'assigned_teams_input' is initialized as a list
      assigned_clubs = []

      # Iterate over the current assignments and ensure proper initialization
      for assignment in player.assignedTeams or []:
          if isinstance(assignment, dict):
              assigned_team_object = AssignedClubs(**assignment)
              assigned_clubs.append(assigned_team_object)

      # Create instances of TeamInput
      team_input = TeamInput(
          teamId=row.get('teamId', ''),
          passNo=row.get('passNo', ''),
          active=True, 
          source=SourceEnum.BISHL,
          modifyDate=modify_date
      )

      # Create new team assignment
      new_club_assignment = AssignedTeamsInput(
          clubId=str(club.id),
          teams=[team_input]
      )

      # Check if club already exists in assigned_teams_input
      existing_club = next(
          (x for x in assigned_clubs if x.clubId == str(club.id)), None)

      if existing_club:
          # Club exists, add new team to existing club's teams
          existing_club.teams.append(team_input)
      else:
          # Club doesn't exist, append new club assignment
          assigned_clubs.append(new_club_assignment)

      try:
          # db.players.update_one({"_id": player.id}, {"$set": {"assignedTeams": [x.dict() for x in assigned_clubs]}})
          print("DUMMY - Updating player ... ", first_name, last_name, [x.dict() for x in assigned_clubs])
      except Exception as e:
          print(f"An error occurred while updating the database: {e}")
          exit(1)

except Exception as e:
  print(f"An error occurred: {e}")
  exit(1)
