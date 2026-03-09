"""
Centralized Import Service

Provides common functionality for all data import operations:
- Database connection management
- Authentication handling
- Error handling and rollback
- Progress tracking and logging
"""

from collections.abc import Callable
from typing import Any

import certifi
import requests
from pymongo import MongoClient
from pymongo.database import Database

from config import settings
from logging_config import logger


class ImportService:
    """Unified service for data import operations"""

    VALID_ENVIRONMENTS = ("dev", "demo", "prod")

    def __init__(self, environment: str = "dev", use_production: bool = False):
        """
        Initialize import service

        Args:
            environment: Target environment - "dev" (default), "demo", or "prod"
            use_production: Deprecated. If True, treated as environment="prod" for backward compatibility.
        """
        if use_production:
            environment = "prod"

        if environment not in self.VALID_ENVIRONMENTS:
            raise ValueError(
                f"Invalid environment '{environment}'. Must be one of: {', '.join(self.VALID_ENVIRONMENTS)}"
            )

        self.environment = environment
        self.client: MongoClient | None = None
        self.db: Database[Any] | None = None
        self.token: str | None = None
        self.headers: dict[str, str] | None = None

        if environment == "prod":
            self.db_url = settings.DB_URL_PROD
            self.db_name = "bishl"
            self.base_url = settings.BE_API_URL_PROD or settings.BE_API_URL
        elif environment == "demo":
            self.db_url = settings.DB_URL_DEMO
            self.db_name = "bishl_demo"
            self.base_url = settings.BE_API_URL_DEMO or settings.BE_API_URL
        else:
            self.db_url = settings.DB_URL
            self.db_name = "bishl_dev"
            self.base_url = settings.BE_API_URL

        self.environment_label = environment.upper()

        # Shared HTTP session.
        # Replit dev-proxy domains use an intermediate CA not in certifi's bundle,
        # so SSL verification is disabled for those URLs only.  All other
        # environments (prod/demo) keep full verification via certifi.
        self.session = requests.Session()
        if ".replit.dev" in self.base_url:
            self.session.verify = False
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        else:
            self.session.verify = certifi.where()

        logger.info(f"Import Service initialized for {self.environment_label}")
        logger.info(f"Database: {self.db_name}")
        logger.info(f"API URL: {self.base_url}")

    def connect_db(self) -> None:
        """Establish database connection"""
        try:
            self.client = MongoClient(self.db_url, tlsCAFile=certifi.where())
            self.db = self.client[self.db_name]
            logger.info("Database connection established")
        except Exception as e:
            logger.error(f"Failed to connect to database: {str(e)}")
            raise

    def authenticate(self) -> bool:
        """
        Authenticate with API and get token

        Returns:
            True if authentication successful, False otherwise
        """
        login_url = f"{self.base_url}/users/login"
        login_data = {
            "email": settings.SYS_ADMIN_EMAIL,
            "password": settings.SYS_ADMIN_PASSWORD,
        }

        try:
            response = self.session.post(login_url, json=login_data)

            if response.status_code != 200:
                logger.error(f"Authentication failed: {response.text}")
                return False

            self.token = response.json()["access_token"]
            self.headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            }
            # Persist headers on the session so every subsequent request is
            # automatically authenticated without passing headers explicitly.
            self.session.headers.update(self.headers)
            logger.info("Authentication successful")
            return True

        except Exception as e:
            logger.error(f"Authentication error: {str(e)}")
            return False

    def get_collection(self, collection_name: str):
        """Get a database collection"""
        if self.db is None:
            raise RuntimeError("Database not connected. Call connect_db() first.")
        return self.db[collection_name]

    def import_schedule(self, csv_path: str, import_all: bool = False) -> tuple[bool, str]:
        """
        Import match schedule from CSV file

        Args:
            csv_path: Path to CSV file containing schedule data
            import_all: If True, import all matches. If False, stop after first match

        Returns:
            Tuple of (success: bool, message: str)
        """
        import csv
        import json
        from datetime import datetime

        from fastapi.encoders import jsonable_encoder

        from models.matches import (
            MatchBase,
            MatchMatchday,
            MatchRound,
            MatchSeason,
            MatchTeam,
            MatchTournament,
            MatchVenue,
        )
        from models.tournaments import MatchdayBase, RoundDB

        if not self.token or not self.headers:
            return False, "Not authenticated. Call authenticate() first."

        collection = self.get_collection("matches")

        try:
            with open(csv_path, encoding="utf-8") as f:
                reader = csv.DictReader(
                    f, delimiter=";", quotechar='"', doublequote=True, skipinitialspace=True
                )
                rows = list(reader)

            progress = ImportProgress(len(rows), "Importing schedule")
            matches_created = 0
            matches_skipped = 0

            for row in rows:
                try:
                    # Parse tournament data
                    tournament_data = row.get("tournament")
                    if isinstance(tournament_data, str):
                        tournament_data = json.loads(tournament_data)
                    if not tournament_data:
                        progress.add_error("Missing tournament data")
                        continue
                    tournament = MatchTournament(**tournament_data)

                    # Parse season data
                    season_data = row.get("season")
                    if isinstance(season_data, str):
                        season_data = json.loads(season_data)
                    if not season_data:
                        progress.add_error("Missing season data")
                        continue
                    season = MatchSeason(**season_data)

                    # Parse round data
                    round_data = row.get("round")
                    if isinstance(round_data, str):
                        round_data = json.loads(round_data)
                    if not round_data:
                        progress.add_error("Missing round data")
                        continue
                    round = MatchRound(**round_data)

                    # Parse matchday data
                    matchday_data = row.get("matchday")
                    if isinstance(matchday_data, str):
                        matchday_data = json.loads(matchday_data)
                    if not matchday_data:
                        progress.add_error("Missing matchday data")
                        continue
                    matchday = MatchMatchday(**matchday_data)

                    # Parse venue data
                    venue_data = row.get("venue")
                    if isinstance(venue_data, str):
                        venue_data = json.loads(venue_data)
                    if not venue_data:
                        progress.add_error("Missing venue data")
                        continue
                    venue = MatchVenue(**venue_data)

                    # Parse published flag
                    published_value = row.get("published")
                    if isinstance(published_value, str):
                        published_value = published_value.lower() == "true"
                    published_value = (
                        published_value if isinstance(published_value, bool) else False
                    )

                    # Parse start date
                    start_date_str = row.get("startDate")
                    start_date = None
                    if start_date_str:
                        try:
                            start_date = datetime.strptime(start_date_str, "%Y-%m-%d %H:%M:%S%z")
                        except ValueError:
                            progress.add_error(f"Invalid startDate format: {start_date_str}")
                            continue

                    # Get aliases
                    t_alias = tournament.alias
                    s_alias = season.alias
                    r_alias = round.alias
                    md_alias = matchday.alias

                    # Check if round exists
                    round_url = (
                        f"{self.base_url}/tournaments/{t_alias}/seasons/{s_alias}/rounds/{r_alias}"
                    )
                    round_response = self.session.get(round_url)
                    if round_response.status_code != 200:
                        progress.add_error(f"Round does not exist: {t_alias}/{s_alias}/{r_alias}")
                        continue

                    round_db = RoundDB(**round_response.json().get("data", {}))

                    # Check if matchday exists, create if needed
                    matchday_url = f"{self.base_url}/tournaments/{t_alias}/seasons/{s_alias}/rounds/{r_alias}/matchdays/{md_alias}"
                    matchday_response = self.session.get(matchday_url)
                    if matchday_response.status_code != 200:
                        new_matchday_data = row.get("newMatchday")
                        logger.info(
                            f"Creating new matchday: {t_alias}/{s_alias}/{r_alias}/{md_alias}"
                        )
                        if isinstance(new_matchday_data, str):
                            new_matchday_data = json.loads(new_matchday_data)

                        if not new_matchday_data:
                            progress.add_error("Missing newMatchday data for matchday creation")
                            continue

                        new_matchday = MatchdayBase(**new_matchday_data)
                        new_matchday.published = True

                        create_md_response = self.session.post(
                            f"{self.base_url}/tournaments/{t_alias}/seasons/{s_alias}/rounds/{r_alias}/matchdays",
                            json=jsonable_encoder(new_matchday),
                        )
                        if create_md_response.status_code != 201:
                            progress.add_error(
                                f"Failed to create matchday: {t_alias}/{s_alias}/{r_alias}/{md_alias}"
                            )
                            continue

                    # Fetch home club and team
                    home_club_alias = row.get("homeClubAlias")
                    home_team_alias = row.get("homeTeamAlias")

                    home_club_response = self.session.get(
                        f"{self.base_url}/clubs/{home_club_alias}"
                    )
                    if home_club_response.status_code != 200:
                        progress.add_error(f"Home club not found: {home_club_alias}")
                        continue
                    home_club = home_club_response.json().get("data")

                    home_team_response = self.session.get(
                        f"{self.base_url}/clubs/{home_club_alias}/teams/{home_team_alias}"
                    )
                    if home_team_response.status_code != 200:
                        progress.add_error(
                            f"Home team not found: {home_club_alias}/{home_team_alias}"
                        )
                        continue
                    home_team = home_team_response.json().get("data")

                    home = MatchTeam(
                        clubId=home_club.get("_id"),
                        clubName=home_club.get("name"),
                        clubAlias=home_club.get("alias"),
                        teamId=home_team.get("_id"),
                        teamAlias=home_team.get("alias"),
                        name=home_team.get("name"),
                        fullName=home_team.get("fullName"),
                        shortName=home_team.get("shortName"),
                        tinyName=home_team.get("tinyName"),
                        logo=home_club.get("logoUrl"),
                    )

                    # Fetch away club and team
                    away_club_alias = row.get("awayClubAlias")
                    away_team_alias = row.get("awayTeamAlias")

                    away_club_response = self.session.get(
                        f"{self.base_url}/clubs/{away_club_alias}"
                    )
                    if away_club_response.status_code != 200:
                        progress.add_error(f"Away club not found: {away_club_alias}")
                        continue
                    away_club = away_club_response.json().get("data")

                    away_team_response = self.session.get(
                        f"{self.base_url}/clubs/{away_club_alias}/teams/{away_team_alias}"
                    )
                    if away_team_response.status_code != 200:
                        progress.add_error(
                            f"Away team not found: {away_club_alias}/{away_team_alias}"
                        )
                        continue
                    away_team = away_team_response.json().get("data")

                    away = MatchTeam(
                        clubId=away_club.get("_id"),
                        clubName=away_club.get("name"),
                        clubAlias=away_club.get("alias"),
                        teamId=away_team.get("_id"),
                        teamAlias=away_team.get("alias"),
                        name=away_team.get("name"),
                        fullName=away_team.get("fullName"),
                        shortName=away_team.get("shortName"),
                        tinyName=away_team.get("tinyName"),
                        logo=away_club.get("logoUrl"),
                    )

                    # Create match
                    new_match = MatchBase(
                        tournament=tournament,
                        season=season,
                        round=round,
                        matchday=matchday,
                        venue=venue,
                        published=published_value,
                        home=home,
                        away=away,
                        startDate=start_date,
                    )

                    new_match_data = jsonable_encoder(new_match)

                    # Check if match already exists
                    query = {
                        "startDate": start_date,
                        "home.clubId": home.clubId,
                        "home.teamId": home.teamId,
                        "away.clubId": away.clubId,
                        "away.teamId": away.teamId,
                    }
                    match_exists = collection.find_one(query)

                    if not match_exists:
                        response = self.session.post(
                            f"{self.base_url}/matches", json=new_match_data
                        )
                        if response.status_code == 201:
                            matches_created += 1
                            progress.update(
                                message=f"Created: {home.fullName} - {away.fullName} in {t_alias}/{r_alias}/{md_alias}"
                            )

                            if not import_all:
                                logger.info("import_all flag not set, stopping after first match")
                                break
                        else:
                            progress.add_error(
                                f"Failed to create match (HTTP {response.status_code}): {home.fullName} - {away.fullName}"
                            )
                    else:
                        matches_skipped += 1
                        progress.update(
                            message=f"Skipped (exists): {home.fullName} - {away.fullName}"
                        )

                except json.JSONDecodeError as e:
                    progress.add_error(f"Invalid JSON in row: {str(e)}")
                except Exception as e:
                    progress.add_error(f"Error processing row: {str(e)}")

            summary = progress.summary()
            logger.info(summary)

            result_msg = (
                f"Created {matches_created} matches, skipped {matches_skipped} existing matches"
            )
            return True, result_msg

        except FileNotFoundError:
            error_msg = f"CSV file not found: {csv_path}"
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Schedule import failed: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

    def import_referees(
        self,
        csv_path: str,
        import_all: bool = False,
        send_email: bool = False,
        strategy: str = "merge",
    ) -> tuple[bool, str]:
        """
        Import referees from a semicolon-delimited CSV file using a configurable strategy.

        Existing users are matched by firstName + lastName (case-sensitive).

        CSV columns (semicolon-delimited):
            firstName, lastName, email, club (JSON), level, passNo, ishdLevel

        Args:
            csv_path:   Path to the CSV file.
            import_all: If False, stop after the first successfully created user.
                        Useful for smoke-testing before a full run.
            send_email: If True, send email notifications:
                        - Welcome email for newly created referees.
                        - Login-change email when an existing referee's email is updated.
            strategy:   Controls how the CSV is reconciled against the database.

                        "merge"  (default)
                            Step 1 — Deactivate all current referees by setting
                                     referee.active = False on every user that has a
                                     referee sub-document.
                            Step 2 — Loop CSV rows:
                                Found   → Reactivate (active=True) and update level,
                                          passNo, ishdLevel.  If the email in the CSV
                                          differs from the stored email, update it too
                                          and, if --send-email is set, notify the user
                                          that their login credential has changed.
                                Not found → Create new user/referee and optionally
                                            send a welcome email.
                            Use this strategy for a full roster replacement, e.g.
                            at the start of a new season.

                        "insert"
                            Does NOT deactivate existing referees.
                            Found   → Skip (no changes made).
                            Not found → Create new user/referee and optionally
                                        send a welcome email.
                            Use this strategy to add new referees without touching
                            existing records.

                        "update"
                            Does NOT deactivate existing referees.
                            Found   → Update level, passNo, ishdLevel and handle
                                      email changes the same way as "merge".
                            Not found → Skip (no changes made).
                            Use this strategy to refresh data for known referees
                            without creating new accounts.

        Returns:
            Tuple of (success: bool, message: str)

        Examples:
            # Full season refresh — deactivate all, re-activate from CSV, create new ones
            service.import_referees("data/referees.csv", strategy="merge",
                                    import_all=True, send_email=True)

            # Add new referees only, leave existing ones untouched
            service.import_referees("data/referees.csv", strategy="insert",
                                    import_all=True, send_email=True)

            # Update existing referees only (no creates)
            service.import_referees("data/referees.csv", strategy="update",
                                    import_all=True)
        """
        import asyncio
        import csv
        import json
        import random
        import string
        from typing import Literal

        # Validate strategy value early so callers get a clear error
        valid_strategies = ("merge", "insert", "update")
        if strategy not in valid_strategies:
            return False, f"Invalid strategy '{strategy}'. Must be one of: {', '.join(valid_strategies)}"

        if not self.token or not self.headers:
            return False, "Not authenticated. Call authenticate() first."

        clubs_collection = self.get_collection("clubs")
        users_collection = self.get_collection("users")

        # ------------------------------------------------------------------
        # BACKUP — capture all users that carry referee data so we can
        # restore them precisely if anything goes wrong.  Referees are
        # embedded in the 'users' collection, so a generic collection-level
        # rollback would be both wrong (wrong collection name) and dangerous
        # (would delete all users).  We scope the backup to referee docs only.
        # ------------------------------------------------------------------
        referee_backup = list(users_collection.find({"referee": {"$exists": True}}))
        logger.info(f"Backed up {len(referee_backup)} referee user(s) for rollback safety")

        try:
            with open(csv_path, encoding="utf-8") as f:
                reader = csv.DictReader(
                    f, delimiter=";", quotechar='"', doublequote=True, skipinitialspace=True
                )
                rows = list(reader)

            progress = ImportProgress(len(rows), f"Importing referees [{strategy}]")
            created = 0
            updated = 0
            skipped = 0
            email_changed = 0

            # ------------------------------------------------------------------
            # MERGE: deactivate all existing referees before processing the CSV.
            # They will be selectively reactivated as each matching row is found.
            # Only target documents where 'referee' is a real object (type 3).
            # Using dot-notation $set on a null referee field causes MongoDB
            # error 28 "Cannot create field in element {referee: null}".
            # ------------------------------------------------------------------
            if strategy == "merge":
                deactivated = users_collection.update_many(
                    {"referee": {"$type": "object"}},
                    {"$set": {"referee.active": False}},
                )
                logger.info(
                    f"[merge] Deactivated {deactivated.modified_count} referee(s) before import"
                )

            for row in rows:
                try:
                    first_name = row.get("firstName", "").strip()
                    last_name = row.get("lastName", "").strip()
                    email = (row.get("email") or "").strip()

                    if not email:
                        progress.add_error(
                            f"No email for referee {first_name} {last_name} — skipping"
                        )
                        continue

                    # Parse club JSON
                    club_raw = row.get("club")
                    club = None
                    if isinstance(club_raw, str) and club_raw.strip():
                        try:
                            club = json.loads(club_raw)
                        except json.JSONDecodeError:
                            pass

                    if not club:
                        progress.add_error(f"No club data for referee {email} — skipping")
                        continue

                    # Enrich club with logoUrl from DB
                    if club.get("clubId"):
                        club_doc = clubs_collection.find_one({"_id": club["clubId"]})
                        if club_doc and club_doc.get("logoUrl"):
                            club["logoUrl"] = club_doc["logoUrl"]

                    level = (row.get("level") or "n/a").strip()
                    pass_no = row.get("passNo") or None
                    ishd_level = row.get("ishdLevel") or None

                    # ----------------------------------------------------------
                    # Look up the user by firstName + lastName (not by email).
                    # Email may change between imports; the name is the stable key.
                    # ----------------------------------------------------------
                    existing_user = users_collection.find_one(
                        {"firstName": first_name, "lastName": last_name}
                    )

                    if existing_user:
                        # -------------------------------------------------------
                        # User EXISTS — behaviour depends on strategy
                        # -------------------------------------------------------

                        if strategy == "insert":
                            # insert: skip existing users entirely
                            skipped += 1
                            progress.update(
                                message=f"[insert] Skipped existing: {first_name} {last_name}"
                            )
                            continue

                        # merge / update: update the referee's fields
                        stored_email = existing_user.get("email", "")
                        update_fields: dict = {
                            "referee.active": True,
                            "referee.level": level,
                            "referee.passNo": pass_no,
                            "referee.ishdLevel": ishd_level,
                            "referee.club": club,
                        }

                        # Handle email change
                        if email != stored_email:
                            update_fields["email"] = email
                            email_changed += 1
                            logger.info(
                                f"[{strategy}] Email changed for {first_name} {last_name}: "
                                f"{stored_email} → {email}"
                            )

                            # Notify the user about the credential change if requested
                            if send_email:
                                try:
                                    from mail_service import send_email as _send_email

                                    subject = "BISHL - Deine Login-E-Mail wurde geändert"
                                    body = f"""
<p>Hallo {first_name},</p>
<p>deine Login-E-Mail-Adresse für dein Schiedsrichter-Account auf www.bishl.de wurde aktualisiert.</p>
<p>Ab sofort meldest du dich mit folgender E-Mail-Adresse an:</p>
<ul>
  <li><strong>Neue E-Mail (Login):</strong> {email}</li>
</ul>
<p>Bitte verwende ab sofort diese Adresse, um dich bei www.bishl.de einzuloggen.</p>
<p>Falls du diese Änderung nicht erwartet hast, melde dich bitte über website@bishl.de</p>
<p>Viele Grüße,<br>Das BISHL-Team</p>
"""
                                    asyncio.run(_send_email(subject, [email], body))
                                    logger.info(f"Email-change notification sent to {email}")
                                except Exception as mail_err:
                                    logger.warning(
                                        f"Failed to send email-change notification to {email}: {mail_err}"
                                    )

                        users_collection.update_one(
                            {"_id": existing_user["_id"]},
                            {"$set": update_fields},
                        )

                        # Ensure the REFEREE role is present
                        roles = existing_user.get("roles", [])
                        if "REFEREE" not in roles:
                            roles.append("REFEREE")
                            users_collection.update_one(
                                {"_id": existing_user["_id"]}, {"$set": {"roles": roles}}
                            )

                        updated += 1
                        progress.update(
                            message=f"[{strategy}] Updated: {first_name} {last_name} ({email})"
                        )
                        continue

                    else:
                        # -------------------------------------------------------
                        # User does NOT EXIST — behaviour depends on strategy
                        # -------------------------------------------------------

                        if strategy == "update":
                            # update: skip rows where no matching user exists
                            skipped += 1
                            progress.update(
                                message=f"[update] Not found, skipped: {first_name} {last_name}"
                            )
                            continue

                        # merge / insert: create a new user account

                    # ----------------------------------------------------------
                    # CREATE or UPGRADE — reached by merge (not found by name)
                    # and insert (not found by name).
                    #
                    # A user may already exist under a different name match but
                    # share the same email (e.g. they registered independently
                    # before becoming a referee).  Check by email first:
                    #   • Found by email → upgrade: add REFEREE role + set
                    #     referee sub-document.  No new account is created.
                    #   • Not found by email → register a brand-new account via
                    #     the API with a generated password.
                    # ----------------------------------------------------------
                    existing_by_email = users_collection.find_one({"email": email})

                    if existing_by_email:
                        # Upgrade an existing user to referee.
                        # Set the whole referee sub-document (not dot-notation fields)
                        # to avoid MongoDB error 28 when the field is currently null.
                        users_collection.update_one(
                            {"_id": existing_by_email["_id"]},
                            {"$set": {
                                "referee": {
                                    "club": club,
                                    "level": level,
                                    "passNo": pass_no,
                                    "ishdLevel": ishd_level,
                                    "active": True,
                                }
                            }},
                        )
                        roles = existing_by_email.get("roles", [])
                        if "REFEREE" not in roles:
                            roles.append("REFEREE")
                            users_collection.update_one(
                                {"_id": existing_by_email["_id"]},
                                {"$set": {"roles": roles}},
                            )
                        updated += 1
                        progress.update(
                            message=f"[{strategy}] Upgraded existing user to referee: {email}"
                        )

                        # Send notification email to the upgraded user
                        if send_email:
                            try:
                                from mail_service import send_email as _send_email

                                user_first_name = existing_by_email.get("firstName", "")
                                subject = "BISHL - Du bist nun auch Schiedsrichter"
                                body = f"""
<p>Hallo {user_first_name},</p>
<p>du bist jetzt als Schiedsrichter bei der BISHL registriert.</p>
<p>Du kannst dich mit deinen bekannten Login-Daten anmelden:</p>
<ul>
  <li><strong>E-Mail:</strong> {email}</li>
  <li><strong>Passwort:</strong> Dein bestehendes Passwort</li>
</ul>
<p>Bitte logge dich bei www.bishl.de ein und aktualisiere dein Profil mit deinen Schiedsrichter-Daten, falls nötig.</p>
<p>Falls du Fragen hast, melde dich bitte über website@bishl.de</p>
<p>Viele Grüße,<br>Das BISHL-Team</p>
"""
                                asyncio.run(_send_email(subject, [email], body))
                                logger.info(f"Referee upgrade notification sent to {email}")
                            except Exception as mail_err:
                                logger.warning(
                                    f"Failed to send upgrade notification to {email}: {mail_err}"
                                )

                        # Upgrades are idempotent updates — do NOT apply the
                        # import_all safety stop here.  That stop only makes sense
                        # for brand-new account creation where a random password
                        # was generated and a single test-creation is desired.
                        continue

                    # No match by email either — register a brand-new account
                    random_password = "".join(
                        random.choices(string.ascii_letters + string.digits, k=12)
                    )

                    new_user = {
                        "email": email,
                        "password": random_password,
                        "firstName": first_name,
                        "lastName": last_name,
                        "roles": ["REFEREE"],
                        "referee": {
                            "club": club,
                            "level": level,
                            "passNo": pass_no,
                            "ishdLevel": ishd_level,
                            "active": True,
                        },
                    }

                    register_url = f"{self.base_url}/users/register"
                    response = self.session.post(register_url, json=new_user)

                    if response.status_code == 201:
                        created += 1
                        progress.update(message=f"[{strategy}] Created: {email}")

                        # Optionally send welcome email to new referee
                        if send_email:
                            try:
                                from mail_service import send_email as _send_email

                                subject = "BISHL - Schiedsrichter-Account angelegt"
                                body = f"""
<p>Hallo {first_name},</p>
<p>dein Schiedsrichter-Account wurde erfolgreich angelegt.</p>
<p>Hier sind deine Login-Details:</p>
<ul>
  <li><strong>E-Mail:</strong> {email}</li>
  <li><strong>Passwort:</strong> {random_password}</li>
</ul>
<p>Bitte logge dich bei www.bishl.de ein und ändere dein Passwort.</p>
<p>Falls du Fragen hast, melde dich bitte über website@bishl.de</p>
<p>Viele Grüße,<br>Das BISHL-Team</p>
"""
                                asyncio.run(_send_email(subject, [email], body))
                                logger.info(f"Welcome email sent to {email}")
                            except Exception as mail_err:
                                logger.warning(
                                    f"Failed to send welcome email to {email}: {mail_err}"
                                )
                        else:
                            logger.info(
                                f"Skipping welcome email for {email} (--send-email not set)"
                            )

                        if not import_all:
                            logger.info(
                                "--import-all not set, stopping after first created referee"
                            )
                            break
                    else:
                        progress.add_error(
                            f"Failed to register {email} "
                            f"(HTTP {response.status_code}): {response.text}"
                        )

                except json.JSONDecodeError as e:
                    progress.add_error(
                        f"Invalid JSON in row for {row.get('firstName', '?')} "
                        f"{row.get('lastName', '?')}: {e}"
                    )
                except Exception as e:
                    progress.add_error(
                        f"Error processing row {row.get('firstName', '?')} "
                        f"{row.get('lastName', '?')}: {e}"
                    )

            summary = progress.summary()
            logger.info(summary)

            result_msg = (
                f"Referees [{strategy}]: {created} created, {updated} updated "
                f"({email_changed} email change(s)), {skipped} skipped"
            )
            return True, result_msg

        except FileNotFoundError:
            error_msg = f"CSV file not found: {csv_path}"
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            # Build the error message as a plain string for return values.
            # IMPORTANT: do NOT embed str(e) directly inside a loguru message
            # template because MongoDB errors may contain literal curly-brace
            # sequences (e.g. "{referee: null}") that loguru interprets as
            # format placeholders, causing a secondary KeyError.
            # Always pass exception objects as positional args to loguru.
            error_msg = f"Referee import failed: {str(e)}"
            logger.opt(exception=True).error("Referee import failed: {}", e)

            # ------------------------------------------------------------------
            # ROLLBACK — restore all referee users to their pre-import state.
            # Uses replace_one with upsert=True so that documents that were
            # modified are fully overwritten, and any that were removed are
            # recreated.  Users created via the /users/register API during this
            # run are NOT automatically deleted here; a warning is logged instead.
            # ------------------------------------------------------------------
            if referee_backup:
                try:
                    logger.info(
                        f"Rolling back {len(referee_backup)} referee user(s) to pre-import state..."
                    )
                    for doc in referee_backup:
                        users_collection.replace_one(
                            {"_id": doc["_id"]}, doc, upsert=True
                        )
                    logger.info("Rollback completed successfully")
                    return False, f"{error_msg} (rolled back)"
                except Exception as rollback_err:
                    logger.error("Rollback failed: {}", rollback_err)
                    return False, f"{error_msg} (rollback failed: {rollback_err})"

            return False, error_msg

    def import_with_rollback(
        self, import_func: Callable, collection_name: str, backup_before: bool = True
    ) -> tuple[bool, str]:
        """
        Execute import function with automatic rollback on failure

        Args:
            import_func: Function to execute (should return success boolean and message)
            collection_name: Name of collection being modified
            backup_before: Whether to backup collection before import

        Returns:
            Tuple of (success: bool, message: str)
        """
        collection = self.get_collection(collection_name)
        backup_data = None

        try:
            # Backup if requested
            if backup_before:
                logger.info(f"Backing up {collection_name} collection...")
                backup_data = list(collection.find())
                logger.info(f"Backed up {len(backup_data)} documents")

            # Execute import
            success, message = import_func()

            if success:
                logger.info(f"Import completed successfully: {message}")
                return True, message
            else:
                logger.warning(f"Import returned failure: {message}")
                return False, message

        except Exception as e:
            error_msg = f"Import failed with error: {str(e)}"
            logger.error(error_msg)

            # Rollback if we have backup
            if backup_data is not None:
                try:
                    logger.info("Rolling back changes...")
                    collection.delete_many({})
                    if backup_data:
                        collection.insert_many(backup_data)
                    logger.info("Rollback completed")
                    return False, f"{error_msg} (rolled back)"
                except Exception as rollback_error:
                    logger.error(f"Rollback failed: {str(rollback_error)}")
                    return False, f"{error_msg} (rollback failed: {str(rollback_error)})"

            return False, error_msg

    def close(self) -> None:
        """Close database connection and HTTP session"""
        if self.client is not None:
            self.client.close()
            logger.info("Database connection closed")
        self.session.close()

    def __enter__(self):
        """Context manager entry"""
        self.connect_db()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()
        return False


class ImportProgress:
    """Track and log import progress"""

    def __init__(self, total: int, description: str = "Processing"):
        self.total = total
        self.current = 0
        self.description = description
        self.errors: list[str] = []

    def update(self, increment: int = 1, message: str | None = None):
        """Update progress counter"""
        self.current += increment
        percentage = (self.current / self.total * 100) if self.total > 0 else 0

        if message:
            logger.info(
                f"{self.description}: {self.current}/{self.total} ({percentage:.1f}%) - {message}"
            )
        elif self.current % max(1, self.total // 10) == 0:  # Log every 10%
            logger.info(f"{self.description}: {self.current}/{self.total} ({percentage:.1f}%)")

    def add_error(self, error: str):
        """Record an error"""
        self.errors.append(error)
        logger.warning(f"Error recorded: {error}")

    def summary(self) -> str:
        """Get progress summary"""
        success_count = self.current - len(self.errors)
        summary = f"Completed: {self.current}/{self.total} ({success_count} successful, {len(self.errors)} errors)"

        if self.errors:
            summary += "\nErrors:\n" + "\n".join(f"  - {err}" for err in self.errors[:10])
            if len(self.errors) > 10:
                summary += f"\n  ... and {len(self.errors) - 10} more errors"

        return summary
