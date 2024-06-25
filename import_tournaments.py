#!/usr/bin/env python

import csv
import json
import os
import requests
from pymongo import MongoClient
import certifi

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
db_collection = db['tournaments']

import argparse

# Set up argument parser
parser = argparse.ArgumentParser(description='Manage tournaments.')
parser.add_argument('--deleteAll',
                    action='store_true',
                    help='Delete all tournaments.')
args = parser.parse_args()

if args.deleteAll:
    delete_result = db_collection.delete_many({})
    print(
        f"Deleted {delete_result.deleted_count} tournaments from the database."
    )
    delete_result = db['matches'].delete_many({})
    print(
        f"Deleted {delete_result.deleted_count} matches from the database."
    )

# read csv
# iterate over rows and post to tournaments API
with open("data/data_tournaments.csv", encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        # Check if the tournament alias already exists
        tournament_exists = db_collection.find_one({'alias': row['alias']})
        if not tournament_exists:
            # parse JSON strings if they are not already dictionaries
            if isinstance(row.get('ageGroup'), str):
                row['ageGroup'] = json.loads(row['ageGroup'])
            if isinstance(row.get('defaultSettings'), str):
                row['defaultSettings'] = json.loads(row['defaultSettings'])
            if isinstance(row.get('published'), str):
                row['published'] = row['published'].lower() == 'true'
            if isinstance(row.get('active'), str):
                row['active'] = row['active'].lower() == 'true'
            row['seasons'] = []
            row['external'] = False
            row['legacyId'] = int(row['legacyId'])

            response = requests.post(f"{BASE_URL}/tournaments/", json=row, headers=headers)
            if response.status_code == 201:
                print('--> Successfully posted Tournament: ', row)
            else:
                print('Failed to post Tournament: ', row, ' - Status code:',
                      response.status_code)
                exit()
        else:
            print(
                f"Tournament with alias {row['alias']} already exists, skipping insertion."
            )

# insert seasons
with open("data/data_seasons.csv", encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        # Check if the season already exists
        season_exists = db_collection.find_one({
            'alias': row['t_alias'],
            'seasons.alias': row['alias']
        })
        if not season_exists:
            # parse JSON strings if they are not already dictionaries
            if isinstance(row.get('published'), str):
                row['published'] = row['published'].lower() == 'true'
            row['rounds'] = []

            response = requests.post(f"{BASE_URL}/tournaments/{row['t_alias']}/seasons/",
                                     json=row,
                                     headers=headers)
            if response.status_code == 201:
                print('--> Successfully posted Season: ', row)
            else:
                print('Failed to post Season: ', row, ' - Status code:',
                      response.status_code)
                exit()
        else:
            print(
                f"Season {row['alias']} for tournament {row['t_alias']} already exists, skipping insertion."
            )

# insert rounds
with open("data/data_rounds.csv", encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        # Check if the round already exists
        round_exists = db_collection.find_one({
            'alias': row['t_alias'],
            'seasons': {
                '$elemMatch': {
                    'alias': row['s_alias'],
                    'rounds': {
                        '$elemMatch': {
                            'alias': row['alias']
                        }
                    }
                }
            }
        })
        if not round_exists:
            # parse JSON strings if they are not already dictionaries
            if isinstance(row.get('published'), str):
                row['published'] = row['published'].lower() == 'true'
            if isinstance(row.get('cresteStats'), str):
                row['cresteStats'] = row['cresteStats'].lower() == 'true'
            if isinstance(row.get('createStandings'), str):
                row['createStandings'] = row['createStandings'].lower(
                ) == 'true'
            if isinstance(row.get('matchdaysType'), str):
                row['matchdaysType'] = json.loads(row['matchdaysType'])
            if isinstance(row.get('matchdaysSortedBy'), str):
                row['matchdaysSortedBy'] = json.loads(row['matchdaysSortedBy'])
            if isinstance(row.get('settings'), str):
                row['settings'] = json.loads(row['settings'])
            row['matchdays'] = []

            response = requests.post(
                f"{BASE_URL}/tournaments/{row['t_alias']}/seasons/{row['s_alias']}/rounds/",
                json=row,
                headers=headers)
            if response.status_code == 201:
                print('--> Successfully posted Round: ', row)
            else:
                print('Failed to post Round: ', row, ' - Status code:',
                      response.status_code)
                exit()
        else:
            print(
                f"Round {row['alias']} for season {row['s_alias']} for tournament {row['t_alias']} already exists, skipping insertion."
            )

# insert matchdays
with open("data/data_matchdays.csv", encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        # Check if the matchday already exists
        matchday_exists = db_collection.find_one({
            'alias': row['t_alias'],
            'seasons': {
                '$elemMatch': {
                    'alias': row['s_alias'],
                    'rounds': {
                        '$elemMatch': {
                            'alias': row['r_alias'],
                            'matchdays': {
                                '$elemMatch': {
                                    'alias': row['alias']
                                }
                            }
                        }
                    }
                }
            }
        })
        if not matchday_exists:
            # parse JSON strings if they are not already dictionaries
            if isinstance(row.get('published'), str):
                row['published'] = row['published'].lower() == 'true'
            if isinstance(row.get('createStandings'), str):
                row['createStandings'] = row['createStandings'].lower(
                ) == 'true'
            if isinstance(row.get('createStats'), str):
                row['createStats'] = row['createStats'].lower() == 'true'
            if isinstance(row.get('settings'), str):
                row['settings'] = json.loads(row['settings'])
            if isinstance(row.get('type'), str):
                row['type'] = json.loads(row['type'])
            row['matches'] = []

            response = requests.post(
                f"{BASE_URL}/tournaments/{row['t_alias']}/seasons/{row['s_alias']}/rounds/{row['r_alias']}/matchdays/",
                json=row,
                headers=headers)
            if response.status_code == 201:
                print('--> Successfully posted Matchday: ', row)
            else:
                print('Failed to post Matchday: ', row, ' - Status code:',
                      response.status_code)
                exit()
        else:
            print(
                f"Matchday {row['alias']} for round {row['r_alias']} for season {row['s_alias']} for tournament {row['t_alias']} already exists, skipping insertion."
            )

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
        if isinstance(row.get('away'), str):
            row['away'] = json.loads(row['away'])
        if isinstance(row.get('matchStatus'), str):
            row['matchStatus'] = json.loads(row['matchStatus'])
        if isinstance(row.get('published'), str):
            row['published'] = row['published'].lower() == 'true'
        if isinstance(row.get('overtime'), str):
            row['overtime'] = row['overtime'].lower() == 'true'
        if isinstance(row.get('shootout'), str):
            row['shootout'] = row['shootout'].lower() == 'true'
        if isinstance(row.get('matchId'), str):
            row['matchId'] = int(row['matchId'])


        t_alias = row['tournament']['alias']
        s_alias = row['season']['alias']
        r_alias = row['round']['alias']
        md_alias = row['matchday']['alias']

        # Check if the match already exists
        db_collection = db['matches']
        match_exists = db_collection.find_one({
            'matchId': row['matchId']
        })
        if not match_exists:
            response = requests.post(
                f"{BASE_URL}/matches/",
                json=row,
                headers=headers)
            if response.status_code == 201:
                print('--> Successfully posted Match: ', row)
                exit()
            else:
                print('Failed to post Match: ', row, ' - Status code:',
                      response.status_code)
                exit()
        else:
            print(
                f"Match {row['matchId']} for tournament {t_alias}, season {s_alias}, round {r_alias} and matchday {md_alias} already exists, skipping insertion."
            )
