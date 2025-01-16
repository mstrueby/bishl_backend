#!/usr/bin/env python

import csv
import json
import os
import glob
import requests
from pymongo import MongoClient
import certifi
from fastapi.encoders import jsonable_encoder
import argparse

filename = "data/data_tournaments.csv"
BASE_URL = os.environ['BE_API_URL']
api_url = f"{BASE_URL}/"
print("api_url", api_url)

# first login user
login_url = f"{BASE_URL}/users/login"
login_data = {
  "email": os.environ['ADMIN_USER'],
  "password": os.environ['ADMIN_PASSWORD']
}
login_response = requests.post(login_url, json=login_data)
print("login_response", login_response.status_code)
if login_response.status_code != 200:
  print("Error logging in - Repl online?")
  exit(1)

# get token
token = login_response.json()["token"]
print("token", token)

# User authentication header
headers = {
  'Authorization': f'Bearer {token}',
  'Content-Type': 'application/json'
}

# Connect to the MongoDB collection
client = MongoClient(os.environ['DB_URL'], tlsCAFile=certifi.where())
db = client[os.environ['DB_NAME']]
db_collection = db['matches']


# import rosters
def import_rosters():
  # Get the list of all files starting with 'data_rosters' in the 'data' directory
  roster_files = sorted(glob.glob(os.path.join("data", "data_rosters_*.csv")))
  roster_files = [
    file for file in roster_files if not file.endswith('_done.csv')
  ]
  # Iterate over each file
  for roster_file in roster_files:
    print(f"Processing file: {roster_file}")
    with open(roster_file, encoding='utf-8') as f:
      reader = csv.DictReader(f)
      matches = []
      for row in reader:

        #if int(row['match_id']) not in [7279,7439,7445]:
        #    continue

        existing_match = db['matches'].find_one(
          {'matchId': int(row['match_id'])})
        if not existing_match:
          print("Match not found for roster: ", row['match_id'])
          exit()
        # parse JSON strings if they are not already dictionaries
        match_id = int(row['match_id'])
        team_flag = row['team_flag']
        if isinstance(row.get('player'), str):
          player = json.loads(row['player'])
        if isinstance(row.get('playerPosition'), str):
          playerPosition = json.loads(row['playerPosition'])
        passNumber = row['passNumber']
        #print("player", player)
        roster_player = {
          'player': player,
          'playerPosition': playerPosition,
          'passNumber': passNumber
        }

        match_exists = any(
          match.get('match_id') == match_id for match in matches)
        if not match_exists:
          match = {'match_id': match_id}
          matches.append(match)

        # Check if any team_flag roster exists in any match object in matches
        for match in matches:
          if match['match_id'] == match_id:
            if team_flag == 'home':
              if 'home_roster' not in match:
                match['home_roster'] = []
              match['home_roster'].append(roster_player)
            elif team_flag == 'away':
              if 'away_roster' not in match:
                match['away_roster'] = []
              match['away_roster'].append(roster_player)

        print("processed file row: ", row['match_id'], row['team_flag'],
              player['lastName'])

      # Print matches in readable JSON format
      for match in matches:
        match_id = int(match['match_id'])
        # Ensure match_id is an int and retrieve the existing match
        existing_match = db_collection.find_one({'matchId': match_id})
        if existing_match:
          # Post home roster
          #print(json.dumps(match['home_roster'], indent=2))
          response = requests.put(
            f"{BASE_URL}/matches/{existing_match['_id']}/home/roster/",
            json=match.get('home_roster', []),
            headers=headers)
          if response.status_code == 200:
            print('--> Successfully put Home Roster for Match ', match_id)
          else:
            print('Failed to put Home Roster for Match ', match_id,
                  ' - Status code:', response.status_code, response.json())
            exit()
          # Post away roster
          response = requests.put(
            f"{BASE_URL}/matches/{existing_match['_id']}/away/roster/",
            json=match.get('away_roster', []),
            headers=headers)
          if response.status_code == 200:
            print('--> Successfully put Away Roster for Match ', match_id)
          else:
            print('Failed to put Away Roster for Match ', match_id,
                  ' - Status code:', response.status_code)
            exit()
        else:
          print("Match not found for roster: ", match_id)
          exit()

    # Rename the roster file to start with an underscore
    new_roster_file_name = os.path.join(
      os.path.dirname(roster_file),
      os.path.splitext(os.path.basename(roster_file))[0] + '_done.csv')
    os.rename(roster_file, new_roster_file_name)


