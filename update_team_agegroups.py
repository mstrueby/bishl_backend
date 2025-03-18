#!/usr/bin/env python
import os
import certifi
from pymongo import MongoClient
import argparse

# Set up argument parser
parser = argparse.ArgumentParser(description='Update team ageGroups in clubs collection.')
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

# Define age group mapping
age_group_mapping = {
    'MEN': 'HERREN',
    'WOMEN': 'DAMEN',
    'Junioren': 'U19',
    'Jugend': 'U16',
    'Schüler': 'U13',
    'Bambini': 'U10',
    'Mini': 'U8'
}

# Update all clubs
clubs = db['clubs'].find({})
total_teams = 0
updated_teams = 0

for club in clubs:
    print(f"\nProcessing club: {club.get('name', 'Unknown')}")
    teams = club.get('teams', [])
    
    for team_idx, team in enumerate(teams):
        total_teams += 1
        current_age_group = team.get('ageGroup')
        
        if current_age_group in age_group_mapping:
            new_age_group = age_group_mapping[current_age_group]
            
            # Update the team's ageGroup
            update_result = db['clubs'].update_one(
                {'_id': club['_id']},
                {'$set': {f'teams.{team_idx}.ageGroup': new_age_group}}
            )
            
            #if True:
            if update_result.modified_count > 0:
                updated_teams += 1
                print(f"  ✅ Updated team: {team.get('name', 'Unknown')} - {current_age_group} -> {new_age_group}")
            else:
                print(f"  ⚠️ No changes needed for team: {team.get('name', 'Unknown')} - {current_age_group}")
        else:
            print(f"  ❌ Unknown age group for team: {team.get('name', 'Unknown')} - {current_age_group}")

print(f"\nSummary: Updated {updated_teams} of {total_teams} teams")
