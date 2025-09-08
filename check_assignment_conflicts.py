#!/usr/bin/env python
import asyncio
import motor.motor_asyncio
import os
from typing import List, Dict, Any
import argparse
from datetime import datetime

class AssignmentConflictChecker:
    def __init__(self, is_prod: bool = False):
        if is_prod:
            DB_URL = os.environ['DB_URL_PROD']
            DB_NAME = 'bishl'
        else:
            DB_URL = os.environ['DB_URL']
            DB_NAME = 'bishl_dev'
        
        self.client = motor.motor_asyncio.AsyncIOMotorClient(DB_URL)
        self.db = self.client[DB_NAME]
        self.is_prod = is_prod
        
    async def close(self):
        self.client.close()
        
    async def check_assignment_conflicts(self) -> List[Dict[str, Any]]:
        """
        Check for conflicts between assignments collection and match documents
        Returns list of conflicts found
        """
        conflicts = []
        
        # Get all assignments with status ASSIGNED
        assignments = await self.db.assignments.find({
            "status": "ASSIGNED"
        }).to_list(None)
        
        print(f"Found {len(assignments)} assignments with status ASSIGNED")
        
        for assignment in assignments:
            match_id = assignment.get('matchId')
            referee_user_id = assignment.get('referee', {}).get('userId')
            position = assignment.get('position')
            
            if not match_id or not referee_user_id or not position:
                print(f"Skipping assignment {assignment.get('_id')} - missing required fields")
                continue
                
            # Get the corresponding match
            match = await self.db.matches.find_one({"_id": match_id})
            
            if not match:
                conflicts.append({
                    'type': 'MATCH_NOT_FOUND',
                    'assignment_id': assignment.get('_id'),
                    'match_id': match_id,
                    'assigned_referee': assignment.get('referee'),
                    'position': position,
                    'issue': f"Match with ID {match_id} not found"
                })
                continue
                
            # Check if the referee is properly set in the match
            match_referee_key = f"referee{position}"
            match_referee = match.get(match_referee_key)
            
            if not match_referee:
                # Referee is not set in match at all
                conflicts.append({
                    'type': 'REFEREE_NOT_SET_IN_MATCH',
                    'assignment_id': assignment.get('_id'),
                    'match_id': match_id,
                    'assigned_referee': assignment.get('referee'),
                    'position': position,
                    'match_referee': None,
                    'match_info': {
                        'tournament': match.get('tournament', {}).get('name'),
                        'home_team': match.get('home', {}).get('fullName'),
                        'away_team': match.get('away', {}).get('fullName'),
                        'start_date': match.get('startDate'),
                        'referee1': match.get('referee1'),
                        'referee2': match.get('referee2')
                    },
                    'issue': f"Referee not set in match at position {position}"
                })
            elif match_referee.get('userId') != referee_user_id:
                # Different referee is set in match
                conflicts.append({
                    'type': 'REFEREE_MISMATCH',
                    'assignment_id': assignment.get('_id'),
                    'match_id': match_id,
                    'assigned_referee': assignment.get('referee'),
                    'position': position,
                    'match_referee': match_referee,
                    'match_info': {
                        'tournament': match.get('tournament', {}).get('name'),
                        'home_team': match.get('home', {}).get('fullName'),
                        'away_team': match.get('away', {}).get('fullName'),
                        'start_date': match.get('startDate'),
                        'referee1': match.get('referee1'),
                        'referee2': match.get('referee2')
                    },
                    'issue': f"Different referee in match: assigned={referee_user_id}, match={match_referee.get('userId')}"
                })
                
        return conflicts
    
    async def print_conflicts_report(self, conflicts: List[Dict[str, Any]]):
        """Print a detailed report of conflicts found"""
        print("\n" + "="*80)
        print(f"ASSIGNMENT-MATCH CONFLICTS REPORT")
        print(f"Database: {'PRODUCTION' if self.is_prod else 'DEVELOPMENT'}")
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Total conflicts found: {len(conflicts)}")
        print("="*80)
        
        if not conflicts:
            print("✅ No conflicts found! All assignments are properly synchronized with matches.")
            return
            
        # Group conflicts by type
        conflicts_by_type = {}
        for conflict in conflicts:
            conflict_type = conflict['type']
            if conflict_type not in conflicts_by_type:
                conflicts_by_type[conflict_type] = []
            conflicts_by_type[conflict_type].append(conflict)
            
        for conflict_type, type_conflicts in conflicts_by_type.items():
            print(f"\n🚨 {conflict_type} ({len(type_conflicts)} cases):")
            print("-" * 60)
            
            for i, conflict in enumerate(type_conflicts, 1):
                print(f"\n{i}. Assignment ID: {conflict['assignment_id']}")
                print(f"   Match ID: {conflict['match_id']}")
                print(f"   Position: {conflict['position']}")
                print(f"   Issue: {conflict['issue']}")
                
                # Print assigned referee info
                assigned_ref = conflict['assigned_referee']
                print(f"   Assigned Referee: {assigned_ref.get('firstName')} {assigned_ref.get('lastName')} ({assigned_ref.get('userId')})")
                if assigned_ref.get('clubName'):
                    print(f"                    Club: {assigned_ref.get('clubName')}")
                
                # Print match referee info if available
                if conflict.get('match_referee'):
                    match_ref = conflict['match_referee']
                    print(f"   Match Referee: {match_ref.get('firstName')} {match_ref.get('lastName')} ({match_ref.get('userId')})")
                    if match_ref.get('clubName'):
                        print(f"                 Club: {match_ref.get('clubName')}")
                
                # Print match info if available
                if conflict.get('match_info'):
                    match_info = conflict['match_info']
                    print(f"   Match Details:")
                    print(f"     Tournament: {match_info.get('tournament')}")
                    print(f"     Teams: {match_info.get('home_team')} vs {match_info.get('away_team')}")
                    if match_info.get('start_date'):
                        print(f"     Date: {match_info.get('start_date')}")
                    print(f"     Current Referees:")
                    if match_info.get('referee1'):
                        ref1 = match_info['referee1']
                        print(f"       Referee1: {ref1.get('firstName')} {ref1.get('lastName')} ({ref1.get('userId')})")
                    else:
                        print(f"       Referee1: Not set")
                    if match_info.get('referee2'):
                        ref2 = match_info['referee2']
                        print(f"       Referee2: {ref2.get('firstName')} {ref2.get('lastName')} ({ref2.get('userId')})")
                    else:
                        print(f"       Referee2: Not set")

async def main():
    parser = argparse.ArgumentParser(description='Check for assignment-match conflicts')
    parser.add_argument('--prod', action='store_true', 
                       help='Use production database (default: development)')
    
    args = parser.parse_args()
    
    checker = AssignmentConflictChecker(is_prod=args.prod)
    
    try:
        print(f"Checking assignment conflicts in {'PRODUCTION' if args.prod else 'DEVELOPMENT'} database...")
        print("This may take a moment...\n")
        
        conflicts = await checker.check_assignment_conflicts()
        await checker.print_conflicts_report(conflicts)
        
        print("\n" + "="*80)
        print("Check completed!")
        
        if conflicts:
            print("\n💡 Recommended actions:")
            print("1. Review each conflict to determine the correct referee assignment")
            print("2. Update either the assignment record or the match document to resolve conflicts")
            print("3. Consider running this check regularly to catch future inconsistencies")
        
    except Exception as e:
        print(f"❌ Error occurred: {str(e)}")
        raise
    finally:
        await checker.close()

if __name__ == "__main__":
    asyncio.run(main())