# import scores
def import_scores():
  with open("data/data_scores.csv", encoding='utf-8') as f:
    reader = csv.DictReader(f)
    matches = []
    for i, row in enumerate(reader):
      print(f"Processing file row: {i}")
      #if i >= 37:
      #  break
      match_id = int(row['match_id'])
      existing_match = db_collection.find_one({'matchId': match_id})
      if not existing_match:
        print("Match not found for scores: ", row['match_id'])
        exit()
      if len(existing_match['home']['scores']) > 0:
        print("Match already has scores: ", row['match_id'])
        continue
      # parse JSON strings if they are not already dictionaries
      team_flag = row['team_flag']
      if isinstance(row.get('goalPlayer'), str):
        goalPlayer = json.loads(row['goalPlayer'])
      if isinstance(row.get('assistPlayer'), str) and row['assistPlayer']:
        assistPlayer = json.loads(row['assistPlayer'])
      else:
        assistPlayer = None
      current_score = {
        'matchTime': row['matchTime'],
        'goalPlayer': goalPlayer
      }
      if assistPlayer:
        current_score['assistPlayer'] = assistPlayer

      match_exists = False
      for match in matches:
        if match.get('match_id') == match_id:
          match_exists = True
          match[team_flag]['scores'].append(current_score)
          #print("# match existed ", match)
          break
      if not match_exists:
        match = {
          '_id': existing_match['_id'],
          'match_id': match_id,
          'home': {
            'scores': []
          },
          'away': {
            'scores': []
          }
        }
        match[team_flag]['scores'].append(current_score)
        #print("# new match", match)

        matches.append(match)
      #print("### matches", matches)

    #print(json.dumps(matches, indent=2))

    # For each match in matches, call PATCH endpoint to update match
    for match in matches:
      match_obj_id = match['_id']
      response = requests.patch(f"{BASE_URL}/matches/{match_obj_id}",
                                json=match,
                                headers=headers)
      if response.status_code == 200:
        print(f"--> Successfully patched Match {match_obj_id}")
      else:
        print(
          f"Failed to patch Match {match_obj_id} - Status code: {response.status_code}"
        )
        exit()


# import penalties
def import_penalties():
  with open("data/data_penalties.csv", encoding='utf-8') as f:
    reader = csv.DictReader(f)
    matches = []
    for i, row in enumerate(reader):
      #if i >= 7:
      #  break
      match_id = int(row['match_id'])
      existing_match = db_collection.find_one({'matchId': match_id})
      if not existing_match:
        print("Match not found for penalties: ", row['match_id'])
        exit()
      team_flag = row['team_flag']
      if isinstance(row.get('penaltyPlayer'), str):
        penaltyPlayer = json.loads(row['penaltyPlayer'])
      if isinstance(row.get('penaltyCode'), str):
        penaltyCode = json.loads(row['penaltyCode'])
      if isinstance(row.get('isGM'), str):
        row['isGM'] = row['isGM'].lower() == 'true'
      if isinstance(row.get('isMP'), str):
        row['isMP'] = row['isMP'].lower() == 'true'
      if len(row['matchTimeEnd']) == 0:
        row['matchTimeEnd'] = None
      current_penalty = {
        'matchTimeStart': row['matchTimeStart'],
        'matchTimeEnd': row['matchTimeEnd'],
        'penaltyPlayer': penaltyPlayer,
        'penaltyCode': penaltyCode,
        'penaltyMinutes': int(row['penaltyMinutes']),
        'isGM': row['isGM'],
        'isMP': row['isMP']
      }
      match_exists = False
      for match in matches:
        if match.get('match_id') == match_id:
          match_exists = True
          match[team_flag]['penalties'].append(current_penalty)
          break
      if not match_exists:
        match = {
          '_id': existing_match['_id'],
          'match_id': match_id,
          'home': {
            'penalties': []
          },
          'away': {
            'penalties': []
          }
        }
        match[team_flag]['penalties'].append(current_penalty)
        matches.append(match)

    #print(json.dumps(matches, indent=2))
    for match in matches:
      match_obj_id = match['_id']
      response = requests.patch(f"{BASE_URL}/matches/{match_obj_id}",
                                json=match,
                                headers=headers)
      if response.status_code == 200:
        print(f"--> Successfully patched Match {match_obj_id}")
      else:
        print(
          f"Failed to patch Match {match_obj_id} - Status code: {response.status_code}"
        )
        exit()


