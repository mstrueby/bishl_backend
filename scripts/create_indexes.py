
"""
MongoDB Index Creation Script

Run this to create all necessary indexes for optimal query performance.
Should be run once after deployment and whenever index strategy changes.

Usage:
    python scripts/create_indexes.py
"""

from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
import os
from logging_config import logger

async def create_indexes():
    """Create all necessary indexes for optimal query performance"""
    
    client = AsyncIOMotorClient(os.environ['DB_URL'])
    db = client[os.environ['DB_NAME']]
    
    logger.info("Starting index creation...")
    
    try:
        # Matches indexes
        logger.info("Creating matches collection indexes...")
        await db.matches.create_index([
            ("tournament.alias", 1),
            ("season.alias", 1),
            ("round.alias", 1)
        ], name="tournament_season_round_idx", background=True)
        
        await db.matches.create_index([
            ("tournament.alias", 1),
            ("season.alias", 1),
            ("matchday.alias", 1)
        ], name="tournament_season_matchday_idx", background=True)
        
        await db.matches.create_index(
            [("status", 1), ("startDate", 1)], 
            name="status_startdate_idx",
            background=True
        )
        
        await db.matches.create_index(
            [("home.teamId", 1)], 
            name="home_team_idx",
            background=True
        )
        
        await db.matches.create_index(
            [("away.teamId", 1)], 
            name="away_team_idx",
            background=True
        )
        
        # Players indexes
        logger.info("Creating players collection indexes...")
        await db.players.create_index(
            [("alias", 1)], 
            unique=True, 
            name="alias_unique_idx",
            background=True
        )
        
        await db.players.create_index([
            ("lastName", 1),
            ("firstName", 1),
            ("yearOfBirth", 1)
        ], name="player_lookup_idx", background=True)
        
        await db.players.create_index(
            [("assignedClubs.clubId", 1)], 
            name="assigned_clubs_idx",
            background=True
        )
        
        # Tournaments indexes
        logger.info("Creating tournaments collection indexes...")
        await db.tournaments.create_index(
            [("alias", 1)], 
            unique=True, 
            name="tournament_alias_unique_idx",
            background=True
        )
        
        # Users indexes
        logger.info("Creating users collection indexes...")
        await db.users.create_index(
            [("email", 1)], 
            unique=True, 
            name="email_unique_idx",
            background=True
        )
        
        await db.users.create_index(
            [("club.clubId", 1)], 
            name="club_idx",
            background=True
        )
        
        # Assignments indexes
        logger.info("Creating assignments collection indexes...")
        await db.assignments.create_index(
            [("matchId", 1)], 
            name="match_idx",
            background=True
        )
        
        await db.assignments.create_index(
            [("userId", 1)], 
            name="user_idx",
            background=True
        )
        
        await db.assignments.create_index(
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
