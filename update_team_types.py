#!/usr/bin/env python
import argparse
import os

import certifi
from pymongo import MongoClient

# Set up argument parser
parser = argparse.ArgumentParser(
    description="Update teamType for all teams: HOBBY for 1-hobby, COMPETITIVE for others."
)
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
db_clubs = db["clubs"]

try:
    # Statistics
    total_clubs = 0
    clubs_modified = 0
    hobby_teams_updated = 0
    competitive_teams_updated = 0

    # Get all clubs
    all_clubs = db_clubs.find({})

    for club in all_clubs:
        total_clubs += 1
        club_modified = False
        club_name = club.get("name", "")

        # Loop through teams
        for team_idx, team in enumerate(club.get("teams", [])):
            team_alias = team.get("alias")
            current_team_type = team.get("teamType")

            # Determine the expected teamType
            if team_alias == "1-hobby":
                expected_team_type = "HOBBY"
            else:
                expected_team_type = "COMPETITIVE"

            # Only update if teamType doesn't match expected value
            if current_team_type != expected_team_type:
                if not club_modified:
                    clubs_modified += 1
                    club_modified = True
                    print(f"Club: {club_name}")

                print(f"  - Team: {team.get('name')} (alias: {team_alias})")
                print(
                    f"    Current teamType: {current_team_type} -> Setting to {expected_team_type}"
                )

                if expected_team_type == "HOBBY":
                    hobby_teams_updated += 1
                else:
                    competitive_teams_updated += 1

                if not args.dry_run:
                    # Update the teamType in the database
                    update_path = f"teams.{team_idx}.teamType"
                    db_clubs.update_one(
                        {"_id": club["_id"]}, {"$set": {update_path: expected_team_type}}
                    )

    print()
    print("=" * 60)
    print("UPDATING PLAYERS COLLECTION")
    print("=" * 60)

    # Statistics for players
    total_players = 0
    players_modified = 0
    player_hobby_teams_updated = 0
    player_competitive_teams_updated = 0

    # Get all players
    all_players = db.players.find({})

    for player in all_players:
        total_players += 1
        player_modified = False
        player_name = f"{player.get('firstName', '')} {player.get('lastName', '')}"

        # Loop through assignedTeams (clubs)
        for club_idx, club in enumerate(player.get("assignedTeams", [])):
            # Loop through teams within each club
            for team_idx, team in enumerate(club.get("teams", [])):
                team_alias = team.get("teamAlias")
                current_team_type = team.get("teamType")

                # Determine the expected teamType based on teamAlias
                if team_alias == "1-hobby":
                    expected_team_type = "HOBBY"
                else:
                    expected_team_type = "COMPETITIVE"

                # Only update if teamType doesn't match expected value
                if current_team_type != expected_team_type:
                    if not player_modified:
                        players_modified += 1
                        player_modified = True
                        print(f"Player: {player_name}")

                    print(f"  - Team: {team.get('teamName')} (alias: {team_alias})")
                    print(
                        f"    Current teamType: {current_team_type} -> Setting to {expected_team_type}"
                    )

                    if expected_team_type == "HOBBY":
                        player_hobby_teams_updated += 1
                    else:
                        player_competitive_teams_updated += 1

                    if not args.dry_run:
                        # Update the teamType in the database
                        update_path = f"assignedTeams.{club_idx}.teams.{team_idx}.teamType"
                        db.players.update_one(
                            {"_id": player["_id"]}, {"$set": {update_path: expected_team_type}}
                        )

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Clubs processed: {total_clubs}")
    print(f"Clubs with updates: {clubs_modified}")
    print(f"Club teams set to HOBBY: {hobby_teams_updated}")
    print(f"Club teams set to COMPETITIVE: {competitive_teams_updated}")
    print(f"Total club teams updated: {hobby_teams_updated + competitive_teams_updated}")
    print()
    print(f"Players processed: {total_players}")
    print(f"Players with updates: {players_modified}")
    print(f"Player teams set to HOBBY: {player_hobby_teams_updated}")
    print(f"Player teams set to COMPETITIVE: {player_competitive_teams_updated}")
    print(
        f"Total player teams updated: {player_hobby_teams_updated + player_competitive_teams_updated}"
    )

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
