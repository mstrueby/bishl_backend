
#!/usr/bin/env python
import argparse
import os

import certifi
from pymongo import MongoClient

# Set up argument parser
parser = argparse.ArgumentParser(description="Remove BISHL club assignments from all players.")
parser.add_argument("--prod", action="store_true", help="Update production database.")
parser.add_argument("--dry-run", action="store_true", help="Show what would be removed without actually removing it.")
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
    """Remove all club assignments where clubName='BISHL' from all players"""
    
    # Find all players with BISHL assignments
    query = {
        "assignedTeams": {
            "$elemMatch": {
                "clubName": "BISHL"
            }
        }
    }
    
    players = db["players"].find(query)
    players_list = list(players)
    
    print(f"\nFound {len(players_list)} players with BISHL club assignments")
    
    if len(players_list) == 0:
        print("No players found with BISHL assignments")
        return
    
    modified_count = 0
    
    for player in players_list:
        player_name = f"{player.get('firstName', '')} {player.get('lastName', '')}"
        player_id = player["_id"]
        
        # Count BISHL assignments for this player
        bishl_count = sum(1 for club in player.get("assignedTeams", []) if club.get("clubName") == "BISHL")
        
        print(f"\nPlayer: {player_name} (ID: {player_id})")
        print(f"  - BISHL assignments to remove: {bishl_count}")
        
        if args.dry_run:
            print("  - [DRY RUN] Would remove BISHL assignments")
        else:
            # Remove all club assignments where clubName='BISHL'
            result = db["players"].update_one(
                {"_id": player_id},
                {
                    "$pull": {
                        "assignedTeams": {
                            "clubName": "BISHL"
                        }
                    }
                }
            )
            
            if result.modified_count > 0:
                modified_count += 1
                print(f"  - ✓ Removed BISHL assignments")
            else:
                print(f"  - ✗ Failed to remove assignments")
    
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
        confirm = input("\nThis will permanently remove BISHL club assignments. Continue? (yes/no): ")
        if confirm.lower() != "yes":
            print("Operation cancelled")
            exit(0)
    
    remove_bishl_assignments()
    client.close()
    print("\nDone!")
