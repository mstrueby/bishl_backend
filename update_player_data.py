
#!/usr/bin/env python
import os
import certifi
from pymongo import MongoClient
import argparse
from datetime import datetime

# Set up argument parser
parser = argparse.ArgumentParser(description='Update player data in matches.')
parser.add_argument('--prod',
                   action='store_true',
                   help='Update production database.')
parser.add_argument('--player_id',
                   required=True,
                   help='Player ID to update')
parser.add_argument('--first_name',
                   required=True,
                   help='New first name')
parser.add_argument('--last_name',
                   required=True,
                   help='New last name')
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

# Update function
async def update_player_info():
    # Update player info in rosters
    roster_result = await db['matches'].update_many(
        {
            "$or": [
                {"home.roster.player.playerId": args.player_id},
                {"away.roster.player.playerId": args.player_id}
            ]
        },
        {
            "$set": {
                "home.roster.$[elem].player.firstName": args.first_name,
                "home.roster.$[elem].player.lastName": args.last_name,
                "away.roster.$[elem].player.firstName": args.first_name,
                "away.roster.$[elem].player.lastName": args.last_name
            }
        },
        array_filters=[{"elem.player.playerId": args.player_id}]
    )
    
    # Update player info in scores
    scores_result = await db['matches'].update_many(
        {
            "$or": [
                {"home.scores.goalPlayer.playerId": args.player_id},
                {"home.scores.assistPlayer.playerId": args.player_id},
                {"away.scores.goalPlayer.playerId": args.player_id},
                {"away.scores.assistPlayer.playerId": args.player_id}
            ]
        },
        {
            "$set": {
                "home.scores.$[score].goalPlayer.firstName": args.first_name,
                "home.scores.$[score].goalPlayer.lastName": args.last_name,
                "home.scores.$[score].assistPlayer.firstName": args.first_name,
                "home.scores.$[score].assistPlayer.lastName": args.last_name,
                "away.scores.$[score].goalPlayer.firstName": args.first_name,
                "away.scores.$[score].goalPlayer.lastName": args.last_name,
                "away.scores.$[score].assistPlayer.firstName": args.first_name,
                "away.scores.$[score].assistPlayer.lastName": args.last_name
            }
        },
        array_filters=[
            {
                "$or": [
                    {"score.goalPlayer.playerId": args.player_id},
                    {"score.assistPlayer.playerId": args.player_id}
                ]
            }
        ]
    )

    # Update player info in penalties
    penalties_result = await db['matches'].update_many(
        {
            "$or": [
                {"home.penalties.penaltyPlayer.playerId": args.player_id},
                {"away.penalties.penaltyPlayer.playerId": args.player_id}
            ]
        },
        {
            "$set": {
                "home.penalties.$[penalty].penaltyPlayer.firstName": args.first_name,
                "home.penalties.$[penalty].penaltyPlayer.lastName": args.last_name,
                "away.penalties.$[penalty].penaltyPlayer.firstName": args.first_name,
                "away.penalties.$[penalty].penaltyPlayer.lastName": args.last_name
            }
        },
        array_filters=[{"penalty.penaltyPlayer.playerId": args.player_id}]
    )

    print(f"\nUpdate Summary:")
    print(f"Modified {roster_result.modified_count} roster entries")
    print(f"Modified {scores_result.modified_count} score entries")
    print(f"Modified {penalties_result.modified_count} penalty entries")

if __name__ == "__main__":
    import asyncio
    asyncio.run(update_player_info())
