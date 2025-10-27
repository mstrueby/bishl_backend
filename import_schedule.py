#!/usr/bin/env python
import argparse
import csv
import json
import os
from datetime import datetime

import certifi
import requests
from fastapi.encoders import jsonable_encoder
from pymongo import MongoClient

from models.matches import (
    MatchBase,
    MatchMatchday,
    MatchRound,
    MatchSeason,
    MatchTeam,
    MatchTournament,
    MatchVenue,
)
from models.tournaments import MatchdayBase, RoundDB

# Set up argument parser
parser = argparse.ArgumentParser(description='Manage matches.')
parser.add_argument('--importAll',
                    action='store_true',
                    help='Import all matches.')
parser.add_argument('--prod',
                    action='store_true',
                    help='Import matches to production.')
args = parser.parse_args()


filename = "data/data_schedule_2025.csv"
if args.prod:
    BASE_URL = os.environ['BE_API_URL_PROD']
    DB_URL = os.environ['DB_URL_PROD']
    DB_NAME = 'bishl'
else:
    BASE_URL = os.environ['BE_API_URL']
    DB_URL = os.environ['DB_URL']
    DB_NAME = 'bishl_dev'

# Connect to the MongoDB collection
client = MongoClient(DB_URL, tlsCAFile=certifi.where())
db = client[DB_NAME]
db_collection = db['matches']

print("BASE_URL: ", BASE_URL)
print("DB_NAME", DB_NAME)

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

