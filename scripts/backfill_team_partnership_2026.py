#!/usr/bin/env python3
"""
One-way migration script: backfill home.teamPartnership and away.teamPartnership
for all matches in the 2026 season (season.alias == "2026").

Matches created before Task #14 do not carry teamPartnership because the field
did not exist in the model at that time.  This script reads the current
teamPartnership from the clubs collection and writes it into each affected
match document.

Usage:
    python scripts/backfill_team_partnership_2026.py [--dry-run] [--production] [--verbose]

Options:
    --dry-run     Preview changes without modifying the database
    --production  Run against production database (uses DB_URL_PROD)
    --verbose     Print per-match per-side resolution details
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
INDEX_SAMPLE_SIZE = 5   # How many index entries to print during diagnosis


# ---------------------------------------------------------------------------
# Database connection
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Index build
# ---------------------------------------------------------------------------

async def build_team_partnership_index(
    db, verbose: bool = False
) -> dict[tuple[str, str], list[dict]]:
    """
    Pre-load all clubs and build a lookup table:
        (club_id_str, team_id_str) -> teamPartnership list

    Uses str() on both IDs so the key format is predictable regardless of
    whether MongoDB stored them as ObjectId or plain string.
    """
    index: dict[tuple[str, str], list[dict]] = {}
    clubs_scanned = 0
    teams_indexed = 0

    async for club in db["clubs"].find({}, {"_id": 1, "alias": 1, "teams": 1}):
        clubs_scanned += 1
        raw_club_id = club["_id"]
        club_id = str(raw_club_id)
        club_alias = club.get("alias", "?")

        for team in club.get("teams", []):
            raw_team_id = team.get("_id", "")
            team_id = str(raw_team_id) if raw_team_id else ""
            if not team_id:
                if verbose:
                    print(f"    SKIP  club={club_alias!r}: team has no _id — {team.get('alias','?')!r}")
                continue

            key = (club_id, team_id)
            index[key] = team.get("teamPartnership", [])
            teams_indexed += 1

            if verbose and teams_indexed <= INDEX_SAMPLE_SIZE:
                tp = index[key]
                tp_summary = (
                    f"{len(tp)} partner(s): "
                    + ", ".join(p.get("teamAlias", "?") for p in tp)
                    if tp else "no partners"
                )
                print(
                    f"    IDX   club={club_alias!r} ({type(raw_club_id).__name__} {club_id!r})"
                    f"  team={team.get('alias','?')!r} ({type(raw_team_id).__name__} {team_id!r})"
                    f"  → {tp_summary}"
                )

    if verbose and teams_indexed > INDEX_SAMPLE_SIZE:
        print(f"    … {teams_indexed - INDEX_SAMPLE_SIZE} more teams not shown")

    print(
        f"  → {clubs_scanned} club(s) scanned, "
        f"{teams_indexed} team(s) indexed."
    )
    return index


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def resolve_partnership(
    index: dict[tuple[str, str], list[dict]],
    club_id: str | None,
    team_id: str | None,
) -> list[dict] | None:
    """
    Return the teamPartnership list for a given club+team pair, or None if
    the club/team could not be found.

    Distinguishes three outcomes:
      - None   → IDs were blank or not present in index at all
      - []     → found but team has no partners
      - [...]  → found and team has at least one partner
    """
    if not club_id or not team_id:
        return None
    return index.get((str(club_id), str(team_id)))


def already_has_partnership(team_data: dict) -> bool:
    """True if the match team document already carries a teamPartnership field."""
    return "teamPartnership" in team_data


def fmt_side(side: str, team_data: dict) -> str:
    """Format a compact identifier string for a match side."""
    return (
        f"{side}("
        f"clubId={team_data.get('clubId')!r}, "
        f"teamId={team_data.get('teamId')!r}, "
        f"alias={team_data.get('teamAlias')!r})"
    )


# ---------------------------------------------------------------------------
# Migration core
# ---------------------------------------------------------------------------

async def run_migration(
    dry_run: bool = False,
    use_production: bool = False,
    verbose: bool = False,
):
    print(f"\n{'=' * 70}")
    print(f"Backfill teamPartnership — season {SEASON_ALIAS}")
    print(f"{'=' * 70}")
    print(f"Mode:    {'DRY RUN (no writes)' if dry_run else 'LIVE'}")
    print(f"Target:  {'PRODUCTION' if use_production else 'DEVELOPMENT'}")
    print(f"Verbose: {verbose}")
    print(f"Started: {datetime.now().isoformat()}")
    print(f"{'=' * 70}\n")

    db = await get_database(use_production)

    # ------------------------------------------------------------------
    # 1. Build index — sample a few entries so we can verify ID format
    # ------------------------------------------------------------------
    print("Building club/team partnership index …")
    if verbose:
        print(f"  (showing first {INDEX_SAMPLE_SIZE} entries)")
    partnership_index = await build_team_partnership_index(db, verbose=verbose)
    print()

    # Cross-check: how many teams in the index actually have partners?
    with_partners = sum(1 for v in partnership_index.values() if v)
    without_partners = len(partnership_index) - with_partners
    print(f"  Index breakdown:")
    print(f"    Teams WITH  at least one partner : {with_partners}")
    print(f"    Teams WITHOUT any partner        : {without_partners}")
    print()

    # ------------------------------------------------------------------
    # 2. Sample a match from the DB to cross-check ID format
    # ------------------------------------------------------------------
    sample_match = await db["matches"].find_one({"season.alias": SEASON_ALIAS})
    if sample_match:
        print("Sample match (for ID format cross-check):")
        for side in ("home", "away"):
            td = sample_match.get(side) or {}
            raw_cid = td.get("clubId")
            raw_tid = td.get("teamId")
            cid = str(raw_cid) if raw_cid else None
            tid = str(raw_tid) if raw_tid else None
            found = resolve_partnership(partnership_index, cid, tid)
            status = (
                "NOT IN INDEX" if found is None
                else f"found — {len(found)} partner(s)"
            )
            print(
                f"  {side}: clubId={raw_cid!r} ({type(raw_cid).__name__}), "
                f"teamId={raw_tid!r} ({type(raw_tid).__name__}) → {status}"
            )
        print()

    # ------------------------------------------------------------------
    # 3. Process all 2026 matches
    # ------------------------------------------------------------------
    query = {"season.alias": SEASON_ALIAS}
    total_count = await db["matches"].count_documents(query)
    print(f"Total matches with season.alias == {SEASON_ALIAS!r}: {total_count}\n")

    # Counters
    already_done = 0          # both sides already have the field
    updated_with_data = 0     # at least one side resolved to a non-empty list
    updated_empty_only = 0    # updated but all sides resolved to []
    partially_done = 0        # one side already had field, other was missing
    unresolvable = 0          # at least one side could not be looked up
    errors = 0

    async for match in db["matches"].find(query):
        match_id = match["_id"]
        updates: dict[str, list] = {}
        unresolved_sides: list[str] = []
        already_done_sides: list[str] = []
        resolved_details: list[str] = []   # for verbose logging

        for side in ("home", "away"):
            team_data: dict = match.get(side) or {}

            # Skip sides that already carry the field
            if already_has_partnership(team_data):
                already_done_sides.append(side)
                resolved_details.append(
                    f"    {side}: SKIP (teamPartnership already present, "
                    f"{len(team_data['teamPartnership'])} entries)"
                )
                continue

            club_id = team_data.get("clubId")
            team_id = team_data.get("teamId")

            partnership = resolve_partnership(partnership_index, club_id, team_id)

            if partnership is None:
                unresolved_sides.append(fmt_side(side, team_data))
                resolved_details.append(
                    f"    {side}: WARN — clubId={club_id!r} / teamId={team_id!r} "
                    f"not found in index"
                )
            else:
                updates[f"{side}.teamPartnership"] = partnership
                n = len(partnership)
                partners = (
                    ", ".join(p.get("teamAlias", "?") for p in partnership)
                    if partnership else "none"
                )
                resolved_details.append(
                    f"    {side}: OK  → {n} partner(s): [{partners}]  "
                    f"(clubId={club_id!r}, teamId={team_id!r})"
                )

        # Diagnostics: did we find anything?
        if unresolved_sides:
            unresolvable += 1
            print(
                f"  WARN  match {match_id}: could not resolve "
                + ", ".join(unresolved_sides)
            )

        # Determine skip / partial / full scenarios
        all_sides_done = len(already_done_sides) == 2
        if all_sides_done:
            already_done += 1
            if verbose:
                print(f"  SKIP  match {match_id}: both sides already have teamPartnership")
                for d in resolved_details:
                    print(d)
            continue

        if not updates:
            # No new data to write (all remaining sides were unresolvable)
            if verbose:
                print(f"  SKIP  match {match_id}: nothing to write (unresolvable or already done)")
                for d in resolved_details:
                    print(d)
            continue

        if already_done_sides:
            partially_done += 1

        # Classify by whether any resolved side has actual partners
        has_real_partners = any(len(v) > 0 for v in updates.values())

        try:
            if not dry_run:
                await db["matches"].update_one(
                    {"_id": match_id},
                    {"$set": updates},
                )
            sides_updated = [k.split(".")[0] for k in updates]
            partner_counts = {
                k.split(".")[0]: len(v) for k, v in updates.items()
            }
            prefix = "[DRY RUN]" if dry_run else "[UPDATED]"

            if has_real_partners:
                updated_with_data += 1
                print(
                    f"  {prefix} match {match_id}: sides={sides_updated}"
                    f"  partners={partner_counts}"
                )
            else:
                updated_empty_only += 1
                if verbose:
                    print(
                        f"  {prefix} match {match_id}: sides={sides_updated}"
                        f"  (all empty partnerships)"
                    )

            if verbose:
                for d in resolved_details:
                    print(d)

        except Exception as exc:
            errors += 1
            print(f"  ERROR match {match_id}: {exc}")

    # ------------------------------------------------------------------
    # 4. Final summary
    # ------------------------------------------------------------------
    print(f"\n{'=' * 70}")
    print("Backfill complete")
    print(f"{'=' * 70}")
    print(f"Total 2026 matches                       : {total_count}")
    print(f"")
    print(f"Already up-to-date (field existed)       : {already_done}")
    print(f"")
    print(f"Written — with real partner data         : {updated_with_data}")
    print(f"Written — empty list only (no partners)  : {updated_empty_only}")
    print(f"Written — one side already done          : {partially_done}  (subset of above two)")
    print(f"")
    print(f"Unresolvable (club/team not in index)    : {unresolvable}")
    print(f"Errors                                   : {errors}")
    print(f"{'=' * 70}\n")

    if dry_run:
        print("Dry run — no changes written to the database.")
        print("Re-run without --dry-run to apply.\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

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
    parser.add_argument(
        "--verbose",
        action="store_true",
        help=(
            "Print per-match per-side resolution details and sample index entries. "
            "Use with --dry-run to diagnose ID mismatches before writing."
        ),
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

    asyncio.run(
        run_migration(
            dry_run=args.dry_run,
            use_production=args.production,
            verbose=args.verbose,
        )
    )


if __name__ == "__main__":
    main()
