
import os
from typing import Dict, List, Optional
import httpx
import aiohttp
from fastapi import HTTPException
from models.tournaments import Standings
from models.matches import MatchStats

DEBUG_LEVEL = int(os.environ.get('DEBUG_LEVEL', 0))
BASE_URL = os.environ.get('BE_API_URL')


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
            raise HTTPException(
                status_code=400,
                detail="Tournament and season aliases are required"
            )

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    f"{BASE_URL}/tournaments/{tournament_alias}/seasons/{season_alias}"
                ) as response:
                    if response.status != 200:
                        raise HTTPException(
                            status_code=404,
                            detail=f"Could not fetch standings settings: Tournament/Season {tournament_alias}/{season_alias} not found"
                        )
                    data = await response.json()
                    settings = data.get('standingsSettings')
                    if not settings:
                        raise HTTPException(
                            status_code=404,
                            detail=f"No standings settings found for {tournament_alias}/{season_alias}"
                        )
                    return settings
            except aiohttp.ClientError as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to fetch standings settings: {str(e)}"
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
        
        if DEBUG_LEVEL > 0:
            print("Calculating match stats...")

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
            if DEBUG_LEVEL > 10:
                print("Setting match stats")
                
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
                print(f"Unknown finish_type: {finish_type}")
                reset_points()
        else:
            if DEBUG_LEVEL > 0:
                print(f"No match stats for matchStatus {match_status}")
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

    async def aggregate_round_standings(self, t_alias: str, s_alias: str, r_alias: str) -> None:
        """
        Aggregate standings for an entire round.
        
        Args:
            t_alias: Tournament alias
            s_alias: Season alias
            r_alias: Round alias
        """
        if not self.db:
            raise ValueError("MongoDB instance required for standings aggregation")
            
        if DEBUG_LEVEL > 0:
            print(f'Calculating standings for {t_alias}, {s_alias}, {r_alias}...')
        
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
                if DEBUG_LEVEL > 0:
                    print(f"No matches for {t_alias}, {s_alias}, {r_alias}")
                standings = {}
            else:
                standings = self._calculate_standings(matches)
        else:
            standings = {}
            if DEBUG_LEVEL > 0:
                print(f"No standings for {t_alias}, {s_alias}, {r_alias}")

        if DEBUG_LEVEL > 20:
            print(f"Standings for {t_alias}, {s_alias}, {r_alias}: {standings}")

        response = await self.db["tournaments"].update_one(
            r_filter,
            {'$set': {
                "seasons.$[season].rounds.$[round].standings": standings
            }},
            array_filters=[{
                'season.alias': s_alias
            }, {
                'round.alias': r_alias
            }],
            upsert=False)
        
        if not response.acknowledged:
            raise HTTPException(status_code=500,
                                detail="Failed to update tournament standings.")
        else:
            if DEBUG_LEVEL > 10:
                print("Updated round standings: ", standings)

    async def aggregate_matchday_standings(self, t_alias: str, s_alias: str, r_alias: str, md_alias: str) -> None:
        """
        Aggregate standings for a specific matchday.
        
        Args:
            t_alias: Tournament alias
            s_alias: Season alias
            r_alias: Round alias
            md_alias: Matchday alias
        """
        if not self.db:
            raise ValueError("MongoDB instance required for standings aggregation")
            
        if DEBUG_LEVEL > 0:
            print(f'Calculating standings for {t_alias}, {s_alias}, {r_alias}, {md_alias}...')
            
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
                if DEBUG_LEVEL > 10:
                    print(f"No matches for {t_alias}, {s_alias}, {r_alias}, {md_alias}")
                standings = {}
            else:
                if DEBUG_LEVEL > 10:
                    print("Calculating standings")
                standings = self._calculate_standings(matches)
        else:
            if DEBUG_LEVEL > 10:
                print(f"No standings for {t_alias}, {s_alias}, {r_alias}, {md_alias}")
            standings = {}

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
            raise HTTPException(status_code=500,
                                detail="Failed to update tournament standings.")
        else:
            if DEBUG_LEVEL > 10:
                print("Updated matchday standings: ", standings)

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
        return Standings(
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
        ).model_dump()

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

    async def calculate_roster_stats(self, match_id: str, team_flag: str) -> None:
        """
        Calculate and update roster statistics for a team in a match.
        Updates goals, assists, points, and penalty minutes for each player.
        
        Args:
            match_id: The ID of the match
            team_flag: The team flag ('home' or 'away')
            
        Raises:
            HTTPException: If team_flag is invalid or data cannot be fetched
        """
        if not self.db:
            raise ValueError("MongoDB instance required for roster stats calculation")
            
        # Validate team_flag
        team_flag = team_flag.lower()
        if team_flag not in ['home', 'away']:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid team flag: {team_flag}. Must be 'home' or 'away'"
            )
        
        if DEBUG_LEVEL > 0:
            print(f'Calculating roster stats ({team_flag})...')
        
        try:
            async with httpx.AsyncClient() as client:
                # Fetch roster
                roster = await self._fetch_roster(client, match_id, team_flag)
                
                # Fetch scoreboard and penaltysheet
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
                
                if DEBUG_LEVEL > 10:
                    print("### player_stats", player_stats)
                    print("### updated roster: ", updated_roster)
                
                # Save updated roster to database
                await self._save_roster_to_db(match_id, team_flag, updated_roster)
                
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to fetch match data: {str(e)}"
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to calculate roster stats: {str(e)}"
            )

    async def _fetch_roster(self, client: httpx.AsyncClient, match_id: str, team_flag: str) -> List[dict]:
        """Fetch roster for a team from the API"""
        response = await client.get(f"{BASE_URL}/matches/{match_id}/{team_flag}/roster/")
        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Failed to fetch roster for {team_flag} team in match {match_id}"
            )
        return response.json()

    async def _fetch_scoreboard(self, client: httpx.AsyncClient, match_id: str, team_flag: str) -> List[dict]:
        """Fetch scoreboard for a team from the API"""
        response = await client.get(f"{BASE_URL}/matches/{match_id}/{team_flag}/scores/")
        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Failed to fetch scoreboard for {team_flag} team in match {match_id}"
            )
        return response.json()

    async def _fetch_penaltysheet(self, client: httpx.AsyncClient, match_id: str, team_flag: str) -> List[dict]:
        """Fetch penaltysheet for a team from the API"""
        response = await client.get(f"{BASE_URL}/matches/{match_id}/{team_flag}/penalties/")
        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Failed to fetch penaltysheet for {team_flag} team in match {match_id}"
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
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to update roster in database"
                    )
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Could not update roster in mongoDB: {str(e)}"
                )

    # ==================== PLACEHOLDER METHODS ====================
    # These will be implemented in subsequent phases

    async def calculate_player_card_stats(self, player_ids: List[str], t_alias: str, s_alias: str, 
                                         r_alias: str, md_alias: str, token_payload=None):
        """Calculate player card statistics - To be implemented in Phase 5"""
        pass