# import matches
with open(filename, encoding='utf-8') as f:
  reader = csv.DictReader(f,
                         delimiter=';',
                         quotechar='"',
                         doublequote=True,
                         skipinitialspace=True)
  for row in reader:
    # match dicts
    tournament=None
    season=None
    round=None
    matchday=None
    # new matchday for creation
    newMatchday=None

    #print("row", row)

    # Create tournament object from row data
    tournament_data = row.get('tournament')
    # Ensure the data is in string format for JSON parsing
    if isinstance(tournament_data, str):
        # Attempt to parse JSON
        try:
            tournament_data = json.loads(tournament_data)
            tournament = MatchTournament(**tournament_data)
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

    # Create matchday object (for match doc) from row data
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

    # Handle startDate from the CSV
    start_date_str = row.get('startDate')
    start_date = None
    if start_date_str:
        try:
            # Parse the start date from a string to a datetime object
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d %H:%M:%S%z')
        except ValueError:
            print(f"Error parsing startDate: {start_date_str}")
            exit(1)

    # Ensure objects are not None before checking alias
    if any(obj is None for obj in [tournament, season, round, matchday]):
        print('Error: One of the required objects (tournament, season, round, matchday) is None.')
        exit()

    # Check for alias attribute
    if any(obj.alias is None for obj in [tournament, season, round, matchday]):
        print('Error: One of the required fields (tournament, season, round, matchday) is None.')
        exit()
    else:
        t_alias = tournament.alias
        s_alias = season.alias
        r_alias = round.alias
        md_alias = matchday.alias

    # Check if round exists
    round_url = f"{BASE_URL}/tournaments/{t_alias}/seasons/{s_alias}/rounds/{r_alias}"
    round_response = requests.get(round_url, headers=headers)
    if round_response.status_code != 200:
        print(f"Error: round does not exist {t_alias} / {s_alias} / {r_alias}")
        exit()
    round_data = RoundDB(**round_response.json())

    # Check if matchday exists in round_data
    if not round_data.matchdays or not any(md.alias == md_alias for md in round_data.matchdays):
        print(f"Creating new matchday {md_alias} for {t_alias} / {s_alias} / {r_alias}...")
        # Create new Matchday object for tournament doc from row data
        new_matchday_data = row.get('newMatchday')
        if isinstance(new_matchday_data, str):
            try:
                new_matchday_data = json.loads(new_matchday_data)
            except json.JSONDecodeError as e:
                print("Error: newMatchday data is not valid JSON")
                print(f"JSONDecodeError: {e}")  # Debugging information about the JSON error
                print(f"Attempted to parse: {new_matchday_data}")  # Debug the invalid JSON content
                exit()
        if isinstance(new_matchday_data, dict) and all(isinstance(k, str) for k in new_matchday_data.keys()):
            new_matchday = MatchdayBase(**new_matchday_data)
            new_matchday.published=True
            new_matchday.matchSettings=round_data.matchSettings
        else:
            print("Error: newMatchday data is not a valid dictionary with string keys")
            exit()
        create_md_response = requests.post(f"{BASE_URL}/tournaments/{t_alias}/seasons/{s_alias}/rounds/{r_alias}/matchdays/",
                                           json=jsonable_encoder(new_matchday),
                                           headers=headers)
        if create_md_response.status_code != 201:
            print("Failed to create new matchday: ", f"{t_alias} / {s_alias} / {r_alias} / {md_alias}", " - Status code:", create_md_response.status_code)
            exit()

    # Fetch home club and team data
    home_club_alias = row.get('homeClubAlias')
    home_team_alias = row.get('homeTeamAlias')
    home_club_response = requests.get(f"{BASE_URL}/clubs/{home_club_alias}", headers=headers)
    if home_club_response.status_code != 200:
        print(f"Error: home club {home_club_alias} not found")
        exit()
    home_club = home_club_response.json()

    home_team_response = requests.get(f"{BASE_URL}/clubs/{home_club_alias}/teams/{home_team_alias}", headers=headers)
    if home_team_response.status_code != 200:
        print(f"Error: home team {home_team_alias} not found in club {home_club_alias}")
        exit()
    home_team = home_team_response.json()

    # Create home MatchTeam
    home = MatchTeam(
        clubId=home_club.get('_id'),
        clubName=home_club.get('name'),
        clubAlias=home_club.get('alias'),
        teamId=home_team.get('_id'),
        teamAlias=home_team.get('alias'),
        name=home_team.get('name'),
        fullName=home_team.get('fullName'),
        shortName=home_team.get('shortName'),
        tinyName=home_team.get('tinyName'),
        logo=home_club.get('logoUrl')
    )

    # Fetch away club and team data
    away_club_alias = row.get('awayClubAlias')
    away_team_alias = row.get('awayTeamAlias')
    away_club_response = requests.get(f"{BASE_URL}/clubs/{away_club_alias}", headers=headers)
    if away_club_response.status_code != 200:
        print(f"Error: away club {away_club_alias} not found")
        exit()
    away_club = away_club_response.json()

    away_team_response = requests.get(f"{BASE_URL}/clubs/{away_club_alias}/teams/{away_team_alias}", headers=headers)
    if away_team_response.status_code != 200:
        print(f"Error: away team {away_team_alias} not found in club {away_club_alias}")
        exit()
    away_team = away_team_response.json()

    # Create away MatchTeam
    away = MatchTeam(
        clubId=away_club.get('_id'),
        clubName=away_club.get('name'),
        clubAlias=away_club.get('alias'),
        teamId=away_team.get('_id'),
        teamAlias=away_team.get('alias'),
        name=away_team.get('name'),
        fullName=away_team.get('fullName'),
        shortName=away_team.get('shortName'),
        tinyName=away_team.get('tinyName'),
        logo=away_club.get('logoUrl')
    )

    # Create a new match instance using MatchBase
    new_match = MatchBase(
        tournament=tournament,
        season=season,
        round=round,
        matchday=matchday,
        venue=venue,
        published=published_value,
        home=home,
        away=away,
        startDate=start_date
    )

    # Encode the match object to JSON
    new_match_data = jsonable_encoder(new_match)
    #print("new_match_data", new_match_data)

    # Check if the match already exists based on multiple criteria
    query = {
        'startDate': start_date,
        'home.clubId': home.clubId,
        'home.teamId': home.teamId,
        'away.clubId': away.clubId,
        'away.teamId': away.teamId
    }
    match_exists = db_collection.find_one(query)

    if not match_exists:
        response = requests.post(f"{BASE_URL}/matches/",
                                 json=new_match_data,
                                 headers=headers)
        if response.status_code == 201:
          print(
            f"--> Successfully posted Match in {t_alias} / {r_alias} / {md_alias}: {home.fullName} - {away.fullName}"
          )
          if not args.importAll:
            print("--importAll flag not set, exiting.")
            exit()
        else:
          print('Failed to post Match: ', new_match_data, ' - Status code:',
                response.status_code)
          exit()
    else:
        print(f"Match already exists in {t_alias} / {r_alias} / {md_alias}: {home.fullName} - {away.fullName}")

print("Done...")
