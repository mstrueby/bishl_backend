import os
import time
from typing import Dict, List, Optional
from functools import wraps
import httpx
import aiohttp
from datetime import datetime

from exceptions.custom_exceptions import (
    ResourceNotFoundException,
    DatabaseOperationException,
    StatsCalculationException,
    ValidationException
)
from logging_config import logger

BASE_URL = os.environ.get('BE_API_URL', 'http://localhost:8080')

# Remove the pydantic_patch.py file as requested.


def log_performance(func):
    """Decorator to log execution time and basic metrics for stats operations"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        func_name = func.__name__

        logger.info(f"Starting {func_name}...")

        try:
            result = await func(*args, **kwargs)
            elapsed = time.time() - start_time

            logger.info(f"{func_name} completed in {elapsed:.3f}s")

            return result
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"{func_name} failed after {elapsed:.3f}s: {str(e)}")
            raise

    return wrapper


class StatsService:
    """
    Centralized service for all statistics calculations.
    Handles match stats, standings aggregation, roster stats, and player card stats.
    """

    def __init__(self, mongodb=None):
        self.db = mongodb

    # ==================== MATCH STATISTICS ====================

    async def get_standings_settings(self, tournament_alias: str, season_alias: str) -> dict:
        """
        Fetch standings settings for a tournament/season.

        Args:
            tournament_alias: Tournament identifier
            season_alias: Season identifier

        Returns:
            Dictionary containing standings settings (points for win/loss/draw/etc.)

        Raises:
            HTTPException: If settings cannot be fetched
        """
        if not tournament_alias or not season_alias:
            raise ValidationException(
                field="tournament_alias, season_alias",
                message="Tournament and season aliases are required",
                details={"tournament_alias": tournament_alias, "season_alias": season_alias}
            )

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    f"{BASE_URL}/tournaments/{tournament_alias}/seasons/{season_alias}"
                ) as response:
                    if response.status != 200:
                        raise ResourceNotFoundException(
                            resource_type="StandingsSettings",
                            resource_id=f"{tournament_alias}/{season_alias}",
                            details={"http_status_code": response.status}
                        )
                    data = await response.json()
                    settings = data.get('standingsSettings')
                    if not settings:
                        raise ResourceNotFoundException(
                            resource_type="StandingsSettings",
                            resource_id=f"{tournament_alias}/{season_alias}",
                            details={"message": "No standings settings found"}
                        )
                    return settings
            except aiohttp.ClientError as e:
                logger.error(f"Failed to fetch standings settings: {str(e)}", extra={
                    "tournament_alias": tournament_alias,
                    "season_alias": season_alias,
                    "error": str(e)
                })
                raise DatabaseOperationException(
                    operation="fetch_standings_settings",
                    message=f"Failed to fetch standings settings: {str(e)}",
                    details={"tournament_alias": tournament_alias, "season_alias": season_alias}
                )

    def calculate_match_stats(
        self,
        match_status: str,
        finish_type: str,
        standings_setting: dict,
        home_score: int = 0,
        away_score: int = 0
    ) -> Dict[str, Dict]:
        """
        Calculate match statistics (points, wins, losses) for both teams.

        Args:
            match_status: Current match status (FINISHED, INPROGRESS, FORFEITED, etc.)
            finish_type: How match finished (REGULAR, OVERTIME, SHOOTOUT)
            standings_setting: Points settings from tournament/season
            home_score: Home team score
            away_score: Away team score

        Returns:
            Dictionary with 'home' and 'away' keys containing stats for each team
        """
        stats = {'home': {}, 'away': {}}

        logger.debug("Calculating stats", extra={
            "match_status": match_status,
            "finish_type": finish_type,
            "score": f"{home_score}-{away_score}"
        })

        def reset_points():
            """Initialize/reset all stats to zero"""
            stats['home']['gamePlayed'] = 0
            stats['home']['goalsFor'] = home_score
            stats['home']['goalsAgainst'] = away_score
            stats['away']['goalsFor'] = away_score
            stats['away']['goalsAgainst'] = home_score

            for team in ['home', 'away']:
                stats[team]['points'] = 0
                stats[team]['win'] = 0
                stats[team]['loss'] = 0
                stats[team]['draw'] = 0
                stats[team]['otWin'] = 0
                stats[team]['otLoss'] = 0
                stats[team]['soWin'] = 0
                stats[team]['soLoss'] = 0

        # Only calculate stats for finished/active matches
        if match_status in ['FINISHED', 'INPROGRESS', 'FORFEITED']:
            logger.debug("Setting match stats")

            reset_points()
            stats['home']['gamePlayed'] = 1
            stats['away']['gamePlayed'] = 1

            if finish_type == 'REGULAR':
                self._calculate_regular_time_stats(stats, standings_setting, home_score, away_score)
            elif finish_type == 'OVERTIME':
                self._calculate_overtime_stats(stats, standings_setting, home_score, away_score)
            elif finish_type == 'SHOOTOUT':
                self._calculate_shootout_stats(stats, standings_setting, home_score, away_score)
            else:
                logger.warning(f"Unknown finish_type: {finish_type}")
                reset_points()
        else:
            logger.debug(f"Skipping stats calculation for match status: {match_status}")
            reset_points()

        return stats

    def _calculate_regular_time_stats(self, stats: dict, settings: dict, home_score: int, away_score: int):
        """Calculate stats for matches finished in regular time"""
        if home_score > away_score:
            # Home team wins in regulation
            stats['home']['win'] = 1
            stats['home']['points'] = settings.get("pointsWinReg", 3)
            stats['away']['loss'] = 1
            stats['away']['points'] = settings.get("pointsLossReg", 0)
        elif home_score < away_score:
            # Away team wins in regulation
            stats['home']['loss'] = 1
            stats['home']['points'] = settings.get("pointsLossReg", 0)
            stats['away']['win'] = 1
            stats['away']['points'] = settings.get("pointsWinReg", 3)
        else:
            # Draw
            stats['home']['draw'] = 1
            stats['home']['points'] = settings.get("pointsDrawReg", 1)
            stats['away']['draw'] = 1
            stats['away']['points'] = settings.get("pointsDrawReg", 1)

    def _calculate_overtime_stats(self, stats: dict, settings: dict, home_score: int, away_score: int):
        """Calculate stats for matches finished in overtime"""
        if home_score > away_score:
            # Home team wins in OT
            stats['home']['otWin'] = 1
            stats['home']['points'] = settings.get("pointsWinOvertime", 2)
            stats['away']['otLoss'] = 1
            stats['away']['points'] = settings.get("pointsLossOvertime", 1)
        else:
            # Away team wins in OT
            stats['home']['otLoss'] = 1
            stats['home']['points'] = settings.get("pointsLossOvertime", 1)
            stats['away']['otWin'] = 1
            stats['away']['points'] = settings.get("pointsWinOvertime", 2)

    def _calculate_shootout_stats(self, stats: dict, settings: dict, home_score: int, away_score: int):
        """Calculate stats for matches finished in shootout"""
        if home_score > away_score:
            # Home team wins in shootout
            stats['home']['soWin'] = 1
            stats['home']['points'] = settings.get("pointsWinShootout", 2)
            stats['away']['soLoss'] = 1
            stats['away']['points'] = settings.get("pointsLossShootout", 1)
        else:
            # Away team wins in shootout
            stats['home']['soLoss'] = 1
            stats['home']['points'] = settings.get("pointsLossShootout", 1)
            stats['away']['soWin'] = 1
            stats['away']['points'] = settings.get("pointsWinShootout", 2)

    # ==================== STANDINGS AGGREGATION ====================

    @log_performance
    async def aggregate_round_standings(self, t_alias: str, s_alias: str, r_alias: str) -> None:
        """
        Aggregate standings for an entire round.

        Args:
            t_alias: Tournament alias
            s_alias: Season alias
            r_alias: Round alias
        """
        if self.db is None:
            raise DatabaseOperationException(operation="initialize_mongodb", message="MongoDB instance required for standings aggregation")

        logger.info("Calculating round standings", extra={
            "tournament_alias": t_alias,
            "season_alias": s_alias,
            "round_alias": r_alias
        })

        r_filter = {
            'alias': t_alias,
            'seasons.alias': s_alias,
            'seasons.rounds.alias': r_alias,
            'seasons': {
                '$elemMatch': {
                    'alias': s_alias,
                    'rounds': {
                        '$elemMatch': {
                            'alias': r_alias
                        }
                    }
                }
            }
        }

        if await self._check_create_standings_for_round(r_filter, s_alias, r_alias):
            matches = await self.db["matches"].find({
                "tournament.alias": t_alias,
                "season.alias": s_alias,
                "round.alias": r_alias
            }).sort("startDate", 1).to_list(length=None)

            if not matches:
                logger.debug("No matches found for round, skipping standings calculation.")
                standings = {}
            else:
                standings = self._calculate_standings(matches)
        else:
            standings = {}
            logger.debug("Standings creation not enabled for this round, skipping.")

        logger.debug("Round standings calculated", extra={"standings": standings})

        try:
            response = await self.db["tournaments"].update_one(
                r_filter,
                {'$set': {
                    "seasons.$[season].rounds.$[round].standings": standings
                }},
                array_filters=[
                    {'season.alias': s_alias},
                    {'round.alias': r_alias}
                ],
                upsert=False)

            if not response.acknowledged:
                raise DatabaseOperationException(
                    operation="update_tournament_standings",
                    message="Failed to update tournament standings.",
                    details={"filter": r_filter}
                )
            else:
                logger.debug("Updated round standings", extra={"standings": standings})
        except Exception as e:
            logger.exception("Unexpected error updating round standings", extra={
                "tournament_alias": t_alias,
                "season_alias": s_alias,
                "round_alias": r_alias,
                "error": str(e)
            })
            raise StatsCalculationException(
                calculation_type="standings",
                message=str(e),
                details={
                    "tournament_alias": t_alias,
                    "season_alias": s_alias,
                    "round_alias": r_alias
                }
            )

    @log_performance
    async def aggregate_matchday_standings(self, t_alias: str, s_alias: str, r_alias: str, md_alias: str) -> None:
        """
        Aggregate standings for a specific matchday.

        Args:
            t_alias: Tournament alias
            s_alias: Season alias
            r_alias: Round alias
            md_alias: Matchday alias
        """
        if self.db is None:
            raise DatabaseOperationException(operation="initialize_mongodb", message="MongoDB instance required for standings aggregation")

        logger.info("Calculating matchday standings", extra={
            "tournament_alias": t_alias,
            "season_alias": s_alias,
            "round_alias": r_alias,
            "matchday_alias": md_alias
        })

        md_filter = {
            'alias': t_alias,
            'seasons.alias': s_alias,
            'seasons.rounds.alias': r_alias,
            'seasons.rounds.matchdays.alias': md_alias,
            'seasons': {
                '$elemMatch': {
                    'alias': s_alias,
                    'rounds': {
                        '$elemMatch': {
                            'alias': r_alias,
                            'matchdays': {
                                '$elemMatch': {
                                    'alias': md_alias
                                }
                            }
                        }
                    }
                }
            }
        }

        if await self._check_create_standings_for_matchday(md_filter, s_alias, r_alias, md_alias):
            matches = await self.db["matches"].find({
                "tournament.alias": t_alias,
                "season.alias": s_alias,
                "round.alias": r_alias,
                "matchday.alias": md_alias
            }).sort("startDate").to_list(1000)

            if not matches:
                logger.debug("No matches found for matchday, skipping standings calculation.")
                standings = {}
            else:
                logger.debug("Calculating standings for matchday.")
                standings = self._calculate_standings(matches)
        else:
            standings = {}
            logger.debug("Standings creation not enabled for this matchday, skipping.")

        try:
            response = await self.db["tournaments"].update_one(
                md_filter,
                {
                    '$set': {
                        "seasons.$[season].rounds.$[round].matchdays.$[matchday].standings": standings
                    }
                },
                array_filters=[
                    {'season.alias': s_alias},
                    {'round.alias': r_alias},
                    {'matchday.alias': md_alias}
                ],
                upsert=False)

            if not response.acknowledged:
                raise DatabaseOperationException(
                    operation="update_tournament_standings",
                    message="Failed to update tournament standings.",
                    details={"filter": md_filter}
                )
            else:
                logger.debug("Updated matchday standings", extra={"standings": standings})
        except Exception as e:
            logger.exception("Unexpected error updating matchday standings", extra={
                "tournament_alias": t_alias,
                "season_alias": s_alias,
                "round_alias": r_alias,
                "matchday_alias": md_alias,
                "error": str(e)
            })
            raise StatsCalculationException(
                calculation_type="standings",
                message=str(e),
                details={
                    "tournament_alias": t_alias,
                    "season_alias": s_alias,
                    "round_alias": r_alias,
                    "matchday_alias": md_alias
                }
            )

    # ==================== HELPER METHODS ====================

    async def _check_create_standings_for_round(self, round_filter: dict, s_alias: str, r_alias: str) -> bool:
        """Check if standings should be created for a round"""
        if (tournament := await self.db['tournaments'].find_one(round_filter)) is not None:
            for season in tournament.get('seasons', []):
                if season.get("alias") == s_alias:
                    for round_data in season.get("rounds", []):
                        if round_data.get("alias") == r_alias:
                            return round_data.get("createStandings", False)
        return False

    async def _check_create_standings_for_matchday(self, md_filter: dict, s_alias: str,
                                                   r_alias: str, md_alias: str) -> bool:
        """Check if standings should be created for a matchday"""
        tournament = await self.db['tournaments'].find_one(md_filter)
        if tournament is not None:
            for season in tournament.get('seasons', []):
                if season.get("alias") == s_alias:
                    for round_data in season.get("rounds", []):
                        if round_data.get("alias") == r_alias:
                            for matchday in round_data.get("matchdays", []):
                                if matchday.get("alias") == md_alias:
                                    return matchday.get("createStandings", False)
        return False

    def _calculate_standings(self, matches: List[dict]) -> dict:
        """
        Calculate standings from a list of matches.

        Args:
            matches: List of match documents

        Returns:
            Dictionary of team standings sorted by points, goal difference, etc.
        """
        standings = {}

        logger.debug(f"Processing {len(matches)} matches for standings calculation")

        for match in matches:
            home_team = {
                'fullName': match['home']['fullName'],
                'shortName': match['home']['shortName'],
                'tinyName': match['home']['tinyName'],
                'logo': match['home']['logo']
            }
            away_team = {
                'fullName': match['away']['fullName'],
                'shortName': match['away']['shortName'],
                'tinyName': match['away']['tinyName'],
                'logo': match['away']['logo']
            }
            h_key = home_team['fullName']
            a_key = away_team['fullName']

            if h_key not in standings:
                standings[h_key] = self._init_team_standings(home_team)
            if a_key not in standings:
                standings[a_key] = self._init_team_standings(away_team)

            # Aggregate stats from match
            standings[h_key]['gamesPlayed'] += match['home']['stats'].get('gamePlayed', 0)
            standings[a_key]['gamesPlayed'] += match['away']['stats'].get('gamePlayed', 0)
            standings[h_key]['goalsFor'] += match['home']['stats'].get('goalsFor', 0)
            standings[h_key]['goalsAgainst'] += match['home']['stats'].get('goalsAgainst', 0)
            standings[a_key]['goalsFor'] += match['away']['stats'].get('goalsFor', 0)
            standings[a_key]['goalsAgainst'] += match['away']['stats'].get('goalsAgainst', 0)
            standings[h_key]['points'] += match['home']['stats'].get('points', 0)
            standings[a_key]['points'] += match['away']['stats'].get('points', 0)
            standings[h_key]['wins'] += match['home']['stats'].get('win', 0)
            standings[a_key]['wins'] += match['away']['stats'].get('win', 0)
            standings[h_key]['losses'] += match['home']['stats'].get('loss', 0)
            standings[a_key]['losses'] += match['away']['stats'].get('loss', 0)
            standings[h_key]['draws'] += match['home']['stats'].get('draw', 0)
            standings[a_key]['draws'] += match['away']['stats'].get('draw', 0)
            standings[h_key]['otWins'] += match['home']['stats'].get('otWin', 0)
            standings[a_key]['otWins'] += match['away']['stats'].get('otWin', 0)
            standings[h_key]['otLosses'] += match['home']['stats'].get('otLoss', 0)
            standings[a_key]['otLosses'] += match['away']['stats'].get('otLoss', 0)
            standings[h_key]['soWins'] += match['home']['stats'].get('soWin', 0)
            standings[a_key]['soWins'] += match['away']['stats'].get('soWin', 0)
            standings[h_key]['soLosses'] += match['home']['stats'].get('soLoss', 0)
            standings[a_key]['soLosses'] += match['away']['stats'].get('soLoss', 0)

            # Update streak
            self._update_streak(standings[h_key], match['home']['stats'])
            self._update_streak(standings[a_key], match['away']['stats'])

        # Sort standings by points, goal difference, goals for, and team name
        sorted_standings = {
            k: v
            for k, v in sorted(
                standings.items(),
                key=lambda item: (
                    item[1]['points'],
                    item[1]['goalsFor'] - item[1]['goalsAgainst'],
                    item[1]['goalsFor'],
                    -ord(item[1]['fullName'][0])
                ),
                reverse=True
            )
        }
        return sorted_standings

    def _init_team_standings(self, team_data: dict) -> dict:
        """Initialize standings structure for a team"""
        from models.tournaments import Standings
        standings_obj = Standings(
            fullName=team_data['fullName'],
            shortName=team_data['shortName'],
            tinyName=team_data['tinyName'],
            logo=team_data['logo'],
            gamesPlayed=0,
            goalsFor=0,
            goalsAgainst=0,
            points=0,
            wins=0,
            losses=0,
            draws=0,
            otWins=0,
            otLosses=0,
            soWins=0,
            soLosses=0,
            streak=[],
        )
        # Convert to dict and ensure logo is a string, not HttpUrl object
        standings_dict = standings_obj.model_dump()
        if standings_dict.get('logo'):
            standings_dict['logo'] = str(standings_dict['logo'])
        return standings_dict

    def _update_streak(self, team_standings: dict, match_stats: dict) -> None:
        """Update the team's streak based on match result"""
        if 'win' in match_stats and match_stats['win'] == 1:
            result = 'W'
        elif 'loss' in match_stats and match_stats['loss'] == 1:
            result = 'L'
        elif 'draw' in match_stats and match_stats['draw'] == 1:
            result = 'D'
        elif 'otWin' in match_stats and match_stats['otWin'] == 1:
            result = 'OTW'
        elif 'otLoss' in match_stats and match_stats['otLoss'] == 1:
            result = 'OTL'
        elif 'soWin' in match_stats and match_stats['soWin'] == 1:
            result = 'SOW'
        elif 'soLoss' in match_stats and match_stats['soLoss'] == 1:
            result = 'SOL'
        else:
            result = None

        if result:
            team_standings['streak'].append(result)
            if len(team_standings['streak']) > 5:
                team_standings['streak'].pop(0)

    # ==================== ROSTER STATISTICS ====================

    @log_performance
    async def calculate_roster_stats(self, match_id: str, team_flag: str, use_db_direct: bool = False) -> None:
        """
        Calculate and update roster statistics for a team in a match.
        Updates goals, assists, points, and penalty minutes for each player.

        Args:
            match_id: The ID of the match
            team_flag: The team flag ('home' or 'away')
            use_db_direct: If True, fetch data directly from DB instead of API (for validation/testing)

        Raises:
            HTTPException: If team_flag is invalid or data cannot be fetched
        """
        if self.db is None:
            raise DatabaseOperationException(operation="initialize_mongodb", message="MongoDB instance required for roster stats calculation")

        # Validate team_flag
        team_flag = team_flag.lower()
        if team_flag not in ['home', 'away']:
            raise ValidationException(
                field="team_flag",
                message=f"Must be 'home' or 'away', got '{team_flag}'",
                details={"provided_value": team_flag}
            )

        logger.info("Calculating roster stats", extra={
            "match_id": match_id,
            "team_flag": team_flag
        })

        try:
            if use_db_direct:
                # Fetch directly from database (for validation/testing)
                roster, scoreboard, penaltysheet = await self._fetch_match_data_from_db(match_id, team_flag)
            else:
                # Fetch via HTTP API (normal operation)
                async with httpx.AsyncClient() as client:
                    roster = await self._fetch_roster(client, match_id, team_flag)
                    scoreboard = await self._fetch_scoreboard(client, match_id, team_flag)
                    penaltysheet = await self._fetch_penaltysheet(client, match_id, team_flag)

            # Initialize player stats from roster
            player_stats = self._initialize_roster_player_stats(roster)

            # Calculate stats from scores
            self._calculate_scoring_stats(scoreboard, player_stats)

            # Calculate stats from penalties
            self._calculate_penalty_stats(penaltysheet, player_stats)

            # Update roster with calculated stats
            updated_roster = self._apply_stats_to_roster(roster, player_stats)

            logger.debug(f"Updated roster with stats", extra={"num_players_updated": len([p for p in player_stats.values() if any(v > 0 for v in p.values())]), "total_players": len(player_stats)})
            logger.debug(f"Player stats summary: {player_stats}")

            # Save updated roster to database
            await self._save_roster_to_db(match_id, team_flag, updated_roster)

        except StatsCalculationException:
            raise
        except ResourceNotFoundException:
            raise
        except ValidationException:
            raise
        except Exception as e:
            logger.exception("Unexpected error in roster stats calculation", extra={
                "match_id": match_id,
                "team_flag": team_flag,
                "error": str(e)
            })
            raise StatsCalculationException(
                calculation_type="roster",
                message=str(e),
                details={"match_id": match_id, "team_flag": team_flag}
            )

    async def _fetch_match_data_from_db(self, match_id: str, team_flag: str) -> tuple:
        """
        Fetch roster, scores, and penalties directly from database.
        Used for validation/testing when API might not be available.

        Returns:
            Tuple of (roster, scoreboard, penaltysheet)
        """
        match = await self.db["matches"].find_one({"_id": match_id})
        if not match:
            raise ResourceNotFoundException(
                resource_type="Match",
                resource_id=match_id,
                details={"team_flag": team_flag}
            )

        team_data = match.get(team_flag, {})
        roster = team_data.get('roster', [])
        scoreboard = team_data.get('scores', [])
        penaltysheet = team_data.get('penalties', [])

        logger.debug("Fetched from DB", extra={"num_roster": len(roster), "num_scores": len(scoreboard), "num_penalties": len(penaltysheet)})

        return roster, scoreboard, penaltysheet

    async def _fetch_roster(self, client: httpx.AsyncClient, match_id: str, team_flag: str) -> List[dict]:
        """Fetch roster for a team from the API"""
        response = await client.get(f"{BASE_URL}/matches/{match_id}/{team_flag}/roster/")
        if response.status_code != 200:
            raise DatabaseOperationException(
                operation="fetch_roster",
                message=f"Failed to fetch roster for {team_flag} team in match {match_id}",
                details={"http_status_code": response.status_code, "match_id": match_id, "team_flag": team_flag}
            )
        return response.json()

    async def _fetch_scoreboard(self, client: httpx.AsyncClient, match_id: str, team_flag: str) -> List[dict]:
        """Fetch scoreboard for a team from the API"""
        response = await client.get(f"{BASE_URL}/matches/{match_id}/{team_flag}/scores/")
        if response.status_code != 200:
            raise DatabaseOperationException(
                operation="fetch_scoreboard",
                message=f"Failed to fetch scoreboard for {team_flag} team in match {match_id}",
                details={"http_status_code": response.status_code, "match_id": match_id, "team_flag": team_flag}
            )
        return response.json()

    async def _fetch_penaltysheet(self, client: httpx.AsyncClient, match_id: str, team_flag: str) -> List[dict]:
        """Fetch penaltysheet for a team from the API"""
        response = await client.get(f"{BASE_URL}/matches/{match_id}/{team_flag}/penalties/")
        if response.status_code != 200:
            raise DatabaseOperationException(
                operation="fetch_penaltysheet",
                message=f"Failed to fetch penaltysheet for {team_flag} team in match {match_id}",
                details={"http_status_code": response.status_code, "match_id": match_id, "team_flag": team_flag}
            )
        return response.json()

    def _initialize_roster_player_stats(self, roster: List[dict]) -> dict:
        """
        Initialize stats dictionary for all players in roster.

        Args:
            roster: List of roster player entries

        Returns:
            Dictionary mapping player_id to initialized stats
        """
        player_stats = {}
        for roster_player in roster:
            player_id = roster_player.get('player', {}).get('playerId')
            if player_id:
                player_stats[player_id] = {
                    'goals': 0,
                    'assists': 0,
                    'points': 0,
                    'penaltyMinutes': 0
                }
        return player_stats

    def _calculate_scoring_stats(self, scoreboard: List[dict], player_stats: dict) -> None:
        """
        Calculate goals and assists from scoreboard.
        Updates player_stats dictionary in place.

        Args:
            scoreboard: List of score entries
            player_stats: Dictionary of player stats to update
        """
        for score in scoreboard:
            # Process goal scorer
            goal_player_id = score.get('goalPlayer', {}).get('playerId')
            if goal_player_id:
                if goal_player_id not in player_stats:
                    player_stats[goal_player_id] = {
                        'goals': 0, 'assists': 0, 'points': 0, 'penaltyMinutes': 0
                    }
                player_stats[goal_player_id]['goals'] += 1
                player_stats[goal_player_id]['points'] += 1

            # Process assist player
            assist_player = score.get('assistPlayer')
            assist_player_id = assist_player.get('playerId') if assist_player else None
            if assist_player_id:
                if assist_player_id not in player_stats:
                    player_stats[assist_player_id] = {
                        'goals': 0, 'assists': 0, 'points': 0, 'penaltyMinutes': 0
                    }
                player_stats[assist_player_id]['assists'] += 1
                player_stats[assist_player_id]['points'] += 1

    def _calculate_penalty_stats(self, penaltysheet: List[dict], player_stats: dict) -> None:
        """
        Calculate penalty minutes from penaltysheet.
        Updates player_stats dictionary in place.

        Args:
            penaltysheet: List of penalty entries
            player_stats: Dictionary of player stats to update
        """
        for penalty in penaltysheet:
            pen_player_id = penalty.get('penaltyPlayer', {}).get('playerId')
            if pen_player_id:
                if pen_player_id not in player_stats:
                    player_stats[pen_player_id] = {
                        'goals': 0, 'assists': 0, 'points': 0, 'penaltyMinutes': 0
                    }
                player_stats[pen_player_id]['penaltyMinutes'] += penalty.get('penaltyMinutes', 0)

    def _apply_stats_to_roster(self, roster: List[dict], player_stats: dict) -> List[dict]:
        """
        Apply calculated stats to roster entries.

        Args:
            roster: Original roster list
            player_stats: Dictionary of calculated player stats

        Returns:
            Updated roster list with stats applied
        """
        for roster_player in roster:
            player_id = roster_player.get('player', {}).get('playerId')
            if player_id and player_id in player_stats:
                roster_player.update(player_stats[player_id])
        return roster

    async def _save_roster_to_db(self, match_id: str, team_flag: str, roster: List[dict]) -> None:
        """
        Save updated roster to the database.

        Args:
            match_id: The match ID
            team_flag: The team flag ('home' or 'away')
            roster: Updated roster list
        """
        if roster:
            try:
                result = await self.db["matches"].update_one(
                    {"_id": match_id},
                    {"$set": {f"{team_flag}.roster": roster}}
                )
                if not result.acknowledged:
                    raise DatabaseOperationException(
                        operation="save_roster",
                        message="Failed to update roster in database",
                        details={"match_id": match_id, "team_flag": team_flag}
                    )
            except Exception as e:
                logger.exception("Could not update roster in mongoDB", extra={
                    "match_id": match_id,
                    "team_flag": team_flag,
                    "error": str(e)
                })
                raise DatabaseOperationException(
                    operation="save_roster",
                    message=f"Could not update roster in mongoDB: {str(e)}",
                    details={"match_id": match_id, "team_flag": team_flag}
                )

    # ==================== PLAYER CARD STATISTICS ====================

    @log_performance
    async def calculate_player_card_stats(self, player_ids: List[str], t_alias: str, s_alias: str,
                                         r_alias: str, md_alias: str, token_payload=None):
        """
        Calculate and update player statistics for a given tournament/season/round/matchday.
        Also handles called matches logic for assignedTeams updates.

        Args:
            player_ids: List of player IDs to calculate stats for
            t_alias: Tournament alias
            s_alias: Season alias
            r_alias: Round alias
            md_alias: Matchday alias
            token_payload: Authentication token payload for API calls
        """
        if self.db is None:
            raise DatabaseOperationException(operation="initialize_mongodb", message="MongoDB instance required for player card stats calculation")

        logger.info("Calculating player card stats", extra={
            "player_ids_count": len(player_ids),
            "tournament_alias": t_alias,
            "season_alias": s_alias,
            "round_alias": r_alias,
            "matchday_alias": md_alias
        })

        if not all([t_alias, s_alias, r_alias, md_alias]):
            logger.warning("Missing tournament, season, round, or matchday alias. Skipping player stats calculation.")
            return

        # Fetch round information
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{BASE_URL}/tournaments/{t_alias}/seasons/{s_alias}/rounds/{r_alias}")
                response.raise_for_status() # Raise HTTPStatusError for bad responses (4xx or 5xx)
                round_info = response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Failed to fetch round information: {str(e)}", extra={
                    "tournament_alias": t_alias,
                    "season_alias": s_alias,
                    "round_alias": r_alias,
                    "http_status_code": e.response.status_code
                })
                raise ResourceNotFoundException(
                    resource_type="Round",
                    resource_id=f"{t_alias}/{s_alias}/{r_alias}",
                    details={"http_status_code": e.response.status_code}
                )
            except httpx.RequestError as e:
                logger.error(f"Network error fetching round information: {str(e)}", extra={
                    "tournament_alias": t_alias,
                    "season_alias": s_alias,
                    "round_alias": r_alias,
                    "error": str(e)
                })
                raise DatabaseOperationException(
                    operation="fetch_round_info",
                    message=f"Network error fetching round info: {str(e)}",
                    details={"tournament_alias": t_alias, "season_alias": s_alias, "round_alias": r_alias}
                )


        # Process round statistics
        matches = []
        if round_info.get('createStats', False):
            matches = await self.db["matches"].find({
                "tournament.alias": t_alias,
                "season.alias": s_alias,
                "round.alias": r_alias
            }).to_list(length=None)

            player_card_stats = {}
            await self._update_player_card_stats("ROUND", matches, player_ids, player_card_stats,
                                                t_alias, s_alias, r_alias, md_alias)

            logger.debug("Round player card stats calculated", extra={"player_card_stats": player_card_stats})
        elif logger.isEnabledFor(logger.DEBUG):
            logger.debug("Round statistics not enabled, skipping.")

        # Process matchday statistics
        for matchday in round_info.get('matchdays', []):
            if matchday.get('createStats', False) and matchday.get('alias') == md_alias: # Ensure we only process the requested matchday
                matchday_matches = await self.db["matches"].find({
                    "tournament.alias": t_alias,
                    "season.alias": s_alias,
                    "round.alias": r_alias,
                    "matchday.alias": md_alias
                }).to_list(length=None)

                player_card_stats = {}
                await self._update_player_card_stats("MATCHDAY", matchday_matches, player_ids,
                                                    player_card_stats, t_alias, s_alias, r_alias, md_alias)

                logger.debug("Matchday player card stats calculated", extra={"player_card_stats": player_card_stats})

                # Update matches for called teams processing if not already done for the round
                if not matches:
                    matches = matchday_matches
            elif logger.isEnabledFor(logger.DEBUG):
                logger.debug(f"Matchday '{matchday.get('alias')}' statistics not enabled or not the target matchday, skipping.")

        # Process called teams assignments
        if matches:
            await self._process_called_teams_assignments(player_ids, matches, t_alias, s_alias, token_payload)

    async def _update_player_card_stats(self, flag: str, matches: List[dict], player_ids: List[str],
                                       player_card_stats: dict, t_alias: str, s_alias: str,
                                       r_alias: str, md_alias: str) -> None:
        """Main function to update player card statistics."""
        if flag not in ['ROUND', 'MATCHDAY']:
            raise ValueError("Invalid flag, only 'ROUND' or 'MATCHDAY' are accepted.")

        logger.debug(f"Processing roster for {flag}", extra={"num_matches": len(matches)})

        # Process rosters for both home and away teams
        self._process_roster_for_team(matches, 'home', player_ids, player_card_stats, flag)
        self._process_roster_for_team(matches, 'away', player_ids, player_card_stats, flag)

        logger.debug("Player card stats updated", extra={"player_card_stats": player_card_stats})

        # Save statistics to database
        await self._save_player_stats_to_db(player_card_stats, t_alias, s_alias, r_alias, md_alias, flag)

    def _process_roster_for_team(self, matches: List[dict], team_flag: str, player_ids: List[str],
                                player_card_stats: dict, flag: str) -> None:
        """Process roster data for a specific team (home/away) across all matches."""
        for match in matches:
            match_info = {
                'tournament': match.get('tournament', {}),
                'season': match.get('season', {}),
                'round': match.get('round', {}),
                'matchday': match.get('matchday', {}) if flag == 'MATCHDAY' else None,
                'match_status': match.get('matchStatus', {})
            }

            roster = match.get(team_flag, {}).get('roster', [])
            team = self._create_team_dict(match.get(team_flag, {}))

            logger.debug(f"Processing {team_flag} roster", extra={"roster_size": len(roster)})

            for roster_player in roster:
                player_id = roster_player.get('player', {}).get('playerId')
                if player_id and player_id in player_ids:
                    logger.debug(f"Updating stats for player {player_id} in {team_flag} team")
                    self._update_player_stats(player_id, team, roster_player, match_info, player_card_stats)

    def _create_team_dict(self, match_team_data: dict) -> dict:
        """Create a standardized team dictionary from match data."""
        return {
            'name': match_team_data.get('name'),
            'fullName': match_team_data.get('fullName'),
            'shortName': match_team_data.get('shortName'),
            'tinyName': match_team_data.get('tinyName')
        }

    def _initialize_player_stats(self, player_id: str, team_key: str, team: dict,
                                 match_info: dict, player_card_stats: dict) -> None:
        """Initialize player stats structure if it doesn't exist."""
        if player_id not in player_card_stats:
            player_card_stats[player_id] = {}

        if team_key not in player_card_stats[player_id]:
            player_card_stats[player_id][team_key] = {
                'tournament': match_info.get('tournament', {}),
                'season': match_info.get('season', {}),
                'round': match_info.get('round', {}),
                'matchday': match_info.get('matchday'),
                'team': team,
                'gamesPlayed': 0,
                'goals': 0,
                'assists': 0,
                'points': 0,
                'penaltyMinutes': 0,
                'calledMatches': 0,
            }

    def _update_player_stats(self, player_id: str, team: dict, roster_player: dict,
                            match_info: dict, player_card_stats: dict) -> None:
        """Update individual player statistics from roster data."""
        team_key = team['fullName']
        self._initialize_player_stats(player_id, team_key, team, match_info, player_card_stats)

        # Only count stats for finished/active matches
        if match_info.get('match_status', {}).get('key') in ['FINISHED', 'INPROGRESS', 'FORFEITED']:
            stats = player_card_stats[player_id][team_key]
            stats['gamesPlayed'] += 1
            stats['goals'] += roster_player.get('goals', 0)
            stats['assists'] += roster_player.get('assists', 0)
            stats['points'] += roster_player.get('points', 0)
            stats['penaltyMinutes'] += roster_player.get('penaltyMinutes', 0)

            # Track called matches
            if roster_player.get('called', False):
                stats['calledMatches'] += 1

    async def _save_player_stats_to_db(self, player_card_stats: dict, t_alias: str, s_alias: str,
                                      r_alias: str, md_alias: str, flag: str) -> None:
        """Save calculated player statistics to the database."""
        logger.debug(f"Saving stats for {len(player_card_stats)} players ({flag})")

        for player_id, stats_by_team in player_card_stats.items():
            for team_key, stats in stats_by_team.items():
                player = await self.db['players'].find_one({"_id": player_id})
                if not player:
                    logger.error(f"Player {player_id} not found in mongoDB, cannot save stats.")
                    raise ResourceNotFoundException(resource_type="Player", resource_id=player_id)

                # Merge with existing stats or create new ones
                existing_stats = player.get('stats', [])
                updated_stats = []
                stat_found = False

                for existing_stat in existing_stats:
                    # Check if this stat entry should be updated
                    if self._should_update_stat(existing_stat, stats, t_alias, s_alias, r_alias, md_alias, flag):
                        merged_stat = {**existing_stat, **stats,
                                      'team': existing_stat.get('team', stats['team'])}
                        updated_stats.append(merged_stat)
                        stat_found = True
                    else:
                        updated_stats.append(existing_stat)

                # Add new stat if no existing one was updated
                if not stat_found:
                    updated_stats.append(stats)

                # Save to database
                try:
                    result = await self.db['players'].update_one(
                        {"_id": player_id},
                        {"$set": {"stats": updated_stats}}
                    )
                    if not result.acknowledged:
                        logger.warning(f"Failed to update stats for player {player_id} in DB.")
                except Exception as e:
                    logger.exception(f"Error updating stats for player {player_id} in DB", extra={"error": str(e)})
                    raise DatabaseOperationException(
                        operation="save_player_stats",
                        message=f"Failed to update stats for player {player_id}: {str(e)}",
                        details={"player_id": player_id}
                    )


    def _should_update_stat(self, existing_stat: dict, new_stats: dict,
                           t_alias: str, s_alias: str, r_alias: str,
                           md_alias: str, flag: str) -> bool:
        """Check if an existing stat entry should be updated with new data."""
        return (existing_stat.get('tournament', {}).get('alias') == t_alias and
                existing_stat.get('season', {}).get('alias') == s_alias and
                existing_stat.get('round', {}).get('alias') == r_alias and
                existing_stat.get('team', {}).get('fullName') == new_stats['team']['fullName'] and
                (existing_stat.get('matchday', {}).get('alias') == md_alias if flag == 'MATCHDAY' else True))

    async def _process_called_teams_assignments(self, player_ids: List[str], matches: List[dict],
                                               t_alias: str, s_alias: str, token_payload) -> None:
        """Check calledMatches for affected players and update assignedTeams if needed."""
        base_url = os.environ.get('BE_API_URL', '')
        if not base_url or not token_payload:
            logger.debug("Skipping called teams processing (no base_url or token)")
            return

        logger.info(f"Checking {len(player_ids)} players for called team assignments...")

        # Prepare authentication headers
        from authentication import AuthHandler
        auth_handler = AuthHandler()
        try:
            auth_token = auth_handler.encode_token({
                "_id": token_payload.sub,
                "roles": token_payload.roles,
                "firstName": token_payload.firstName,
                "lastName": token_payload.lastName,
                "club": {
                    "clubId": token_payload.clubId,
                    "clubName": token_payload.clubName
                } if token_payload.clubId else None
            })
            headers = {"Authorization": f"Bearer {auth_token}"}
        except Exception as e:
            logger.error(f"Failed to encode authentication token: {str(e)}")
            raise DatabaseOperationException(operation="encode_auth_token", message=f"Failed to encode auth token: {str(e)}")


        for player_id in player_ids:
            try:
                async with httpx.AsyncClient() as client:
                    player_response = await client.get(f"{base_url}/players/{player_id}", headers=headers)
                    if player_response.status_code != 200:
                        logger.warning(f"Could not fetch player {player_id} data (Status: {player_response.status_code}). Skipping.", extra={"player_id": player_id})
                        continue

                    player_data = player_response.json()
                    teams_to_check = self._find_called_teams(player_id, matches)

                    await self._update_assigned_teams_for_called_matches(
                        client, player_id, player_data, teams_to_check, t_alias, s_alias, base_url, headers)

            except Exception as e:
                logger.exception(f"Error processing called matches for player {player_id}", extra={"player_id": player_id, "error": str(e)})
                # Continue to next player even if one fails

    def _find_called_teams(self, player_id: str, matches: List[dict]) -> set:
        """Find all teams this player was called for across matches."""
        teams_to_check = set()

        for match in matches:
            for team_flag in ['home', 'away']:
                roster = match.get(team_flag, {}).get('roster', [])
                for roster_player in roster:
                    if (roster_player.get('player', {}).get('playerId') == player_id and
                        roster_player.get('called', False)):
                        current_team = match.get(team_flag, {}).get('team', {})
                        current_club = match.get(team_flag, {}).get('club', {})
                        if current_team and current_club:
                            teams_to_check.add((
                                current_team.get('teamId'),
                                current_team.get('name'),
                                current_team.get('alias'),
                                current_team.get('ageGroup', ''),
                                current_team.get('ishdId'),
                                current_club.get('clubId'),
                                current_club.get('name'),
                                current_club.get('alias'),
                                current_club.get('ishdId')
                            ))

        return teams_to_check

    async def _update_assigned_teams_for_called_matches(self, client, player_id: str, player_data: dict,
                                                       teams_to_check: set, t_alias: str,
                                                       s_alias: str, base_url: str, headers: dict) -> None:
        """Update assignedTeams for players with 5+ called matches."""
        for team_info in teams_to_check:
            (team_id, team_name, team_alias, team_age_group, team_ishd_id,
             club_id, club_name, club_alias, club_ishd_id) = team_info

            # Check if player has 5+ called matches for this team
            player_stats = player_data.get('stats', [])
            for stat in player_stats:
                if (self._has_enough_called_matches(stat, t_alias, s_alias, team_name) and
                    not self._team_already_assigned(player_data, team_id)):

                    await self._add_called_team_assignment(
                        client, player_id, player_data, team_info, base_url, headers)
                    break # Move to the next team if an assignment was made

    def _has_enough_called_matches(self, stat: dict, t_alias: str, s_alias: str, team_name: str) -> bool:
        """Check if a player has enough called matches for a team."""
        return (stat.get('tournament', {}).get('alias') == t_alias and
                stat.get('season', {}).get('alias') == s_alias and
                stat.get('team', {}).get('name') == team_name and
                stat.get('calledMatches', 0) >= 5)

    def _team_already_assigned(self, player_data: dict, team_id: str) -> bool:
        """Check if team is already in player's assignedTeams."""
        assigned_teams = player_data.get('assignedTeams', [])
        for club in assigned_teams:
            for team in club.get('teams', []):
                if team.get('teamId') == team_id:
                    return True
        return False

    async def _add_called_team_assignment(self, client, player_id: str, player_data: dict,
                                         team_info: tuple, base_url: str, headers: dict) -> None:
        """Add a new team assignment with CALLED source."""
        (team_id, team_name, team_alias, team_age_group, team_ishd_id,
         club_id, club_name, club_alias, club_ishd_id) = team_info

        assigned_teams = player_data.get('assignedTeams', [])

        # Try to add to existing club or create new club
        club_found = False
        for club in assigned_teams:
            if club.get('clubId') == club_id:
                club['teams'].append(self._create_team_assignment(team_info))
                club_found = True
                break

        if not club_found and club_id: # Ensure club_id exists before creating a new club entry
            assigned_teams.append(self._create_club_assignment(team_info))

        # Update player in database
        try:
            update_response = await client.patch(
                f"{base_url}/players/{player_id}",
                json={"assignedTeams": assigned_teams},
                headers=headers
            )
            update_response.raise_for_status() # Raise HTTPStatusError for bad responses
            logger.info(f"Added CALLED assignment: Player {player_id} → Team {team_name}")

        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to update assignments for player {player_id} (HTTP {e.response.status_code})", extra={"player_id": player_id, "team_name": team_name, "http_status_code": e.response.status_code})
            raise DatabaseOperationException(
                operation="update_player_assignments",
                message=f"HTTP error updating assignments for player {player_id}: {str(e)}",
                details={"player_id": player_id, "team_name": team_name, "http_status_code": e.response.status_code}
            )
        except httpx.RequestError as e:
            logger.error(f"Network error updating assignments for player {player_id}: {str(e)}", extra={"player_id": player_id, "team_name": team_name, "error": str(e)})
            raise DatabaseOperationException(
                operation="update_player_assignments",
                message=f"Network error updating assignments for player {player_id}: {str(e)}",
                details={"player_id": player_id, "team_name": team_name}
            )


    def _create_team_assignment(self, team_info: tuple) -> dict:
        """Create a team assignment dictionary."""
        team_id, team_name, team_alias, team_age_group, team_ishd_id = team_info[:5]
        return {
            "teamId": team_id,
            "teamName": team_name,
            "teamAlias": team_alias,
            "teamAgeGroup": team_age_group,
            "teamIshdId": team_ishd_id,
            "passNo": "",
            "source": "CALLED",
            "modifyDate": None,
            "active": True,
            "jerseyNo": None
        }

    def _create_club_assignment(self, team_info: tuple) -> dict:
        """Create a club assignment dictionary with team."""
        club_id, club_name, club_alias, club_ishd_id = team_info[5:]
        return {
            "clubId": club_id,
            "clubName": club_name,
            "clubAlias": club_alias,
            "clubIshdId": club_ishd_id,
            "teams": [self._create_team_assignment(team_info)]
        }