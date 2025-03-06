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
      club_alias = row['clubAlias']
      team_alias = row['teamAlias']
      first_name = row['firstName']
      last_name = row['lastName']
      year_of_birth = int(row['yearOfBirth'])
      date_string = row.get('modifiedDate', '')
      modify_date = None
      if date_string:
        modify_date = datetime.strptime(date_string, '%Y-%m-%dT%H:%M:%S')

      # get player from db#
      query = {
          "firstName": first_name,
          "lastName": last_name,
          "birthdate": {
              "$gte": datetime(year_of_birth, 1, 1),
              "$lte": datetime(year_of_birth, 12, 31, 23, 59, 59)
          }
      }
      players_cursor = db.players.find(query)

      # Convert cursor to list
      existing_players = list(players_cursor)

      # Use count_documents method to get the number of matching documents
      count = db.players.count_documents(query)
      if count > 1:
        print(
            f"More than one player found for {first_name} {last_name} ({year_of_birth})"
        )

      if not existing_players:
        print(
            f"Player {first_name} {last_name} ({year_of_birth}) not found in db"
        )
        continue
      else:
        # Use the first matching player
        player = PlayerDB(**existing_players[0])

      # get club from db
      club_res = db.clubs.find_one({"alias": club_alias})
      if club_res is None:
        print(f"Club {club_alias} not found in db")
        continue
      else:
        club = ClubDB(**club_res)

      # get team from API endpoint
      team_url = f"{BASE_URL}/clubs/{club_alias}/teams/{team_alias}"
      team_response = requests.get(team_url, headers=headers)
      if team_response.status_code != 200:
        print(f"Error getting team {team_alias}")
        continue
      else:
        team_db = TeamDB(**team_response.json())

      # Ensure that 'assigned_teams_input' is initialized as a list
      assigned_clubs = []

      # Iterate over the current assignments and ensure proper initialization
      for assignment in player.assignedTeams or []:
        assigned_team_object = AssignedClubs(**assignment.dict())
        assigned_clubs.append(assigned_team_object)

      #print(f"Assigning {len(assigned_clubs)} teams to {first_name} {last_name}")
      #if len(assigned_clubs) == 0:
      #  print(f"{first_name};{last_name};({year_of_birth});No assignments found")
      #  continue
      # Print current assignments, returning clubName and teams.teamName only
      club_team_list = []
      for assignment in assigned_clubs:
        club_name = assignment.clubName
        for team in assignment.teams:
          team_name = team.teamName
          club_team_list.append(f"{club_name} ({team_name})")

      # Print all club-team assignments in one line
      print(f"{first_name};{last_name};({year_of_birth});",
            ";".join(club_team_list))
      # Create instances of TeamInput
      new_team_assignemnt = AssignedTeams(
          teamId=str(team_db.id),
          passNo=row.get('passNo', ''),
          active=True,
          source=SourceEnum.BISHL,
          modifyDate=modify_date,
          teamName=team_db.name,  # Assuming team_db has an attribute `name`
          teamAlias=team_db.alias,  # Using the `team_alias` from the CSV row
          teamIshdId=team_db.ishdId if team_db.ishdId is not None else
          ""  # Provide a default empty string if None
      )

      # Create new team assignment
      new_club_assignment = AssignedClubs(
          clubId=str(club.id),
          clubName=club.name,  # Assuming `club` object has an attribute `name`
          clubAlias=club_alias,  # Using club alias from the CSV
          clubIshdId=club.ishdId
          if club.ishdId is not None else 0,  # Provide a default value of 0
          teams=[
              new_team_assignemnt
          ]  # Correct the input to use the correct team assignment variable
      )

      # Check if club already exists in assigned_teams_input
      existing_club = next(
          (x for x in assigned_clubs if x.clubId == str(club.id)), None)

      if existing_club:
        # Club exists, add new team to existing club's teams
        existing_club.teams.append(new_team_assignemnt)
      else:
        # Club doesn't exist, append new club assignment
        assigned_clubs.append(new_club_assignment)

      try:
        from pprint import pprint
        print(f"Updating player ... {first_name} {last_name} (ID: {player.id})")
        assignments_data = [x.dict() for x in assigned_clubs]
        pprint(assignments_data, indent=4)
        
        # Perform the update
        update_result = db.players.update_one(
            {"_id": player.id},
            {"$set": {
                "assignedTeams": assignments_data
            }})
        
        # Check update operation result
        if update_result.matched_count == 0:
          print(f"ERROR: No player matched with ID {player.id}")
          exit(1)
        
        if update_result.modified_count == 0:
          print(f"WARNING: Player found but no modifications made. Data might be identical.")
        
        # Verify the update by fetching the player again
        updated_player = db.players.find_one({"_id": player.id})
        if updated_player:
          actual_teams_count = len(updated_player.get("assignedTeams", []))
          expected_teams_count = len(assignments_data)
          
          print(f"Update stats: Found={update_result.matched_count}, Modified={update_result.modified_count}")
          print(f"Team counts: Expected={expected_teams_count}, Actual={actual_teams_count}")
          
          if actual_teams_count == expected_teams_count:
            print(f"✅ Successfully updated Player: {first_name} {last_name}")
          else:
            print(f"⚠️ Team count mismatch after update for {first_name} {last_name}")
            print(f"Saved teams count: {actual_teams_count}, Expected: {expected_teams_count}")
        else:
          print(f"ERROR: Couldn't retrieve player after update")
          exit(1)

        if not args.importAll:
          print("--importAll flag not set, exiting.")
          exit()

      except Exception as e:
        print(f"An error occurred while updating the database: {e}")
        print(f"Exception type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        exit(1)

except Exception as e:
  print(f"An error occurred: {e}")
  exit(1)
