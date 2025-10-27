#!/usr/bin/env python
"""
Helper script to find suitable matches for testing roster stats calculation.
"""
import asyncio
import os

import certifi
from motor.motor_asyncio import AsyncIOMotorClient

DB_URL = os.environ["DB_URL"]
DB_NAME = os.environ["DB_NAME"]


async def find_test_matches():
    """Find matches with roster data, scores, and penalties for testing"""
    client = AsyncIOMotorClient(DB_URL, tlsCAFile=certifi.where())
    mongodb = client[DB_NAME]

    print("\n🔍 Finding suitable test matches...\n")

    # Find finished matches with rosters, scores, and penalties
    matches = await mongodb['matches'].find({
        'matchStatus.key': 'FINISHED',
        'home.roster.0': {'$exists': True},
        'away.roster.0': {'$exists': True},
        'home.scores.0': {'$exists': True}  # Has at least one goal
    }).limit(10).to_list(length=10)

    if not matches:
        print("❌ No suitable matches found")
        client.close()
        return

    print(f"Found {len(matches)} suitable test matches:\n")
    print("-" * 100)

    for i, match in enumerate(matches, 1):
        home_roster = len(match.get('home', {}).get('roster', []))
        away_roster = len(match.get('away', {}).get('roster', []))
        home_scores = len(match.get('home', {}).get('scores', []))
        away_scores = len(match.get('away', {}).get('scores', []))
        home_penalties = len(match.get('home', {}).get('penalties', []))
        away_penalties = len(match.get('away', {}).get('penalties', []))

        # Calculate total stats in roster
        home_goals = sum(p.get('goals', 0) for p in match.get('home', {}).get('roster', []))
        away_goals = sum(p.get('goals', 0) for p in match.get('away', {}).get('roster', []))
        home_pims = sum(p.get('penaltyMinutes', 0) for p in match.get('home', {}).get('roster', []))
        away_pims = sum(p.get('penaltyMinutes', 0) for p in match.get('away', {}).get('roster', []))

        print(f"{i}. Match ID: {match['_id']}")
        print(f"   {match['home']['fullName']} vs {match['away']['fullName']}")
        print(f"   Tournament: {match.get('tournament', {}).get('name', 'N/A')}")
        print(f"   Date: {match.get('startDate', 'N/A')}")
        print(f"   Rosters: Home={home_roster}, Away={away_roster}")
        print(f"   Scores: Home={home_scores}, Away={away_scores}")
        print(f"   Penalties: Home={home_penalties}, Away={away_penalties}")
        print(f"   Current roster stats: Home G={home_goals} PIM={home_pims}, Away G={away_goals} PIM={away_pims}")
        print()

    print("-" * 100)
    print("\n💡 To test with a specific match, run:")
    print(f"   TEST_MATCH_ID={matches[0]['_id']} python validate_stats_refactoring.py")
    print("\n💡 To run without modifying database:")
    print("   DRY_RUN=true python validate_stats_refactoring.py")

    client.close()


if __name__ == "__main__":
    asyncio.run(find_test_matches())
