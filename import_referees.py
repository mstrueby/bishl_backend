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
from models.matches import MatchDB, MatchBase, MatchTournament, MatchSeason, MatchRound, MatchMatchday, MatchVenue, MatchTeam
from models.tournaments import RoundDB, MatchdayBase, MatchdayType
from datetime import datetime
import random
import string

# Set up argument parser
parser = argparse.ArgumentParser(description='Manage matches.')
parser.add_argument('--importAll',
  action='store_true',
  help='Import all matches.')
parser.add_argument('--prod',
  action='store_true',
  help='Import matches to production.')
args = parser.parse_args()

filename = "data/data_referees.csv"
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
db_collection = db['users']

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

# import and register referees
with open(filename, encoding='utf-8') as f:
  reader = csv.DictReader(f, 
                         delimiter=';',
                         quotechar='"',
                         doublequote=True,
                         skipinitialspace=True)
  for row in reader:
    print("row", row)
    first_name = row['Vorname']
    last_name = row['Nachname']
    email = row['Email']
    club = None
    if isinstance(row.get('Verein'), str):
      club = json.loads(row['Verein'])
    # skip row if no club is found
    if not club:
      print("No club found for referee", row)
      continue

    # check if email is already registered
    existing_user = db_collection.find_one({'email': email})
    if existing_user:
      # ensure roles array contains REFEREE
      if 'roles' not in existing_user or 'REFEREE' not in existing_user['roles']:
        existing_user['roles'].append('REFEREE')
        db_collection.update_one({'email': email}, {'$set': existing_user})
        print(f"User {email} already exists and has been updated.")
      else:
        print(f"User {email} already exists and has REFEREE role.")
    else:
      # create new user
      # generate password
      
      # generate a random password
      password_length = 12
      random_password = ''.join(random.choices(string.ascii_letters + string.digits, k=password_length))
      new_user = {
        'email': email,
        'password': random_password,
        'firstName': first_name,
        'lastName': last_name,
        'roles': ['REFEREE'],
        'club': club
      }
      db_collection.insert_one(new_user)
      print(f"User {email} created.")