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
filename = "data/data_hobby_players.csv"
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
      if len(row.get('assignedTeams', [])) > 0:
        continue
      club_alias = row['clubAlias']
      team_alias = row['teamAlias']
      first_name = row['firstName']
      last_name = row['lastName']
      birthdate = datetime.strptime(row['birthdate'], '%d.%m.%Y')
      modify_date = datetime.now()

      # check player in db
      query = {
          "firstName": first_name,
          "lastName": last_name,
          "birthdate": birthdate
      }
      exisiting_player = db_players.find_one(query)

      if exisiting_player:
        player = PlayerDB(**exisiting_player)
        player_id = str(player.id)
        print(f"⚠️ Player {first_name} {last_name} already exists")
        # check assigned teams of player if a team with source ISHD already exists by looping through assignedTeams[].teams
        if player.assignedTeams is None:
          player.assignedTeams = []
        for assigned_club in player.assignedTeams:
          for team in assigned_club.teams:
            if team.source == SourceEnum.ISHD:
              print(
                  f"❌ Player {first_name} {last_name} already has an ISHD-Pass! --> not allowed!"
              )
              exit(1)
            if team.teamAlias == team_alias:
              print(
                  f"⚠️ Player {first_name} {last_name} already is assigned to {team_alias}!"
              )
              continue

      else:
        player = PlayerDB(firstName=first_name,
                          lastName=last_name,
                          displayFirstName=first_name,
                          displayLastName=last_name,
                          birthdate=birthdate)
        # create player by using post api endpoint
        player_response = requests.post(f"{BASE_URL}/players/",
                                        headers=headers,
                                        data=player.dict())
        if player_response.status_code != 201:
          print(
              f"❌ Error creating player {first_name} {last_name}: {player_response.text}"
          )
          exit(1)
        else:
          player_id = player_response.json()['_id']
          print(f"✅ Player {first_name} {last_name} created")

        # Fetch newly inserted player from the database
        inserted_player = db_players.find_one({"_id": player_id})
        if not inserted_player:
          print(f"❌ Failed to fetch newly inserted player with ID {player_id}")

      # Process assignemnt on existing or new player
      # get club from db
      club_res = db.clubs.find_one({"alias": club_alias})
      if club_res is None:
        print(f"❌ Club {club_alias} not found in db")
        exit()
      else:
        club = ClubDB(**club_res)

      # get team from API endpoint
      team_url = f"{BASE_URL}/clubs/{club_alias}/teams/{team_alias}"
      team_response = requests.get(team_url, headers=headers)
      if team_response.status_code != 200:
        print(f"❌ Error getting team {team_alias}")
        exit(1)
      else:
        team_db = TeamDB(**team_response.json())

      assigned_club = []
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
      print(f"{first_name};{last_name};({birthdate});",
            ";".join(club_team_list))
      # Create instances of TeamInput
      new_team_assignemnt = AssignedTeams(
          teamId=str(team_db.id),
          passNo=row.get('passNo', 'H-LIGA'),
          active=False,
          source=SourceEnum.BISHL,
          modifyDate=modify_date,
          teamName=team_db.name,  # Assuming team_db has an attribute `name`
          teamAlias=team_db.alias,  # Using the `team_alias` from the CSV row
          teamIshdId=team_db.ishdId if team_db.ishdId is not None else "",
          teamAgeGroup=team_db.ageGroup
          # Provide a default empty string if None
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
        # Club exists, check if team already exists in this club's teams
        existing_team = next(
            (t for t in existing_club.teams if t.teamId == str(team_db.id)),
            None)

        if existing_team:
          # Team already exists, update its properties if needed
          print(
              f"Team {team_db.name} already assigned to {first_name} {last_name} in club {club.name}"
          )
          # Update team properties if needed (e.g., passNo, active status)
          existing_team.passNo = ''
          existing_team.active = True
          existing_team.source = SourceEnum.BISHL
          existing_team.modifyDate = modify_date
        else:
          # Team doesn't exist in this club, add new team to existing club's teams
          existing_club.teams.append(new_team_assignemnt)
      else:
        # Club doesn't exist, append new club assignment
        assigned_clubs.append(new_club_assignment)

      try:
        from pprint import pprint
        print(
            f"Updating player ... {first_name} {last_name} (ID: {player.id})")
        assignments_data = [x.dict() for x in assigned_clubs]
        pprint(assignments_data, indent=4)

        # Perform the update with the correct ID format
        update_result = db.players.update_one(
            {"_id": player_id}, {"$set": {
                "assignedTeams": assignments_data,
                "managedByISHD": False
            }})

        # Check update operation result
        if update_result.matched_count == 0:
          print(f"ERROR: No player matched with ID {player_id}")
          exit(1)

        if update_result.modified_count == 0:
          print(
              f"⚠️ WARNING: Player found but no modifications made. Data might be identical."
          )
          continue

        # Verify the update by fetching the player again with the same ID format
        updated_player = db.players.find_one({"_id": player_id})
        if updated_player:
          actual_teams_count = len(updated_player.get("assignedTeams", []))
          expected_teams_count = len(assignments_data)

          print(
              f"Update stats: Found={update_result.matched_count}, Modified={update_result.modified_count}"
          )
          print(
              f"Team counts: Expected={expected_teams_count}, Actual={actual_teams_count}"
          )

          if actual_teams_count == expected_teams_count:
            print(f"✅ Successfully updated Player: {first_name} {last_name}")
          else:
            print(
                f"⚠️ Team count mismatch after update for {first_name} {last_name}"
            )
            print(
                f"Saved teams count: {actual_teams_count}, Expected: {expected_teams_count}"
            )
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
