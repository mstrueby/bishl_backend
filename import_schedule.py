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
from models.matches import MatchDB, MatchBase, MatchTournament, MatchSeason, MatchRound, MatchMatchday, MatchVenue
from models.tournaments import RoundDB, MatchdayBase, MatchdayType

filename = "data/data_schedule.csv"
BASE_URL = os.environ['BE_API_URL']
api_url = f"{BASE_URL}/"
print("api_url", api_url)

# first login user
login_url = f"{BASE_URL}/users/login"
login_data = {
  "email": os.environ['SYS_ADMIN_EMAIL'],
  "password": os.environ['SYS_ADMIN_PASSWORD']
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

# Set up argument parser
parser = argparse.ArgumentParser(description='Manage matches.')
parser.add_argument('--importAll',
                    action='store_true',
                    help='Import all matches.')
args = parser.parse_args()

# import matches
with open(filename, encoding='utf-8') as f:
  reader = csv.DictReader(f)
  for row in reader:
    tournament=None
    season=None
    round=None
    matchday=None
    
    # Create tournament object from row data
    tournament_data = row.get('tournament')
    # Ensure the data is in string format for JSON parsing
    if isinstance(tournament_data, str):
        # Attempt to parse JSON
        try:
            tournament_data = json.loads(tournament_data)
        except json.JSONDecodeError:
            print("Error: tournament data is not valid JSON")
            exit()
    # Ensure tournament_data is a dictionary and all keys are strings
    if isinstance(tournament_data, dict) and all(isinstance(k, str) for k in tournament_data.keys()):
        tournament = MatchTournament(**tournament_data)
    else:
        print("Error: tournament data is not a valid dictionary with string keys")
        exit()

    # Create season object from row data
    season_data = row.get('season')
    if isinstance(season_data, str):
        try:
            season_data = json.loads(season_data)
        except json.JSONDecodeError:
            print("Error: season data is not valid JSON")
            exit()
    if isinstance(season_data, dict) and all(isinstance(k, str) for k in season_data.keys()):
        season = MatchSeason(**season_data)
    else:
        print("Error: season data is not a valid dictionary with string keys")
        exit()

    # Create round object from row data
    round_data = row.get('round')
    if isinstance(round_data, str):
        try:
            round_data = json.loads(round_data)
        except json.JSONDecodeError:
            print("Error: round data is not valid JSON")
            exit()
    if isinstance(round_data, dict) and all(isinstance(k, str) for k in round_data.keys()):
        round = MatchRound(**round_data)
    else:
        print("Error: round data is not a valid dictionary with string keys")
        exit()

    # Create matchday object from row data
    matchday_data = row.get('matchday')
    if isinstance(matchday_data, str):
        try:
            matchday_data = json.loads(matchday_data)
        except json.JSONDecodeError:
            print("Error: matchday data is not valid JSON")
            exit()
    if isinstance(matchday_data, dict) and all(isinstance(k, str) for k in matchday_data.keys()):
        matchday = MatchMatchday(**matchday_data)
    else:
        print("Error: matchday data is not a valid dictionary with string keys")
        exit()

    # Create venue object from row data
    venue_data = row.get('venue')
    if isinstance(venue_data, str):
        try:
            venue_data = json.loads(venue_data)
        except json.JSONDecodeError:
            print("Error: venue data is not valid JSON")
            exit()
    if isinstance(venue_data, dict) and all(isinstance(k, str) for k in venue_data.keys()):
        venue = MatchVenue(**venue_data)
    else:
        print("Error: venue data is not a valid dictionary with string keys")
        exit()

    published_value = row.get('published')
    if isinstance(published_value, str):
        published_value = published_value.lower() == 'true'
    # Ensure whether the value is a boolean or None
    published_value = published_value if isinstance(published_value, bool) else False

    # Ensure objects are not None before checking alias
    if any(obj is None for obj in [tournament, season, round, matchday]):
        print('Error: One of the required objects (tournament, season, round, matchday) is None.')
        exit()

    # Check for alias attribute
    if any(obj.alias is None for obj in [tournament, season, round, matchday]):
        print('Error: One of the required fields (tournament, season, round, matchday) is None.')
        exit()
    else
      t_alias = tournament.alias
      s_alias = season.alias
      r_alias = round.alias
      md_alias = matchday.alias
      md_name = matchday.name 
        
    # Check if round exists
    round_url = f"{BASE_URL}/tournaments/{tournament.alias}/season/{s_alias}/round/{r_alias}"
    round_response = requests.get(round_url, headers=headers)
    if round_response.status_code != 200:
        print(f"Error: round does not exist {t_alias} / {s_alias} / {r_alias}")
        exit()
    round_data = RoundDB(**round_response.json())
    # Check if matchday exists in round_data
    if not round_data.matchdays or not any(md.alias == md_alias for md in round_data.matchdays):
        print(f"Creating new matchday {md_alias} for {t_alias} / {s_alias} / {r_alias}...")
        if not md_name:
          print("Error: matchday name is None")
          exit(1)
        new_matchday = MatchdayBase(
          alias=md_alias, 
          name=md_name,
          type=MatchdayType.REGULAR,
          published=True,
          matchSettings=round_data.matchSettings
        )
        create_md_response = requests.post(f"{BASE_URL}/tournaments/{t_alias}/season/{s_alias}/round/{r_alias}/matchdays",
                                           json=jsonable_encoder(new_matchday),
                                           headers=headers)
        if create_md_response.status_code != 201:
            print("Failed to create new matchday: ", f"{t_alias} / {s_alias} / {r_alias} / {md_alias}", " - Status code:", create_md_response.status_code)
            exit()

    #print("row", row)

    
    # Create a new match instance using MatchBase
    new_match = MatchBase(
        tournament=tournament,
        season=season,
        round=round,
        matchday=matchday,
        venue=venue,
        published=published_value,
        # Add other required fields for MatchDB as needed
    )

    # Encode the match object to JSON
    row = jsonable_encoder(new_match)

    response = requests.post(f"{BASE_URL}/matches/",
                             json=row,
                             headers=headers)
    if response.status_code == 201:
      print(
        f"--> Successfully posted Match for {t_alias} / {s_alias} / {r_alias} / {md_alias}"
      )
      if not args.importAll:
        print("--importAll flag not set, exiting.")
        exit()
    else:
      print('Failed to post Match: ', row, ' - Status code:',
            response.status_code)
      exit()
