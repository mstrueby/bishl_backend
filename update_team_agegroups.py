
#!/usr/bin/env python
import os
import certifi
from pymongo import MongoClient
import argparse

# Set up argument parser
parser = argparse.ArgumentParser(description='Update team ageGroups in clubs and players collections.')
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
print("\nUpdating clubs collection...")
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
            
            if update_result.modified_count > 0:
                updated_teams += 1
                print(f"  ✅ Updated team: {team.get('name', 'Unknown')} - {current_age_group} -> {new_age_group}")
            else:
                print(f"  ⚠️ No changes needed for team: {team.get('name', 'Unknown')} - {current_age_group}")
        else:
            print(f"  ❌ Unknown age group for team: {team.get('name', 'Unknown')} - {current_age_group}")

print(f"\nSummary Clubs: Updated {updated_teams} of {total_teams} teams")

# Update players' assignedTeams
print("\nUpdating players collection...")
players = db['players'].find({})
total_players = 0
updated_players = 0

for player in players:
    total_players += 1
    assigned_teams = player.get('assignedTeams', [])
    updates_needed = False
    
    for club_idx, club in enumerate(assigned_teams):
        for team_idx, team in enumerate(club.get('teams', [])):
            team_ishd_id = team.get('teamIshdId', '')
            if not team_ishd_id:
                continue
                
            # Find matching age group from the mapping
            matched_age_group = None
            for key in age_group_mapping.keys():
                if key.lower() in team_ishd_id.lower():
                    matched_age_group = age_group_mapping[key]
                    break
            
            if matched_age_group:
                updates_needed = True
                update_path = f'assignedTeams.{club_idx}.teams.{team_idx}.teamAgeGroup'
                db['players'].update_one(
                    {'_id': player['_id']},
                    {'$set': {update_path: matched_age_group}}
                )
    
    if updates_needed:
        updated_players += 1
        print(f"  ✅ Updated player: {player.get('firstName', '')} {player.get('lastName', '')}")
    
print(f"\nSummary Players: Updated {updated_players} of {total_players} players")
