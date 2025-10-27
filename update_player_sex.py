#!/usr/bin/env python
import argparse
import os

import certifi
import requests
from pymongo import MongoClient

from models.players import SexEnum

# Set up argument parser
parser = argparse.ArgumentParser(description='Update player sex based on first names.')
parser.add_argument('--prod', action='store_true', help='Update production database.')
args = parser.parse_args()

# Get environment variables and setup MongoDB connection
if args.prod:
    DB_URL = os.environ['DB_URL_PROD']
    DB_NAME = 'bishl'
else:
    DB_URL = os.environ['DB_URL']
    DB_NAME = 'bishl_dev'

print(f"Connecting to database: {DB_NAME}")
client = MongoClient(DB_URL, tlsCAFile=certifi.where())
db = client[DB_NAME]
print("connected")

def get_gender_from_api(name):
    try:
        api_key = os.environ.get('GENDERIZE_API_KEY')
        response = requests.get(f"https://api.genderize.io/?name={name}&apikey={api_key}")
        data = response.json()
        if data['probability'] > 0.8:  # Only use predictions with high confidence
            return SexEnum.FEMALE if data['gender'] == 'female' else SexEnum.MALE
        return SexEnum.MALE  # Default to MAN if unsure
    except:
        return SexEnum.MALE  # Default to MAN on API failure

# Process all players
players = db['players'].find({})
total_players = 0
updated_players = 0

for player in players:
    total_players += 1
    first_name = player.get('firstName', '').split()[0]  # Get first word of first name

    if first_name:
        predicted_sex = get_gender_from_api(first_name)
        current_sex = player.get('sex', SexEnum.MALE)

        if current_sex != predicted_sex:
            update_result = db['players'].update_one(
                {'_id': player['_id']},
                {'$set': {'sex': predicted_sex}}
            )

            if update_result.modified_count > 0:
                updated_players += 1
                print(f"  ✅ Updated player: {player.get('firstName', 'Unknown')} {player.get('lastName', 'Unknown')} - {current_sex} -> {predicted_sex}")
            else:
                print(f"  ❌ Change not successfull for player: {player.get('firstName', 'Unknown')} {player.get('lastName', 'Unknown')} - {current_sex}")
        #else:
        #    print(f"  ⚠️ No changes needed for player: {player.get('firstName', 'Unknown')} {player.get('lastName', 'Unknown')} - {current_sex}")

print(f"\nSummary: Updated {updated_players} of {total_players} players")
