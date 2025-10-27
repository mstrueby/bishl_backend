
"""
MongoDB Index Creation Script

Run this to create all necessary indexes for optimal query performance.
Should be run once after deployment and whenever index strategy changes.

Usage:
    python scripts/create_indexes.py [--prod]
"""

import sys
from pathlib import Path

# Add parent directory to Python path to allow importing from root
sys.path.insert(0, str(Path(__file__).parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
import os
import argparse
from logging_config import logger
from pymongo.errors import OperationFailure

# Set up argument parser
parser = argparse.ArgumentParser(description='Create MongoDB indexes.')
parser.add_argument('--prod',
                    action='store_true',
                    help='Create indexes in production database.')
args = parser.parse_args()

# Get environment variables based on --prod flag
if args.prod:
    DB_URL = os.environ['DB_URL_PROD']
    DB_NAME = 'bishl'
else:
    DB_URL = os.environ['DB_URL']
    DB_NAME = 'bishl_dev'

print("DB_URL:", DB_URL)
print("DB_NAME:", DB_NAME)

async def create_indexes():
    """Create all necessary indexes for optimal query performance"""
    
    client = AsyncIOMotorClient(DB_URL)
    db = client[DB_NAME]
    
    logger.info(f"Starting index creation for database: {DB_NAME}...")
    
    async def create_index_safe(collection, keys, **kwargs):
        """Helper to create index and skip if already exists"""
        index_name = kwargs.get('name', 'unnamed')
        try:
            await collection.create_index(keys, **kwargs)
            logger.info(f"  ✓ Created index: {index_name}")
        except OperationFailure as e:
            if "already exists" in str(e) or "IndexOptionsConflict" in str(e):
                logger.info(f"  ↷ Index already exists: {index_name}")
            else:
                logger.error(f"  ✗ Failed to create index {index_name}: {str(e)}")
                raise
    
    try:
        # Matches indexes
        logger.info("Creating matches collection indexes...")
        await create_index_safe(db.matches, [
            ("tournament.alias", 1),
            ("season.alias", 1),
            ("round.alias", 1)
        ], name="tournament_season_round_idx", background=True)
        
        await create_index_safe(db.matches, [
            ("tournament.alias", 1),
            ("season.alias", 1),
            ("matchday.alias", 1)
        ], name="tournament_season_matchday_idx", background=True)
        
        await create_index_safe(db.matches,
            [("status", 1), ("startDate", 1)], 
            name="status_startdate_idx",
            background=True
        )
        
        await create_index_safe(db.matches,
            [("home.teamId", 1)], 
            name="home_team_idx",
            background=True
        )
        
        await create_index_safe(db.matches,
            [("away.teamId", 1)], 
            name="away_team_idx",
            background=True
        )
        
        # Players indexes
        logger.info("Creating players collection indexes...")
        await create_index_safe(db.players,
            [("alias", 1)], 
            unique=True, 
            name="alias_unique_idx",
            background=True
        )
        
        await create_index_safe(db.players, [
            ("lastName", 1),
            ("firstName", 1),
            ("yearOfBirth", 1)
        ], name="player_lookup_idx", background=True)
        
        await create_index_safe(db.players,
            [("assignedClubs.clubId", 1)], 
            name="assigned_clubs_idx",
            background=True
        )
        
        # Tournaments indexes
        logger.info("Creating tournaments collection indexes...")
        await create_index_safe(db.tournaments,
            [("alias", 1)], 
            unique=True, 
            name="tournament_alias_unique_idx",
            background=True
        )
        
        # Users indexes
        logger.info("Creating users collection indexes...")
        await create_index_safe(db.users,
            [("email", 1)], 
            unique=True, 
            name="email_unique_idx",
            background=True
        )
        
        await create_index_safe(db.users,
            [("club.clubId", 1)], 
            name="club_idx",
            background=True
        )
        
        # Assignments indexes
        logger.info("Creating assignments collection indexes...")
        await create_index_safe(db.assignments,
            [("matchId", 1)], 
            name="match_idx",
            background=True
        )
        
        await create_index_safe(db.assignments,
            [("userId", 1)], 
            name="user_idx",
            background=True
        )
        
        await create_index_safe(db.assignments,
            [("status", 1)], 
            name="status_idx",
            background=True
        )
        
        logger.info("Index creation completed successfully")
        
        # List all indexes for verification
        logger.info("\nVerifying created indexes:")
        for collection_name in ["matches", "players", "tournaments", "users", "assignments"]:
            indexes = await db[collection_name].index_information()
            logger.info(f"\n{collection_name} indexes:")
            for idx_name, idx_info in indexes.items():
                logger.info(f"  - {idx_name}: {idx_info.get('key', [])}")
        
    except Exception as e:
        logger.error(f"Error creating indexes: {str(e)}")
        raise
    finally:
        client.close()

if __name__ == "__main__":
    asyncio.run(create_indexes())
