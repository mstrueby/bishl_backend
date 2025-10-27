#!/usr/bin/env python
import argparse
import os

import certifi
from pymongo import MongoClient

# Set up argument parser
parser = argparse.ArgumentParser(description='Merge two players.')
parser.add_argument('--prod',
                   action='store_true',
                   help='Update production database.')
parser.add_argument('--from_player_id',
                   required=True,
                   help='Player ID to merge from')
parser.add_argument('--to_player_id',
                   required=True,
                   help='Player ID to merge into')
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

async def merge_players():
    # Get target player info
    to_player = db['players'].find_one({"_id": args.to_player_id})
    if not to_player:
        print(f"Target player {args.to_player_id} not found")
        return

    first_name = to_player['firstName']
    last_name = to_player['lastName']

    # Get source player info
    from_player = db['players'].find_one({"_id": args.from_player_id})
    if not from_player:
        print(f"Source player {args.from_player_id} not found")
        return

    # Update rosters
    roster_result = db['matches'].update_many(
        {
            "$or": [
                {"home.roster.player.playerId": args.from_player_id},
                {"away.roster.player.playerId": args.from_player_id}
            ]
        },
        {
            "$set": {
                "home.roster.$[elem].player.playerId": args.to_player_id,
                "home.roster.$[elem].player.firstName": first_name,
                "home.roster.$[elem].player.lastName": last_name,
                "away.roster.$[elem].player.playerId": args.to_player_id,
                "away.roster.$[elem].player.firstName": first_name,
                "away.roster.$[elem].player.lastName": last_name
            }
        },
        array_filters=[{"elem.player.playerId": args.from_player_id}]
    )

    # Update scores
    scores_result = db['matches'].update_many(
        {
            "$or": [
                {"home.scores.goalPlayer.playerId": args.from_player_id},
                {"home.scores.assistPlayer.playerId": args.from_player_id},
                {"away.scores.goalPlayer.playerId": args.from_player_id},
                {"away.scores.assistPlayer.playerId": args.from_player_id}
            ]
        },
        {
            "$set": {
                "home.scores.$[score].goalPlayer.playerId": args.to_player_id,
                "home.scores.$[score].goalPlayer.firstName": first_name,
                "home.scores.$[score].goalPlayer.lastName": last_name,
                "home.scores.$[score].assistPlayer.playerId": args.to_player_id,
                "home.scores.$[score].assistPlayer.firstName": first_name,
                "home.scores.$[score].assistPlayer.lastName": last_name,
                "away.scores.$[score].goalPlayer.playerId": args.to_player_id,
                "away.scores.$[score].goalPlayer.firstName": first_name,
                "away.scores.$[score].goalPlayer.lastName": last_name,
                "away.scores.$[score].assistPlayer.playerId": args.to_player_id,
                "away.scores.$[score].assistPlayer.firstName": first_name,
                "away.scores.$[score].assistPlayer.lastName": last_name
            }
        },
        array_filters=[{
            "$or": [
                {"score.goalPlayer.playerId": args.from_player_id},
                {"score.assistPlayer.playerId": args.from_player_id}
            ]
        }]
    )

    # Merge stats arrays
    from_stats = from_player.get('stats', [])
    to_stats = to_player.get('stats', [])

    # Combine and deduplicate stats
    merged_stats = to_stats.copy()
    for from_stat in from_stats:
        # Check if stat exists in target player
        exists = False
        for to_stat in merged_stats:
            if (to_stat['tournament']['alias'] == from_stat['tournament']['alias'] and
                to_stat['season']['alias'] == from_stat['season']['alias'] and
                to_stat['round']['alias'] == from_stat['round']['alias'] and
                to_stat['team']['name'] == from_stat['team']['name']):
                # Merge stats
                to_stat['gamesPlayed'] += from_stat['gamesPlayed']
                to_stat['goals'] += from_stat['goals']
                to_stat['assists'] += from_stat['assists']
                to_stat['points'] += from_stat['points']
                to_stat['penaltyMinutes'] += from_stat['penaltyMinutes']
                exists = True
                break
        if not exists:
            merged_stats.append(from_stat)

    # Update target player with merged stats
    player_result = db['players'].update_one(
        {"_id": args.to_player_id},
        {"$set": {"stats": merged_stats}}
    )

    # Delete source player
    # delete_result = db['players'].delete_one({"_id": args.from_player_id})

    print("\nMerge Summary:")
    print(f"Modified {roster_result.modified_count} roster entries")
    print(f"Modified {scores_result.modified_count} score entries")
    print("Updated player stats")
    #print(f"Deleted source player: {delete_result.deleted_count == 1}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(merge_players())
