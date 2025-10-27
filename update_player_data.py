#!/usr/bin/env python
import argparse
import os

import certifi
from pymongo import MongoClient

# Set up argument parser
parser = argparse.ArgumentParser(description="Update player data in matches.")
parser.add_argument("--prod", action="store_true", help="Update production database.")
parser.add_argument("--player_id", required=True, help="Player ID to update")
parser.add_argument("--first_name", required=True, help="New first name")
parser.add_argument("--last_name", required=True, help="New last name")
parser.add_argument("--new_player_id", required=False, help="New player ID to update")
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


# Update function
async def update_player_info():
    update_fields = {
        "home.roster.$[elem].player.firstName": args.first_name,
        "home.roster.$[elem].player.lastName": args.last_name,
        "away.roster.$[elem].player.firstName": args.first_name,
        "away.roster.$[elem].player.lastName": args.last_name,
    }

    if args.new_player_id:
        update_fields.update(
            {
                "home.roster.$[elem].player.playerId": args.new_player_id,
                "away.roster.$[elem].player.playerId": args.new_player_id,
            }
        )

    # Update player info in rosters
    roster_result = await db["matches"].update_many(
        {
            "$or": [
                {"home.roster.player.playerId": args.player_id},
                {"away.roster.player.playerId": args.player_id},
            ]
        },
        {"$set": update_fields},
        array_filters=[{"elem.player.playerId": args.player_id}],
    )

    # Update player info in scores
    scores_update = {
        "home.scores.$[score].goalPlayer.firstName": args.first_name,
        "home.scores.$[score].goalPlayer.lastName": args.last_name,
        "home.scores.$[score].assistPlayer.firstName": args.first_name,
        "home.scores.$[score].assistPlayer.lastName": args.last_name,
        "away.scores.$[score].goalPlayer.firstName": args.first_name,
        "away.scores.$[score].goalPlayer.lastName": args.last_name,
        "away.scores.$[score].assistPlayer.firstName": args.first_name,
        "away.scores.$[score].assistPlayer.lastName": args.last_name,
    }

    if args.new_player_id:
        scores_update.update(
            {
                "home.scores.$[score].goalPlayer.playerId": args.new_player_id,
                "home.scores.$[score].assistPlayer.playerId": args.new_player_id,
                "away.scores.$[score].goalPlayer.playerId": args.new_player_id,
                "away.scores.$[score].assistPlayer.playerId": args.new_player_id,
            }
        )

    scores_result = await db["matches"].update_many(
        {
            "$or": [
                {"home.scores.goalPlayer.playerId": args.player_id},
                {"home.scores.assistPlayer.playerId": args.player_id},
                {"away.scores.goalPlayer.playerId": args.player_id},
                {"away.scores.assistPlayer.playerId": args.player_id},
            ]
        },
        {"$set": scores_update},
        array_filters=[
            {
                "$or": [
                    {"score.goalPlayer.playerId": args.player_id},
                    {"score.assistPlayer.playerId": args.player_id},
                ]
            }
        ],
    )

    # Update player info in penalties
    penalties_update = {
        "home.penalties.$[penalty].penaltyPlayer.firstName": args.first_name,
        "home.penalties.$[penalty].penaltyPlayer.lastName": args.last_name,
        "away.penalties.$[penalty].penaltyPlayer.firstName": args.first_name,
        "away.penalties.$[penalty].penaltyPlayer.lastName": args.last_name,
    }

    if args.new_player_id:
        penalties_update.update(
            {
                "home.penalties.$[penalty].penaltyPlayer.playerId": args.new_player_id,
                "away.penalties.$[penalty].penaltyPlayer.playerId": args.new_player_id,
            }
        )

    penalties_result = await db["matches"].update_many(
        {
            "$or": [
                {"home.penalties.penaltyPlayer.playerId": args.player_id},
                {"away.penalties.penaltyPlayer.playerId": args.player_id},
            ]
        },
        {"$set": penalties_update},
        array_filters=[{"penalty.penaltyPlayer.playerId": args.player_id}],
    )

    print("\nUpdate Summary:")
    print(f"Modified {roster_result.modified_count} roster entries")
    print(f"Modified {scores_result.modified_count} score entries")
    print(f"Modified {penalties_result.modified_count} penalty entries")


if __name__ == "__main__":
    import asyncio

    asyncio.run(update_player_info())
