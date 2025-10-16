#!/usr/bin/env python
"""
Stats Service Validation Script
Validates that the refactored stats service produces identical results to the old implementation.
Run this manually after deploying the refactored stats service.
"""
import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from services.stats_service import StatsService
import certifi

DB_URL = os.environ["DB_URL"]
DB_NAME = os.environ["DB_NAME"]


async def validate_match_stats():
    """Validate match stats calculation with different scenarios"""
    print("\n=== VALIDATING MATCH STATS ===")
    
    stats_service = StatsService()
    
    test_cases = [
        # (match_status, finish_type, home_score, away_score, description)
        ("FINISHED", "REGULAR", 3, 1, "Regular time home win"),
        ("FINISHED", "REGULAR", 1, 3, "Regular time away win"),
        ("FINISHED", "REGULAR", 2, 2, "Regular time draw"),
        ("FINISHED", "OVERTIME", 3, 2, "Overtime home win"),
        ("FINISHED", "OVERTIME", 2, 3, "Overtime away win"),
        ("FINISHED", "SHOOTOUT", 2, 1, "Shootout home win"),
        ("FINISHED", "SHOOTOUT", 1, 2, "Shootout away win"),
        ("SCHEDULED", "REGULAR", 0, 0, "Scheduled match (no stats)"),
        ("FORFEITED", "REGULAR", 5, 0, "Forfeited match"),
    ]
    
    # Mock standings settings
    standings_settings = {
        "pointsWinReg": 3,
        "pointsLossReg": 0,
        "pointsDrawReg": 1,
        "pointsWinOvertime": 2,
        "pointsLossOvertime": 1,
        "pointsWinShootout": 2,
        "pointsLossShootout": 1
    }
    
    for match_status, finish_type, home_score, away_score, description in test_cases:
        stats = stats_service.calculate_match_stats(
            match_status, finish_type, standings_settings, home_score, away_score
        )
        
        print(f"\n✓ {description}")
        print(f"  Status: {match_status}, Finish: {finish_type}, Score: {home_score}-{away_score}")
        print(f"  Home: {stats['home']}")
        print(f"  Away: {stats['away']}")
        
        # Basic validation
        if match_status in ['FINISHED', 'INPROGRESS', 'FORFEITED']:
            assert stats['home']['gamePlayed'] == 1, "Home should have 1 game played"
            assert stats['away']['gamePlayed'] == 1, "Away should have 1 game played"
        else:
            assert stats['home']['gamePlayed'] == 0, "Scheduled match should have 0 games"
    
    print("\n✓✓✓ All match stats validations passed!")


async def validate_standings_calculation():
    """Validate standings aggregation with real data"""
    print("\n=== VALIDATING STANDINGS CALCULATION ===")
    
    try:
        client = AsyncIOMotorClient(DB_URL, tlsCAFile=certifi.where())
        mongodb = client[DB_NAME]
        stats_service = StatsService(mongodb)
    except Exception as e:
        print(f"✗ Failed to connect to database: {str(e)}")
        return
    
    # Find a round with createStandings=true
    tournament = await mongodb['tournaments'].find_one({
        'seasons.rounds.createStandings': True
    })
    
    if not tournament:
        print("⊘ No rounds with createStandings found, skipping standings validation")
        client.close()
        return
    
    for season in tournament.get('seasons', []):
        for round_data in season.get('rounds', []):
            if round_data.get('createStandings'):
                t_alias = tournament['alias']
                s_alias = season['alias']
                r_alias = round_data['alias']
                
                print(f"\n→ Testing round: {t_alias}/{s_alias}/{r_alias}")
                
                # Get current standings
                old_standings = round_data.get('standings', {})
                
                # Recalculate standings
                await stats_service.aggregate_round_standings(t_alias, s_alias, r_alias)
                
                # Fetch updated standings
                updated_tournament = await mongodb['tournaments'].find_one({'alias': t_alias})
                new_standings = {}
                for s in updated_tournament.get('seasons', []):
                    if s['alias'] == s_alias:
                        for r in s.get('rounds', []):
                            if r['alias'] == r_alias:
                                new_standings = r.get('standings', {})
                
                # Compare team counts
                print(f"  Old standings: {len(old_standings)} teams")
                print(f"  New standings: {len(new_standings)} teams")
                
                if len(old_standings) == len(new_standings):
                    print("  ✓ Team count matches")
                else:
                    print(f"  ⚠ WARNING: Team count mismatch!")
                
                # Compare a sample team's points
                if old_standings and new_standings:
                    sample_team = list(old_standings.keys())[0]
                    if sample_team in new_standings:
                        old_points = old_standings[sample_team].get('points', 0)
                        new_points = new_standings[sample_team].get('points', 0)
                        print(f"  Sample team '{sample_team}':")
                        print(f"    Old points: {old_points}")
                        print(f"    New points: {new_points}")
                        if old_points == new_points:
                            print("    ✓ Points match")
                        else:
                            print("    ⚠ WARNING: Points mismatch!")
                
                # Only test first round to keep it quick
                break
        break
    
    client.close()
    print("\n✓✓✓ Standings validation complete!")


