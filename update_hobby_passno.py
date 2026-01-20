#!/usr/bin/env python
import argparse
import os

import certifi
from pymongo import MongoClient

# Set up argument parser
parser = argparse.ArgumentParser(description="Update hobby team passNo to null.")
parser.add_argument("--prod", action="store_true", help="Run on production database.")
parser.add_argument(
    "--dry-run", action="store_true", help="Show what would be updated without making changes."
)
args = parser.parse_args()

# Get environment variables
if args.prod:
    DB_URL = os.environ["DB_URL_PROD"]
    DB_NAME = "bishl"
else:
    DB_URL = os.environ["DB_URL"]
    DB_NAME = "bishl_dev"

print("DB_URL: ", DB_URL)
print("DB_NAME:", DB_NAME)
print("DRY RUN:", args.dry_run)
print()

# MongoDB setup
client = MongoClient(DB_URL, tlsCAFile=certifi.where())
db = client[DB_NAME]
db_players = db["players"]

try:
    # Statistics
    total_players = 0
    players_with_hobby = 0
    teams_updated = 0

    # Get all players
    all_players = db_players.find({})

    for player in all_players:
        total_players += 1
        player_modified = False
        player_name = f"{player.get('firstName', '')} {player.get('lastName', '')}"

        # Loop through assignedTeams
        for club_idx, club in enumerate(player.get("assignedTeams", [])):
            for team_idx, team in enumerate(club.get("teams", [])):
                # Check if teamAlias is "1-hobby"
                if team.get("teamAlias") == "1-hobby":
                    current_passno = team.get("passNo")

                    # Only update if passNo is not already None/null
                    if current_passno is not None:
                        if not player_modified:
                            players_with_hobby += 1
                            player_modified = True
                            print(f"Player: {player_name}")

                        print(f"  - Club: {club.get('clubName')}, Team: {team.get('teamName')}")
                        print(f"    Current passNo: {current_passno} -> Setting to null")
                        teams_updated += 1

                        if not args.dry_run:
                            # Update the passNo to None in the database
                            update_path = f"assignedTeams.{club_idx}.teams.{team_idx}.passNo"
                            db_players.update_one(
                                {"_id": player["_id"]}, {"$set": {update_path: None}}
                            )

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total players processed: {total_players}")
    print(f"Players with 1-hobby team: {players_with_hobby}")
    print(f"Teams updated: {teams_updated}")

    if args.dry_run:
        print()
        print("DRY RUN - No changes were made to the database")
        print("Run without --dry-run to apply changes")
    else:
        print()
        print("✅ Changes applied successfully")

except Exception as e:
    print(f"An error occurred: {e}")
    import traceback

    traceback.print_exc()
    exit(1)
finally:
    client.close()
