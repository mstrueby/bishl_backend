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
    #print("row", row)
    first_name = row['Vorname']
    last_name = row['Nachname']
    email = row.get('Email')
    # Skip row if no email is found
    if not email:
      print("No email found for referee", first_name, last_name)
      continue
      
    club = None
    if isinstance(row.get('club'), str):
      club = json.loads(row['club'])
    # skip row if no club is found
    if not club:
      print("No club found for referee", row)
      continue
    level = row.get('level', 'n/a')
    passNo = row.get('passNo', None)
    ishdLevel = row.get('ishdLevel', None)
    active = True

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
      
      # Create user via API endpoint instead of direct DB insertion
      referee_obj = {
        'club': club,
        'level': level,
        'passNo': passNo,
        'ishdLevel': ishdLevel,
        'active': active
      }
      new_user = {
        'email': email,
        'password': random_password,
        'firstName': first_name,
        'lastName': last_name,
        'roles': ['REFEREE'],
        'referee': referee_obj 
      }
      
      # Use the API endpoint to register the user
      register_url = f"{BASE_URL}/users/register"
      register_response = requests.post(register_url, json=new_user, headers=headers)
      
      if register_response.status_code == 201:
        print(f"User {email} created via API endpoint.")
        
        # Send welcome email to the new user
        try:
          # Import here to avoid circular imports
          import asyncio
          from mail_service import send_email
          
          # Prepare email content
          subject = "BISHL - Schiedsrichter-Account angelegt"
          #email='marian.strueby@web.de'
          recipients = [email]
          body = f"""
            <p>Hallo {first_name},</p>
            <p>dein Schiedsrichter-Account wurde erfolgreich angelegt.</p>
            <p>Hier sind deine Login-Details:</p>
            <ul>
              <li><strong>E-Mail:</strong> {email}</li>
              <li><strong>Passwort:</strong> {random_password}</li>
            </ul>
            <p>Bitte logge dich bei www.bishl.de ein und ändere dein Passwort.</p>
            <p>Falls du Fragen hast, melde dich bitte über website@bishl.de</p>
            <p>Viele Grüße,<br>Marian</p>
          """
          #print("reciepient", recipients)
          #print("subject", subject)
          #print("body", body)
          
          # Run the async function in a separate event loop
          if args.prod:
              loop = asyncio.new_event_loop()
              asyncio.set_event_loop(loop)
              loop.run_until_complete(send_email(subject, recipients, body))
              loop.close()
              print(f"Welcome email sent to {email}")
          else:
              print(f"Skipping sending welcome email to {email} in dev mode.")
          if not args.importAll:
            print("--importAll flag not set, exiting.")
            exit()
        except Exception as e:
          print(f"Failed to send welcome email to {email}: {str(e)}")
      else:
        print(f"Failed to create user {email} via API. Status code: {register_response.status_code}")
        print(f"Response: {register_response.text}")