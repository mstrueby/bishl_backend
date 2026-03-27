#!/usr/bin/env python
"""
Backfill referee.level and referee.assignmentStatus in assignments and matches.

Sources:
  - level         → users.referee.level
  - assignmentStatus → assignments.status (ASSIGNED or ACCEPTED only)

Rules:
  - Assignments: skip UNAVAILABLE; update level where it differs.
  - Matches: only future matches (startDate >= now); update level and/or
    assignmentStatus for referee1/referee2 where either field differs from
    what the corresponding assignment holds.

Usage:
  python backfill_referee_levels.py              # dry-run against dev DB
  python backfill_referee_levels.py --apply      # apply changes to dev DB
  python backfill_referee_levels.py --prod       # dry-run against prod DB
  python backfill_referee_levels.py --prod --apply  # apply changes to prod DB
"""
import argparse
import asyncio
import os
from datetime import UTC, datetime

import certifi
import motor.motor_asyncio
from dotenv import load_dotenv

load_dotenv()


async def backfill(is_prod: bool, dry_run: bool) -> None:
    if is_prod:
        DB_URL = os.environ["DB_URL_PROD"]
        DB_NAME = "bishl"
    else:
        DB_URL = os.environ["DB_URL"]
        DB_NAME = "bishl_dev"

    mode = "DRY-RUN" if dry_run else "APPLY"
    env = "PRODUCTION" if is_prod else "DEVELOPMENT"
    print(f"\n{'='*70}")
    print(f"  Backfill referee levels & assignmentStatus — {env} — {mode}")
    print(f"{'='*70}\n")

    client = motor.motor_asyncio.AsyncIOMotorClient(DB_URL, tlsCAFile=certifi.where())
    db = client[DB_NAME]

    # ------------------------------------------------------------------
    # 1. Build userId → level map from the users collection
    # ------------------------------------------------------------------
    print("Loading referee levels from users...")
    referee_users = (
        await db["users"]
        .find(
            {"roles": "REFEREE"},
            {"_id": 1, "firstName": 1, "lastName": 1, "referee.level": 1},
        )
        .to_list(None)
    )

    level_map: dict[str, str] = {}
    for u in referee_users:
        level = u.get("referee", {}).get("level", "n/a")
        level_map[u["_id"]] = level

    print(f"  Found {len(level_map)} referees in users collection.\n")

    # ------------------------------------------------------------------
    # 2. Update assignments (skip UNAVAILABLE)
    # ------------------------------------------------------------------
    print("Processing assignments...")
    assignments = (
        await db["assignments"]
        .find(
            {"status": {"$ne": "UNAVAILABLE"}},
            {
                "_id": 1,
                "status": 1,
                "referee.userId": 1,
                "referee.level": 1,
                "referee.firstName": 1,
                "referee.lastName": 1,
            },
        )
        .to_list(None)
    )

    asgn_checked = 0
    asgn_updated = 0
    asgn_skipped_no_user = 0
    asgn_already_correct = 0

    for asgn in assignments:
        asgn_checked += 1
        ref = asgn.get("referee", {})
        user_id = ref.get("userId")
        current_level = ref.get("level", "n/a")
        name = f"{ref.get('firstName', '')} {ref.get('lastName', '')}".strip()

        if user_id not in level_map:
            print(
                f"  ⚠️  Assignment {asgn['_id']} — userId {user_id!r} not found in users, skipping"
            )
            asgn_skipped_no_user += 1
            continue

        correct_level = level_map[user_id]

        if current_level == correct_level:
            asgn_already_correct += 1
            continue

        print(
            f"  {'[DRY-RUN] Would update' if dry_run else 'Updating'} assignment {asgn['_id']}"
            f" — {name} — {current_level!r} → {correct_level!r}"
            f" (status: {asgn.get('status')})"
        )

        if not dry_run:
            await db["assignments"].update_one(
                {"_id": asgn["_id"]},
                {"$set": {"referee.level": correct_level}},
            )
        asgn_updated += 1

    print("\n  Assignments summary:")
    print(f"    Checked:          {asgn_checked}")
    print(f"    Already correct:  {asgn_already_correct}")
    print(f"    Updated:          {asgn_updated}")
    print(f"    Skipped (no user): {asgn_skipped_no_user}")

    # ------------------------------------------------------------------
    # 3. Update future matches (referee1 and referee2)
    #    — level from users, assignmentStatus from assignments collection
    # ------------------------------------------------------------------
    print("\nProcessing future matches...")
    now = datetime.now(tz=UTC)

    matches = (
        await db["matches"]
        .find(
            {
                "startDate": {"$gte": now},
                "$or": [
                    {"referee1": {"$ne": None}},
                    {"referee2": {"$ne": None}},
                ],
            },
            {
                "_id": 1,
                "matchId": 1,
                "startDate": 1,
                "referee1.userId": 1,
                "referee1.level": 1,
                "referee1.assignmentStatus": 1,
                "referee2.userId": 1,
                "referee2.level": 1,
                "referee2.assignmentStatus": 1,
            },
        )
        .to_list(None)
    )

    # Build a (matchId, userId) → canonical assignmentStatus map from the
    # assignments collection for all future match IDs in one batch query.
    future_match_ids = [m["_id"] for m in matches]
    status_map: dict[tuple, str] = {}
    if future_match_ids:
        positioned_asgns = (
            await db["assignments"]
            .find(
                {
                    "matchId": {"$in": future_match_ids},
                    "status": {"$in": ["ASSIGNED", "ACCEPTED"]},
                    "position": {"$in": [1, 2]},
                },
                {"_id": 0, "matchId": 1, "referee.userId": 1, "status": 1},
            )
            .to_list(None)
        )
        for a in positioned_asgns:
            m_id = a.get("matchId")
            u_id = (a.get("referee") or {}).get("userId")
            if m_id and u_id:
                status_map[(m_id, u_id)] = a["status"]

    match_checked = 0
    match_updated = 0
    match_already_correct = 0
    match_skipped_no_user = 0

    for match in matches:
        match_checked += 1
        match_label = f"matchId={match.get('matchId', match['_id'])}"
        updates: dict = {}
        change_notes: list[str] = []

        for slot in ("referee1", "referee2"):
            ref = match.get(slot)
            if not ref:
                continue

            user_id = ref.get("userId")

            # --- level ---
            current_level = ref.get("level", "n/a")
            if user_id not in level_map:
                print(
                    f"  ⚠️  {match_label} {slot} userId {user_id!r} not found in users, skipping slot"
                )
                match_skipped_no_user += 1
                continue
            correct_level = level_map[user_id]
            if current_level != correct_level:
                updates[f"{slot}.level"] = correct_level
                change_notes.append(f"{slot}.level: {current_level!r} → {correct_level!r}")

            # --- assignmentStatus ---
            current_status = ref.get("assignmentStatus")
            correct_status = status_map.get((match["_id"], user_id))
            if correct_status and current_status != correct_status:
                updates[f"{slot}.assignmentStatus"] = correct_status
                change_notes.append(
                    f"{slot}.assignmentStatus: {current_status!r} → {correct_status!r}"
                )

        if not updates:
            match_already_correct += 1
            continue

        print(
            f"  {'[DRY-RUN] Would update' if dry_run else 'Updating'}"
            f" {match_label} — {', '.join(change_notes)}"
        )

        if not dry_run:
            await db["matches"].update_one(
                {"_id": match["_id"]},
                {"$set": updates},
            )
        match_updated += 1

    print("\n  Matches summary:")
    print(f"    Checked:          {match_checked}")
    print(f"    Already correct:  {match_already_correct}")
    print(f"    Updated:          {match_updated}")
    print(f"    Skipped (no user): {match_skipped_no_user}")

    client.close()

    print(f"\n{'='*70}")
    if dry_run:
        print("  DRY-RUN complete — no changes were written.")
        print("  Re-run with --apply to persist the changes.")
    else:
        print("  Backfill complete.")
    print(f"{'='*70}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill referee.level and assignmentStatus in assignments and matches."
    )
    parser.add_argument(
        "--prod", action="store_true", help="Use production database (default: development)"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write changes (default is dry-run — prints what would change)",
    )
    args = parser.parse_args()

    asyncio.run(backfill(is_prod=args.prod, dry_run=not args.apply))


if __name__ == "__main__":
    main()