# Set up argument parser
parser = argparse.ArgumentParser(description='Manage matches.')
parser.add_argument('--deleteAll',
                    action='store_true',
                    help='Delete all matches.')
parser.add_argument('--importAll',
                    action='store_true',
                    help='Import all matches.')
parser.add_argument('--rosters', action='store_true', help='Import rosters.')
parser.add_argument('--scores', action='store_true', help='Import scoreboard.')
parser.add_argument('--penalties',
                    action='store_true',
                    help='Import penalties.')
args = parser.parse_args()

if args.rosters:
  import_rosters()
  exit()

if args.scores:
  import_scores()
  exit()

if args.penalties:
  import_penalties()
  exit()

if args.deleteAll:
  delete_result = db_collection.delete_many({})
  print(f"Deleted {delete_result.deleted_count} matches from the database.")

# import matches
with open("data/data_matches.csv", encoding='utf-8') as f:
  reader = csv.DictReader(f)
  for row in reader:
    # parse JSON strings if they are not already dictionaries
    if isinstance(row.get('tournament'), str):
      row['tournament'] = json.loads(row['tournament'])
    if isinstance(row.get('season'), str):
      row['season'] = json.loads(row['season'])
    if isinstance(row.get('round'), str):
      row['round'] = json.loads(row['round'])
    if isinstance(row.get('matchday'), str):
      row['matchday'] = json.loads(row['matchday'])
    if isinstance(row.get('home'), str):
      row['home'] = json.loads(row['home'])
    if len(row['home']['logo']) == 0:
      row['home']['logo'] = None
    if isinstance(row.get('away'), str):
      row['away'] = json.loads(row['away'])
    if len(row['away']['logo']) == 0:
      row['away']['logo'] = None
    if isinstance(row.get('venue'), str):
      row['venue'] = json.loads(row['venue'])
    if len(row['venue']['venueId']) == 0:
      row['venue']['venueId'] = None
    if isinstance(row.get('matchStatus'), str):
      row['matchStatus'] = json.loads(row['matchStatus'])
    if isinstance(row.get('finishType'), str):
      row['finishType'] = json.loads(row['finishType'])
    if isinstance(row.get('published'), str):
      row['published'] = row['published'].lower() == 'true'
    if isinstance(row.get('matchId'), str):
      row['matchId'] = int(row['matchId'])
    if 'referee1' in row and row['referee1'].strip():
      row['referee1'] = json.loads(row['referee1'])
      del row['referee1']
    if 'referee2' in row and row['referee2'].strip():
      row['referee2'] = json.loads(row['referee2'])
      del row['referee2']

    t_alias = row['tournament']['alias']
    s_alias = row['season']['alias']
    r_alias = row['round']['alias']
    md_alias = row['matchday']['alias']

    # Check if the match already exists
    match_exists = db_collection.find_one({'matchId': row['matchId']})
    if not match_exists:
      response = requests.post(f"{BASE_URL}/matches/",
                               json=row,
                               headers=headers)
      if response.status_code == 201:
        print(
          f"--> Successfully posted Match: {row['matchId']} - {t_alias} / {s_alias} / {r_alias} / {md_alias}"
        )
        if not args.importAll:
          print("--importAll flag not set, exiting.")
          exit()
      else:
        print('Failed to post Match: ', row, ' - Status code:',
              response.status_code)
        exit()
    else:
      print(
        f"Match {row['matchId']} for {t_alias} / {s_alias} / {r_alias} / {md_alias} already exists, skipping insertion."
      )
