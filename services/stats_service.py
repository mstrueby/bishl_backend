
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

    # ==================== PLACEHOLDER METHODS ====================
    # These will be implemented in subsequent phases

    async def aggregate_round_standings(self, t_alias: str, s_alias: str, r_alias: str):
        """Aggregate standings for entire round - To be implemented in Phase 3"""
        pass

    async def aggregate_matchday_standings(self, t_alias: str, s_alias: str, r_alias: str, md_alias: str):
        """Aggregate standings for specific matchday - To be implemented in Phase 3"""
        pass

    async def calculate_roster_stats(self, match_id: str, team_flag: str):
        """Calculate roster stats for a team - To be implemented in Phase 4"""
        pass

    async def calculate_player_card_stats(self, player_ids: List[str], t_alias: str, s_alias: str, 
                                         r_alias: str, md_alias: str, token_payload=None):
        """Calculate player card statistics - To be implemented in Phase 5"""
        pass
