#!/usr/bin/env python
import os
import certifi
from pymongo import MongoClient
import argparse
from datetime import datetime

# Set up argument parser
parser = argparse.ArgumentParser(description='Update club logo URLs in user documents.')
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

# Create a lookup dictionary for clubs
print("\nBuilding club lookup dictionary...")
clubs_lookup = {}
clubs = db['clubs'].find({})
for club in clubs:
    club_id = club.get('_id')
    logo_url = club.get('logoUrl')
    if club_id and logo_url:
        clubs_lookup[str(club_id)] = logo_url
        print(f"Found logo for club: {club.get('name', 'Unknown')} - {logo_url}")

# Update all users
print("\nUpdating user documents...")
users = db['users'].find({})
total_users = 0
updated_users = 0

for user in users:
    total_users += 1
    updates_needed = {}

    # Check and update club logo
    user_club = user.get('club', {})
    #print("user_club", user_club)
    if user_club and 'clubId' in user_club:
        club_id = user_club.get('clubId')
        if club_id in clubs_lookup and user_club.get('logoUrl') != clubs_lookup[club_id]:
            updates_needed['club.logoUrl'] = clubs_lookup[club_id]

    # Check and update referee club logo
    user_referee = user.get('referee', {})
    #print("user_referee", user_referee)
    if user_referee and user_referee.get('club', {}).get('clubId') in clubs_lookup:
        referee_club_id = user_referee['club']['clubId']
        updates_needed['referee.club.logoUrl'] = clubs_lookup[referee_club_id]
    #print("updates_needed", updates_needed)
    # Apply updates if needed
    if updates_needed:
        try:
            result = db['users'].update_one(
                {'_id': user['_id']},
                {'$set': updates_needed}
            )

            if result.modified_count > 0:
                updated_users += 1
                print(f"✅ Updated logos for {user.get('firstName', '')} {user.get('lastName', '')}")
            else:
                print(f"⚠️ No changes made for {user.get('firstName', '')} {user.get('lastName', '')}")
        except Exception as e:
            print(f"❌ Error updating {user.get('firstName', '')} {user.get('lastName', '')}: {str(e)}")
    else:
        print(f"ℹ️ No updates needed for {user.get('firstName', '')} {user.get('lastName', '')}")

print(f"\nSummary: Updated {updated_users} of {total_users} users")