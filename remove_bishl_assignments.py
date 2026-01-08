#!/usr/bin/env python
import argparse
import os

import certifi
from pymongo import MongoClient

# Set up argument parser
parser = argparse.ArgumentParser(
    description="Remove all team assignments and set managedByISHD=True for eligible players."
)
parser.add_argument("--prod", action="store_true", help="Update production database.")
parser.add_argument(
    "--dry-run", action="store_true", help="Show what would be modified without actually doing it."
)
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


def remove_bishl_assignments():
    """Remove all team assignments and set managedByISHD=True for eligible players"""

    # Query:
    # 1. ignore players who have a managedByISHD set to true
    # 2. ignore players who have a teamType HOBBY in any of their assigned teams
    query = {"managedByISHD": {"$ne": True}, "assignedTeams.teams.teamType": {"$ne": "HOBBY"}}

    players = db["players"].find(query)
    players_list = list(players)

    print(f"\nFound {len(players_list)} eligible players for assignment removal")

    if len(players_list) == 0:
        print("No eligible players found")
        return

    modified_count = 0

    for player in players_list:
        player_name = f"{player.get('firstName', '')} {player.get('lastName', '')}"
        player_id = player["_id"]

        print(f"\nProcessing Player: {player_name} (ID: {player_id})")

        if args.dry_run:
            print("  - [DRY RUN] Would remove all assignments and set managedByISHD=True")
        else:
            # - set assignedTeams to empty array
            # - set managedByISHD to true
            result = db["players"].update_one(
                {"_id": player_id}, {"$set": {"assignedTeams": [], "managedByISHD": True}}
            )

            if result.modified_count > 0:
                modified_count += 1
                print("  - ✓ Updated successfully")
            else:
                print("  - ✗ No changes made (already processed?)")

    print(f"\n{'='*60}")
    if args.dry_run:
        print(f"DRY RUN: Would modify {len(players_list)} players")
    else:
        print(f"Successfully modified {modified_count} out of {len(players_list)} players")
    print(f"{'='*60}")


if __name__ == "__main__":
    if args.dry_run:
        print("\n*** DRY RUN MODE - No changes will be made ***\n")
    else:
        confirm = input(
            "\nThis will permanently remove ALL team assignments and set managedByISHD=True for eligible players. Continue? (yes/no): "
        )
        if confirm.lower() != "yes":
            print("Operation cancelled")
            exit(0)

    remove_bishl_assignments()
    client.close()
    print("\nDone!")
