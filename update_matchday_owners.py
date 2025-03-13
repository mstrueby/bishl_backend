#!/usr/bin/env python
import os
import csv
import certifi
from pymongo import MongoClient
from datetime import datetime
import argparse
from bson.objectid import ObjectId

# Set up argument parser
parser = argparse.ArgumentParser(description='Update matchday owners in tournaments collection.')
parser.add_argument('--prod', action='store_true', help='Update production database.')
parser.add_argument('--importAll',
    action='store_true',
    help='Import all teams.')
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

# Load the matchday owners data from CSV
matchday_owners = {}
with open('data/data_matchday_owners.csv', encoding='utf-8') as f:
    reader = csv.DictReader(f, delimiter=';', quotechar='"')
    for row in reader:
        matchday_owners[row['alias']] = {
            'clubName': row['clubName'],
            'clubAlias': row['clubAlias'],
            'clubId': row['clubId']
        }

print(f"Loaded {len(matchday_owners)} matchday owners from CSV")

# Find all tournaments with seasons for 2025
tournaments = db['tournaments'].find({
    "seasons.alias": "2025"
})

updated_count = 0
total_matchdays = 0

for tournament in tournaments:
    print(f"Processing tournament: {tournament['name']}")
    
    # Find the 2025 season
    for season_idx, season in enumerate(tournament.get('seasons', [])):
        if season.get('alias') == '2025':
            print(f"  Processing season 2025 in {tournament['name']}")
            
            # Process all rounds in the season
            for round_idx, round_data in enumerate(season.get('rounds', [])):
                print(f"    Processing round: {round_data.get('name', 'unknown')}")
                
                # Process all matchdays in the round
                for matchday_idx, matchday in enumerate(round_data.get('matchdays', [])):
                    total_matchdays += 1
                    matchday_alias = matchday.get('alias')
                    
                    if matchday_alias in matchday_owners:
                        owner = matchday_owners[matchday_alias]
                        owner_obj = {
                            'clubId': owner['clubId'],
                            'clubName': owner['clubName'],
                            'clubAlias': owner['clubAlias']
                        }
                        
                        # Update the matchday with the owner
                        update_path = f"seasons.{season_idx}.rounds.{round_idx}.matchdays.{matchday_idx}.owner"
                        result = db['tournaments'].update_one(
                            {"_id": tournament['_id']},
                            {"$set": {update_path: owner_obj}}
                        )
                        
                        if result.modified_count > 0:
                            updated_count += 1
                            print(f"      ✅ Updated owner for matchday: {matchday.get('name', 'unknown')} ({matchday_alias}) to {owner['clubName']}")
                        else:
                            print(f"      ⚠️ No changes made for matchday: {matchday.get('name', 'unknown')} ({matchday_alias})")
                    else:
                        print(f"      ℹ️ No owner data for matchday: {matchday.get('name', 'unknown')} ({matchday_alias})")
        if not args.importAll:
            print("--importAll flag not set, exiting.")
            exit()
            
print(f"\nSummary: Updated {updated_count} of {total_matchdays} matchdays")
