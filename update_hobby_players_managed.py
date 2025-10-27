#!/usr/bin/env python
import argparse
import os

import certifi
from pymongo import MongoClient

# Set up argument parser
parser = argparse.ArgumentParser(description="Update managedByISHD flag for hobby players.")
parser.add_argument("--prod", action="store_true", help="Update in production environment.")
args = parser.parse_args()

# Get environment variables
if args.prod:
    DB_URL = os.environ["DB_URL_PROD"]
    DB_NAME = "bishl"
else:
    DB_URL = os.environ["DB_URL"]
    DB_NAME = "bishl_dev"
print("DB_URL: ", DB_URL)
print("DB_NAME", DB_NAME)

# MongoDB setup
client = MongoClient(DB_URL, tlsCAFile=certifi.where())
db = client[DB_NAME]
db_players = db["players"]

try:
    # Find all players that have '1-hobby' in their team aliases
    query = {"assignedTeams.teams.teamAlias": "1-hobby"}

    players = list(db_players.find(query))
    print(f"Found {len(players)} players with '1-hobby' team assignment")

    # Update each player's managedByISHD flag
    for player in players:
        player_id = player["_id"]
        first_name = player["firstName"]
        last_name = player["lastName"]

        # Update the player's managedByISHD flag
        update_result = db_players.update_one(
            {"_id": player_id}, {"$set": {"managedByISHD": False}}
        )

        if update_result.modified_count > 0:
            print(f"✅ Successfully updated Player: {first_name} {last_name}")
        else:
            print(f"⚠️ No changes made for Player: {first_name} {last_name}")

    # Print summary
    print(f"\nUpdate completed. Processed {len(players)} players with '1-hobby' team assignment.")

except Exception as e:
    print(f"❌ An error occurred: {e}")
    import traceback

    traceback.print_exc()
    exit(1)
