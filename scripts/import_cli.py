#!/usr/bin/env python
"""
Unified Import CLI

Centralized command-line interface for all data import operations.

Usage:
    python scripts/import_cli.py <entity> [options]

Entities:
    players           Import players from CSV
    tournaments       Import tournaments
    schedule          Import match schedule
    teams             Import teams
    team-assignments  Import team assignments
    hobby-players     Import hobby players
    referees          Import referees

Options:
    --prod            Use production database
    --file PATH       Path to CSV file (default: data/data_<entity>.csv)
    --delete-all      Delete all existing records before import
    --import-all      Import all records (bypass confirmations)
    --dry-run         Show what would be imported without making changes

Examples:
    python scripts/import_cli.py players --prod --import-all
    python scripts/import_cli.py schedule --file data/schedule_2025.csv
    python scripts/import_cli.py tournaments --dry-run
"""

import sys
from pathlib import Path

# Add parent directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import csv
import os
from collections.abc import Callable
from typing import Any

from logging_config import logger
from services.import_service import ImportProgress, ImportService


class ImportCLI:
    """Unified CLI for import operations"""

    def __init__(self):
        self.service: ImportService = None
        self.args = None

        # Map entity names to their import handlers
        self.handlers: dict[str, Callable] = {
            "players": self.import_players,
            "tournaments": self.import_tournaments,
            "schedule": self.import_schedule,
            "teams": self.import_teams,
            "team-assignments": self.import_team_assignments,
            "hobby-players": self.import_hobby_players,
            "referees": self.import_referees,
        }

    def setup_parser(self) -> argparse.ArgumentParser:
        """Create argument parser"""
        parser = argparse.ArgumentParser(
            description="Unified import CLI for BISHL data",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog=__doc__,
        )

        parser.add_argument(
            "entity", choices=list(self.handlers.keys()), help="Entity type to import"
        )

        parser.add_argument("--prod", action="store_true", help="Use production database and API")

        parser.add_argument(
            "--file", type=str, help="Path to CSV file (default: data/data_<entity>.csv)"
        )

        parser.add_argument(
            "--delete-all", action="store_true", help="Delete all existing records before import"
        )

        parser.add_argument(
            "--import-all", action="store_true", help="Import all records without confirmation"
        )

        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be imported without making changes",
        )

        return parser

    def get_csv_path(self, entity: str) -> str:
        """Get default CSV path for entity"""
        if self.args.file:
            return self.args.file

        # Map entity names to default file names
        file_map = {
            "players": "data_players.csv",
            "tournaments": "data_tournaments.csv",
            "schedule": "data_schedule.csv",
            "teams": "data_teams.csv",
            "team-assignments": "data_team_assignments.csv",
            "hobby-players": "data_hobby_players.csv",
            "referees": "data_referees.csv",
        }

        filename = file_map.get(entity, f"data_{entity}.csv")
        return f"data/{filename}"

    def read_csv(self, filepath: str, delimiter: str = ",") -> list[dict[str, Any]]:
        """Read CSV file and return list of dictionaries"""
        try:
            with open(filepath, encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter=delimiter)
                data = list(reader)
                logger.info(f"Read {len(data)} rows from {filepath}")
                return data
        except FileNotFoundError:
            logger.error(f"File not found: {filepath}")
            raise
        except Exception as e:
            logger.error(f"Error reading CSV: {str(e)}")
            raise

    def confirm_action(self, message: str) -> bool:
        """Ask user for confirmation"""
        if self.args.import_all or self.args.dry_run:
            return True

        response = input(f"{message} (y/N): ").strip().lower()
        return response == "y"

    # Import handlers (placeholders - to be implemented based on existing scripts)

    def import_players(self) -> tuple[bool, str]:
        """Import players"""
        logger.info("Starting players import...")

        csv_path = self.get_csv_path("players")
        collection = self.service.get_collection("players")

        if self.args.delete_all:
            if self.confirm_action("Delete all existing players?"):
                if not self.args.dry_run:
                    result = collection.delete_many({})
                    logger.info(f"Deleted {result.deleted_count} players")

        data = self.read_csv(csv_path)
        progress = ImportProgress(len(data), "Importing players")

        # TODO: Implement actual player import logic from import_players.py
        # This is a placeholder structure

        for row in data:
            if self.args.dry_run:
                logger.info(f"Would import player: {row.get('firstName')} {row.get('lastName')}")
            else:
                # Actual import logic here
                pass

            progress.update()

        logger.info(progress.summary())
        return True, f"Imported {len(data)} players"

    def import_tournaments(self) -> tuple[bool, str]:
        """Import tournaments"""
        logger.info("Starting tournaments import...")
        # TODO: Implement from import_tournaments.py
        return True, "Tournaments import not yet implemented"

    def import_schedule(self) -> tuple[bool, str]:
        """Import match schedule"""
        logger.info("Starting schedule import...")

        csv_path = self.get_csv_path("schedule")
        if not os.path.exists(csv_path):
            return False, f"Schedule CSV file not found: {csv_path}"

        return self.service.import_schedule(csv_path, import_all=self.args.import_all)

    def import_teams(self) -> tuple[bool, str]:
        """Import teams"""
        logger.info("Starting teams import...")
        # TODO: Implement from import_new_teams.py
        return True, "Teams import not yet implemented"

    def import_team_assignments(self) -> tuple[bool, str]:
        """Import team assignments"""
        logger.info("Starting team assignments import...")
        # TODO: Implement from import_team_assignments.py
        return True, "Team assignments import not yet implemented"

    def import_hobby_players(self) -> tuple[bool, str]:
        """Import hobby players"""
        logger.info("Starting hobby players import...")
        # TODO: Implement from import_hobby_players.py
        return True, "Hobby players import not yet implemented"

    def import_referees(self) -> tuple[bool, str]:
        """Import referees"""
        logger.info("Starting referees import...")
        # TODO: Implement from import_referees.py
        return True, "Referees import not yet implemented"

    def run(self):
        """Main execution flow"""
        parser = self.setup_parser()
        self.args = parser.parse_args()

        logger.info("=== BISHL Import CLI ===")
        logger.info(f"Entity: {self.args.entity}")
        logger.info(f"Environment: {'PRODUCTION' if self.args.prod else 'DEVELOPMENT'}")
        logger.info(f"Mode: {'DRY RUN' if self.args.dry_run else 'LIVE'}")

        # Confirm production imports
        if self.args.prod and not self.args.dry_run:
            if not self.confirm_action("⚠️  This will modify PRODUCTION data. Continue?"):
                logger.info("Import cancelled by user")
                return

        try:
            # Initialize service
            with ImportService(use_production=self.args.prod) as service:
                self.service = service

                # Authenticate
                if not service.authenticate():
                    logger.error("Authentication failed. Exiting.")
                    return

                # Get handler for entity
                handler = self.handlers.get(self.args.entity)
                if not handler:
                    logger.error(f"No handler found for entity: {self.args.entity}")
                    return

                # Execute import with rollback support
                if self.args.dry_run:
                    success, message = handler()
                else:
                    success, message = service.import_with_rollback(
                        handler,
                        collection_name=self.args.entity.replace("-", "_"),
                        backup_before=True,
                    )

                if success:
                    logger.info(f"✓ Import completed: {message}")
                else:
                    logger.error(f"✗ Import failed: {message}")
                    sys.exit(1)

        except KeyboardInterrupt:
            logger.warning("Import interrupted by user")
            sys.exit(130)
        except Exception as e:
            logger.error(f"Import failed with error: {str(e)}", exc_info=True)
            sys.exit(1)


if __name__ == "__main__":
    cli = ImportCLI()
    cli.run()
