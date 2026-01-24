#!/usr/bin/env python3
"""
Migration script to convert existing match documents from flat roster structure
to the new nested roster structure.

Old structure (at match.team level):
- roster: [RosterPlayer, ...]
- rosterStatus: "DRAFT"
- rosterPublished: false
- eligibilityTimestamp: null
- eligibilityValidator: null
- coach: {}
- staff: []

New structure (at match.team.roster level):
- roster: {
    players: [RosterPlayer, ...],
    status: "DRAFT",
    published: false,
    eligibilityTimestamp: null,
    eligibilityValidator: null,
    coach: {},
    staff: []
  }

Usage:
    python scripts/migrate_roster_structure.py [--dry-run] [--production]

Options:
    --dry-run     Preview changes without modifying the database
    --production  Run against production database (uses DB_URL_PROD)
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime

import certifi
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def get_database(use_production: bool = False):
    """Connect to MongoDB."""
    if use_production:
        db_url = os.getenv("DB_URL_PROD")
        db_name = "bishl"
    else:
        db_url = os.getenv("DB_URL")
        db_name = os.getenv("DB_NAME", "bishl_dev")

    if not db_url:
        raise ValueError(f"Database URL not found. Set {'DB_URL_PROD' if use_production else 'DB_URL'} environment variable.")

    client = AsyncIOMotorClient(db_url, tlsCAFile=certifi.where())
    return client[db_name]


def needs_migration(team_data: dict) -> bool:
    """Check if a team's data needs migration to new roster structure."""
    if not team_data:
        return False
    
    roster = team_data.get("roster")
    
    # Already migrated: roster is a dict with 'players' key
    if isinstance(roster, dict) and "players" in roster:
        return False
    
    # Needs migration: roster is a list OR old flat fields exist
    if isinstance(roster, list):
        return True
    
    # Check for old flat fields
    old_fields = ["rosterStatus", "rosterPublished", "eligibilityTimestamp", "eligibilityValidator"]
    return any(field in team_data for field in old_fields)


def migrate_team_roster(team_data: dict) -> dict:
    """Migrate a single team's roster to new nested structure."""
    if not team_data:
        return team_data
    
    roster = team_data.get("roster")
    
    # Already migrated
    if isinstance(roster, dict) and "players" in roster:
        return team_data
    
    # Build new roster structure
    new_roster = {
        "players": roster if isinstance(roster, list) else [],
        "status": team_data.pop("rosterStatus", "DRAFT"),
        "published": team_data.pop("rosterPublished", False),
        "eligibilityTimestamp": team_data.pop("eligibilityTimestamp", None),
        "eligibilityValidator": team_data.pop("eligibilityValidator", None),
        "coach": team_data.pop("coach", {}),
        "staff": team_data.pop("staff", []),
    }
    
    team_data["roster"] = new_roster
    return team_data


async def migrate_match(db, match: dict, dry_run: bool = False) -> dict:
    """Migrate a single match document."""
    match_id = match["_id"]
    updates = {}
    
    for team_flag in ["home", "away"]:
        team_data = match.get(team_flag)
        if team_data and needs_migration(team_data):
            migrated_team = migrate_team_roster(team_data.copy())
            updates[team_flag] = migrated_team
    
    if updates and not dry_run:
        await db["matches"].update_one(
            {"_id": match_id},
            {"$set": updates}
        )
    
    return updates


async def run_migration(dry_run: bool = False, use_production: bool = False):
    """Run the migration."""
    print(f"\n{'=' * 60}")
    print(f"Roster Structure Migration")
    print(f"{'=' * 60}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print(f"Target: {'PRODUCTION' if use_production else 'DEVELOPMENT'}")
    print(f"Started: {datetime.now().isoformat()}")
    print(f"{'=' * 60}\n")
    
    db = await get_database(use_production)
    
    # Count total matches
    total_count = await db["matches"].count_documents({})
    print(f"Total matches in database: {total_count}")
    
    # Find matches that need migration
    matches_cursor = db["matches"].find({})
    
    migrated_count = 0
    skipped_count = 0
    error_count = 0
    
    async for match in matches_cursor:
        match_id = match["_id"]
        home_needs = needs_migration(match.get("home", {}))
        away_needs = needs_migration(match.get("away", {}))
        
        if not home_needs and not away_needs:
            skipped_count += 1
            continue
        
        try:
            updates = await migrate_match(db, match, dry_run)
            if updates:
                migrated_count += 1
                teams_updated = list(updates.keys())
                if dry_run:
                    print(f"  [DRY RUN] Would migrate match {match_id}: {teams_updated}")
                else:
                    print(f"  Migrated match {match_id}: {teams_updated}")
        except Exception as e:
            error_count += 1
            print(f"  ERROR migrating match {match_id}: {e}")
    
    print(f"\n{'=' * 60}")
    print(f"Migration Complete")
    print(f"{'=' * 60}")
    print(f"Total matches:    {total_count}")
    print(f"Migrated:         {migrated_count}")
    print(f"Already up-to-date: {skipped_count}")
    print(f"Errors:           {error_count}")
    print(f"{'=' * 60}\n")
    
    if dry_run:
        print("This was a dry run. No changes were made to the database.")
        print("Run without --dry-run to apply changes.\n")


def main():
    parser = argparse.ArgumentParser(
        description="Migrate match roster structure to nested format"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying the database"
    )
    parser.add_argument(
        "--production",
        action="store_true",
        help="Run against production database"
    )
    
    args = parser.parse_args()
    
    if args.production and not args.dry_run:
        confirm = input("\n⚠️  WARNING: You are about to modify PRODUCTION data.\nType 'yes' to continue: ")
        if confirm.lower() != "yes":
            print("Aborted.")
            return
    
    asyncio.run(run_migration(dry_run=args.dry_run, use_production=args.production))


if __name__ == "__main__":
    main()
