#!/usr/bin/env python3
"""
One-way migration script: backfill home.teamPartnership and away.teamPartnership
for all matches in the 2026 season (season.alias == "2026").

Matches created before Task #14 do not carry teamPartnership because the field
did not exist in the model at that time.  This script reads the current
teamPartnership from the clubs collection and writes it into each affected
match document.

Usage:
    python scripts/backfill_team_partnership_2026.py [--dry-run] [--production]

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

SEASON_ALIAS = "2026"


async def get_database(use_production: bool = False):
    """Connect to MongoDB and return the target database."""
    if use_production:
        db_url = os.getenv("DB_URL_PROD")
        db_name = "bishl"
    else:
        db_url = os.getenv("DB_URL")
        db_name = os.getenv("DB_NAME", "bishl_dev")

    if not db_url:
        raise ValueError(
            f"Database URL not found. "
            f"Set {'DB_URL_PROD' if use_production else 'DB_URL'} environment variable."
        )

    client = AsyncIOMotorClient(db_url, tlsCAFile=certifi.where())
    return client[db_name]


async def build_team_partnership_index(db) -> dict[tuple[str, str], list[dict]]:
    """
    Pre-load all clubs and build a lookup table:
        (club_id, team_id) -> teamPartnership list
    This avoids repeated per-match DB calls.
    """
    index: dict[tuple[str, str], list[dict]] = {}
    async for club in db["clubs"].find({}, {"_id": 1, "teams": 1}):
        club_id = str(club["_id"])
        for team in club.get("teams", []):
            team_id = str(team.get("_id", ""))
            if team_id:
                key = (club_id, team_id)
                index[key] = team.get("teamPartnership", [])
    return index


def resolve_partnership(
    index: dict[tuple[str, str], list[dict]],
    club_id: str | None,
    team_id: str | None,
) -> list[dict] | None:
    """
    Return the teamPartnership list for a given club+team pair, or None if
    the club/team could not be found (distinguishes "found, empty list" from
    "not found").
    """
    if not club_id or not team_id:
        return None
    return index.get((club_id, team_id))  # None when key is absent


def already_has_partnership(team_data: dict) -> bool:
    """True if the match team document already carries a teamPartnership field."""
    return "teamPartnership" in team_data


async def run_migration(dry_run: bool = False, use_production: bool = False):
    print(f"\n{'=' * 60}")
    print(f"Backfill teamPartnership — season {SEASON_ALIAS}")
    print(f"{'=' * 60}")
    print(f"Mode:    {'DRY RUN (no writes)' if dry_run else 'LIVE'}")
    print(f"Target:  {'PRODUCTION' if use_production else 'DEVELOPMENT'}")
    print(f"Started: {datetime.now().isoformat()}")
    print(f"{'=' * 60}\n")

    db = await get_database(use_production)

    # Pre-load club partnership data
    print("Building club/team partnership index …")
    partnership_index = await build_team_partnership_index(db)
    print(f"  → {len(partnership_index)} team entries indexed from clubs collection.\n")

    # Fetch all 2026 matches
    query = {"season.alias": SEASON_ALIAS}
    total_count = await db["matches"].count_documents(query)
    print(f"Matches with season.alias == '{SEASON_ALIAS}': {total_count}\n")

    migrated = 0
    skipped = 0
    not_found = 0
    errors = 0

    async for match in db["matches"].find(query):
        match_id = match["_id"]
        updates: dict[str, list] = {}
        missing_clubs: list[str] = []

        for side in ("home", "away"):
            team_data: dict = match.get(side) or {}

            # Skip sides that already carry the field (already backfilled or
            # created after Task #14 went live)
            if already_has_partnership(team_data):
                continue

            club_id = team_data.get("clubId")
            team_id = team_data.get("teamId")

            partnership = resolve_partnership(partnership_index, club_id, team_id)

            if partnership is None:
                missing_clubs.append(
                    f"{side}(clubId={club_id!r}, teamId={team_id!r})"
                )
                continue

            updates[f"{side}.teamPartnership"] = partnership

        if missing_clubs:
            not_found += 1
            print(
                f"  WARN  match {match_id}: could not resolve club/team for "
                + ", ".join(missing_clubs)
            )

        if not updates:
            skipped += 1
            continue

        try:
            if not dry_run:
                await db["matches"].update_one(
                    {"_id": match_id},
                    {"$set": updates},
                )
            migrated += 1
            sides_updated = [k.split(".")[0] for k in updates]
            prefix = "[DRY RUN] Would update" if dry_run else "Updated"
            print(f"  {prefix} match {match_id}: {sides_updated}")
        except Exception as exc:
            errors += 1
            print(f"  ERROR match {match_id}: {exc}")

    print(f"\n{'=' * 60}")
    print("Backfill complete")
    print(f"{'=' * 60}")
    print(f"Total 2026 matches:        {total_count}")
    print(f"Updated (or would update): {migrated}")
    print(f"Already up-to-date:        {skipped}")
    print(f"Club/team not resolved:    {not_found}")
    print(f"Errors:                    {errors}")
    print(f"{'=' * 60}\n")

    if dry_run:
        print("Dry run — no changes written to the database.")
        print("Re-run without --dry-run to apply.\n")


def main():
    parser = argparse.ArgumentParser(
        description=(
            f"Backfill home/away.teamPartnership for all season {SEASON_ALIAS} matches."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying the database",
    )
    parser.add_argument(
        "--production",
        action="store_true",
        help="Run against production database (DB_URL_PROD)",
    )
    args = parser.parse_args()

    if args.production and not args.dry_run:
        confirm = input(
            "\n⚠️  WARNING: You are about to modify PRODUCTION data.\n"
            "Type 'yes' to continue: "
        )
        if confirm.lower() != "yes":
            print("Aborted.")
            return

    asyncio.run(run_migration(dry_run=args.dry_run, use_production=args.production))


if __name__ == "__main__":
    main()
