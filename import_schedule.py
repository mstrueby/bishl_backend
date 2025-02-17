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
    # parse JSON strings if they are not already dictionaries
    if isinstance(row.get('tournament'), str):
      tournament = MatchTournament(**json.loads(row['tournament']))
    if isinstance(row.get('season'), str):
      season = MatchSeason(**json.loads(row['season']))
    if isinstance(row.get('round'), str):
      round = MatchRound(**json.loads(row['round']))
    if isinstance(row.get('matchday'), str):
      matchday = MatchMatchday(**json.loads(row['matchday']))
    if isinstance(row.get('venue'), str):
      venue = MatchVenue(**json.loads(row['venue']))
        
    if isinstance(row.get('published'), str):
      row['published'] = row['published'].lower() == 'true'

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
    

    
    # Check if matchday exists
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
        tournament=row['tournament'],
        season=s_alias,
        round=r_alias,
        matchday=md_alias,
        venue=row.get('venue'),
        published=row.get('published'),
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
