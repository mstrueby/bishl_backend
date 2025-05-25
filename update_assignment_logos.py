#!/usr/bin/env python
import os
import certifi
from pymongo import MongoClient
import argparse
from datetime import datetime

# Set up argument parser
parser = argparse.ArgumentParser(description='Update club logo URLs in assignment documents.')
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

# Update all assignments
print("\nUpdating assignment documents...")
assignments = db['assignments'].find({})
total_assignments = 0
updated_assignments = 0

for assignment in assignments:
    total_assignments += 1
    updates_needed = {}
    
    # Get referee club info
    referee = assignment.get('referee', {})
    if referee and referee.get('clubId') in clubs_lookup:
        club_id = referee['clubId']
        if clubs_lookup[club_id] != referee.get('logoUrl'):
            updates_needed['referee.logoUrl'] = clubs_lookup[club_id]
    
    # Apply updates if needed
    if updates_needed:
        try:
            result = db['assignments'].update_one(
                {'_id': assignment['_id']},
                {'$set': updates_needed}
            )
            
            if result.modified_count > 0:
                updated_assignments += 1
                print(f"✅ Updated logo for referee {referee.get('firstName', '')} {referee.get('lastName', '')}")
            else:
                print(f"⚠️ No changes made for referee {referee.get('firstName', '')} {referee.get('lastName', '')}")
        except Exception as e:
            print(f"❌ Error updating {referee.get('firstName', '')} {referee.get('lastName', '')}: {str(e)}")
    else:
        print(f"ℹ️ No updates needed for referee {referee.get('firstName', '')} {referee.get('lastName', '')}")

print(f"\nSummary: Updated {updated_assignments} of {total_assignments} assignments")
