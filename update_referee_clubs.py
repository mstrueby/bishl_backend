#!/usr/bin/env python
import argparse
import os

import certifi
from pymongo import MongoClient

# Set up argument parser
parser = argparse.ArgumentParser(description="Update referee clubs from user club data.")
parser.add_argument("--prod", action="store_true", help="Update production database.")
args = parser.parse_args()

# Get environment variables and setup MongoDB connection
if args.prod:
    DB_URL = os.environ["DB_URL_PROD"]
    DB_NAME = "bishl"
else:
    DB_URL = os.environ["DB_URL"]
    DB_NAME = "bishl_dev"

print(f"Connecting to database: {DB_NAME}")
client = MongoClient(DB_URL, tlsCAFile=certifi.where())
db = client[DB_NAME]

# Update all users with REFEREE role
print("\nUpdating referee clubs...")
users = db["users"].find({"roles": "REFEREE"})
total_users = 0
updated_users = 0

for user in users:
    total_users += 1
    user_club = user.get("club")
    user_referee = user.get("referee", {})

    if user_club and (not user_referee or user_referee.get("club") != user_club):
        # Create or update referee subdocument with club data
        update_result = db["users"].update_one(
            {"_id": user["_id"]},
            {
                "$set": {
                    "referee.club": user_club,
                    "referee.level": user_referee.get("level", "n/a"),
                    "referee.passNo": user_referee.get("passNo", None),
                    "referee.ishdLevel": user_referee.get("ishdLevel", None),
                    "referee.active": user_referee.get("active", True),
                }
            },
        )

        if update_result.modified_count > 0:
            updated_users += 1
            print(
                f"✅ Updated referee club for {user.get('firstName', '')} {user.get('lastName', '')} - {user_club.get('clubName', '')}"
            )
        else:
            print(f"⚠️ No changes needed for {user.get('firstName', '')} {user.get('lastName', '')}")
    else:
        print(
            f"ℹ️ Skipping {user.get('firstName', '')} {user.get('lastName', '')} - No club data or already synced"
        )

print(f"\nSummary: Updated {updated_users} of {total_users} referee clubs")