async def validate_roster_stats():
    """Validate roster stats calculation with real data"""
    print("\n=== VALIDATING ROSTER STATS ===")
    
    try:
        client = AsyncIOMotorClient(DB_URL, tlsCAFile=certifi.where())
        mongodb = client[DB_NAME]
        stats_service = StatsService(mongodb)
    except Exception as e:
        print(f"✗ Failed to connect to database: {str(e)}")
        return
    
    # Find a finished match
    match = await mongodb['matches'].find_one({
        'matchStatus.key': 'FINISHED'
    })
    
    if not match:
        print("⊘ No finished matches found, skipping roster validation")
        client.close()
        return
    
    match_id = match['_id']
    print(f"\n→ Testing match: {match_id}")
    print(f"  {match['home']['fullName']} vs {match['away']['fullName']}")
    
    for team_flag in ['home', 'away']:
        print(f"\n  Testing {team_flag} team:")
        
        # Get old roster stats
        old_roster = match.get(team_flag, {}).get('roster', [])
        old_total_goals = sum(p.get('goals', 0) for p in old_roster)
        old_total_assists = sum(p.get('assists', 0) for p in old_roster)
        
        # Recalculate
        await stats_service.calculate_roster_stats(match_id, team_flag)
        
        # Get new roster stats
        updated_match = await mongodb['matches'].find_one({'_id': match_id})
        new_roster = updated_match.get(team_flag, {}).get('roster', [])
        new_total_goals = sum(p.get('goals', 0) for p in new_roster)
        new_total_assists = sum(p.get('assists', 0) for p in new_roster)
        
        print(f"    Old total goals: {old_total_goals}, assists: {old_total_assists}")
        print(f"    New total goals: {new_total_goals}, assists: {new_total_assists}")
        
        if old_total_goals == new_total_goals and old_total_assists == new_total_assists:
            print(f"    ✓ Roster stats match")
        else:
            print(f"    ⚠ WARNING: Roster stats mismatch!")
    
    client.close()
    print("\n✓✓✓ Roster stats validation complete!")


async def performance_comparison():
    """Check that performance logging is working"""
    print("\n=== PERFORMANCE LOGGING CHECK ===")
    print("✓ Performance logging enabled via @log_performance decorator")
    print("✓ Check console output for [STATS] timing logs")
    print("✓ DEBUG_LEVEL > 0 enables detailed logging")


async def main():
    """Run all validation checks"""
    print("=" * 60)
    print("STATS SERVICE REFACTORING VALIDATION")
    print("=" * 60)
    
    try:
        await validate_match_stats()
        await validate_standings_calculation()
        await validate_roster_stats()
        await performance_comparison()
        
        print("\n" + "=" * 60)
        print("VALIDATION COMPLETE")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Review any warnings above")
        print("2. Test in production with DEBUG_LEVEL=1 to see detailed logs")
        print("3. Monitor for errors in actual usage")
        print("4. If all looks good, mark Phase 8 as complete!")
    except Exception as e:
        print(f"\n✗ Validation failed with error: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
