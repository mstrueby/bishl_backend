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
    
    async def analyze_ref_admin_workflow_issues(self) -> Dict[str, Any]:
        """
        Specific analysis of REF_ADMIN workflow issues
        Returns detailed statistics about the assignment workflow problems
        """
        analysis = {
            'total_assigned_status': 0,
            'properly_set_in_match': 0,
            'missing_from_match': 0,
            'wrong_referee_in_match': 0,
            'issues_by_position': {'1': 0, '2': 0},
            'issues_by_tournament': {},
            'issues_by_referee': {},
            'recent_issues': [],
            'oldest_issue_date': None
        }
        
        # Get all assignments with status ASSIGNED
        assignments = await self.db.assignments.find({
            "status": "ASSIGNED"
        }).to_list(None)
        
        analysis['total_assigned_status'] = len(assignments)
        
        for assignment in assignments:
            match_id = assignment.get('matchId')
            referee_user_id = assignment.get('referee', {}).get('userId')
            position = assignment.get('position')
            
            if not match_id or not referee_user_id or not position:
                continue
                
            # Get the corresponding match
            match = await self.db.matches.find_one({"_id": match_id})
            
            if not match:
                continue
                
            # Check if the referee is properly set in the match
            match_referee_key = f"referee{position}"
            match_referee = match.get(match_referee_key)
            
            if not match_referee:
                # Issue: Referee not set in match at all
                analysis['missing_from_match'] += 1
                analysis['issues_by_position'][str(position)] += 1
                
                # Track by tournament
                tournament = match.get('tournament', {}).get('name', 'Unknown')
                if tournament not in analysis['issues_by_tournament']:
                    analysis['issues_by_tournament'][tournament] = 0
                analysis['issues_by_tournament'][tournament] += 1
                
                # Track by referee
                referee_name = f"{assignment.get('referee', {}).get('firstName', '')} {assignment.get('referee', {}).get('lastName', '')}".strip()
                if not referee_name:
                    referee_name = f"Unknown ({referee_user_id})"
                if referee_name not in analysis['issues_by_referee']:
                    analysis['issues_by_referee'][referee_name] = {
                        'missing_from_match': 0,
                        'wrong_referee_in_match': 0,
                        'total_issues': 0,
                        'userId': referee_user_id,
                        'club': assignment.get('referee', {}).get('clubName', 'Unknown')
                    }
                analysis['issues_by_referee'][referee_name]['missing_from_match'] += 1
                analysis['issues_by_referee'][referee_name]['total_issues'] += 1
                
                # Track recent issues (get assignment creation date from statusHistory)
                status_history = assignment.get('statusHistory', [])
                assigned_entry = None
                for entry in status_history:
                    if entry.get('status') == 'ASSIGNED':
                        assigned_entry = entry
                        break
                
                if assigned_entry:
                    issue_date = assigned_entry.get('updateDate')
                    if issue_date:
                        analysis['recent_issues'].append({
                            'assignment_id': assignment.get('_id'),
                            'match_id': match_id,
                            'referee_name': f"{assignment.get('referee', {}).get('firstName', '')} {assignment.get('referee', {}).get('lastName', '')}",
                            'position': position,
                            'tournament': tournament,
                            'assigned_date': issue_date,
                            'match_date': match.get('startDate'),
                            'assigned_by': assigned_entry.get('updatedByName', 'Unknown')
                        })
                        
                        # Track oldest issue
                        if not analysis['oldest_issue_date'] or issue_date < analysis['oldest_issue_date']:
                            analysis['oldest_issue_date'] = issue_date
                            
            elif match_referee.get('userId') != referee_user_id:
                # Issue: Different referee is set in match
                analysis['wrong_referee_in_match'] += 1
                analysis['issues_by_position'][str(position)] += 1
                
                # Track by referee
                referee_name = f"{assignment.get('referee', {}).get('firstName', '')} {assignment.get('referee', {}).get('lastName', '')}".strip()
                if not referee_name:
                    referee_name = f"Unknown ({referee_user_id})"
                if referee_name not in analysis['issues_by_referee']:
                    analysis['issues_by_referee'][referee_name] = {
                        'missing_from_match': 0,
                        'wrong_referee_in_match': 0,
                        'total_issues': 0,
                        'userId': referee_user_id,
                        'club': assignment.get('referee', {}).get('clubName', 'Unknown')
                    }
                analysis['issues_by_referee'][referee_name]['wrong_referee_in_match'] += 1
                analysis['issues_by_referee'][referee_name]['total_issues'] += 1
            else:
                # Properly set
                analysis['properly_set_in_match'] += 1
        
        # Sort recent issues by date (newest first)
        analysis['recent_issues'].sort(key=lambda x: x['assigned_date'], reverse=True)
        
        return analysis
    
    async def print_ref_admin_analysis(self, analysis: Dict[str, Any]):
        """Print detailed analysis of REF_ADMIN workflow issues"""
        print("\n" + "="*80)
        print("REF_ADMIN WORKFLOW ANALYSIS")
        print("="*80)
        
        total = analysis['total_assigned_status']
        properly_set = analysis['properly_set_in_match']
        missing = analysis['missing_from_match']
        wrong = analysis['wrong_referee_in_match']
        
        print(f"Total assignments with ASSIGNED status: {total}")
        print(f"✅ Properly set in match: {properly_set} ({properly_set/total*100:.1f}%)" if total > 0 else "✅ Properly set in match: 0")
        print(f"❌ Missing from match: {missing} ({missing/total*100:.1f}%)" if total > 0 else "❌ Missing from match: 0")
        print(f"⚠️  Wrong referee in match: {wrong} ({wrong/total*100:.1f}%)" if total > 0 else "⚠️  Wrong referee in match: 0")
        
        if missing > 0 or wrong > 0:
            print(f"\n🚨 WORKFLOW SUCCESS RATE: {properly_set/total*100:.1f}%" if total > 0 else "🚨 WORKFLOW SUCCESS RATE: N/A")
            
            print(f"\nIssues by position:")
            print(f"  Referee 1: {analysis['issues_by_position']['1']} issues")
            print(f"  Referee 2: {analysis['issues_by_position']['2']} issues")
            
            if analysis['issues_by_tournament']:
                print(f"\nIssues by tournament:")
                for tournament, count in sorted(analysis['issues_by_tournament'].items(), key=lambda x: x[1], reverse=True):
                    print(f"  {tournament}: {count} issues")
            
            if analysis['issues_by_referee']:
                print(f"\nIssues by referee (Top 10):")
                sorted_referees = sorted(analysis['issues_by_referee'].items(), key=lambda x: x[1]['total_issues'], reverse=True)
                for referee_name, referee_data in sorted_referees[:10]:
                    print(f"  {referee_name} ({referee_data['club']}): {referee_data['total_issues']} issues")
                    if referee_data['missing_from_match'] > 0:
                        print(f"    - Missing from match: {referee_data['missing_from_match']}")
                    if referee_data['wrong_referee_in_match'] > 0:
                        print(f"    - Wrong referee in match: {referee_data['wrong_referee_in_match']}")
                
                if len(sorted_referees) > 10:
                    print(f"  ... and {len(sorted_referees) - 10} more referees with issues")
            
            if analysis['oldest_issue_date']:
                print(f"\nOldest unresolved issue: {analysis['oldest_issue_date'].strftime('%Y-%m-%d %H:%M:%S')}")
            
            print(f"\nRecent issues (last 10):")
            for issue in analysis['recent_issues'][:10]:
                print(f"  {issue['assigned_date'].strftime('%Y-%m-%d %H:%M')} - {issue['referee_name']} (Pos {issue['position']}) for {issue['tournament']}")
                print(f"    Assigned by: {issue['assigned_by']}")
                print(f"    Match: {issue['match_date'].strftime('%Y-%m-%d %H:%M') if issue['match_date'] else 'No date'}")
        else:
            print("\n✅ All ASSIGNED referees are properly set in their matches!")
        
        return analysis
    
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
        ref_admin_issues = 0
        for conflict in conflicts:
            conflict_type = conflict['type']
            if conflict_type not in conflicts_by_type:
                conflicts_by_type[conflict_type] = []
            conflicts_by_type[conflict_type].append(conflict)
            
            # Count REF_ADMIN specific issues (ASSIGNED status but not in match)
            if conflict_type == 'REFEREE_NOT_SET_IN_MATCH':
                ref_admin_issues += 1
        
        # Print summary of REF_ADMIN workflow issues
        if ref_admin_issues > 0:
            print(f"\n🚨 REF_ADMIN WORKFLOW ISSUES: {ref_admin_issues} cases")
            print("These are referees with status ASSIGNED but not set in match documents.")
            print("This indicates the REF_ADMIN assignment workflow is broken.")
            print("-" * 60)
            
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
        
        # Run specific REF_ADMIN workflow analysis
        analysis = await checker.analyze_ref_admin_workflow_issues()
        await checker.print_ref_admin_analysis(analysis)
        
        print("\n" + "="*80)
        print("Check completed!")
        
        if conflicts:
            print("\n💡 Recommended actions:")
            print("1. Review each conflict to determine the correct referee assignment")
            print("2. Update either the assignment record or the match document to resolve conflicts")
            print("3. Consider running this check regularly to catch future inconsistencies")
            
        workflow_issues = analysis['missing_from_match'] + analysis['wrong_referee_in_match']
        if workflow_issues > 0:
            print("\n🔧 REF_ADMIN Workflow Issues:")
            print("1. Check if the set_referee_in_match() function is working properly")
            print("2. Review the assignment creation/update process in routers/assignments.py")
            print("3. Consider adding transaction rollback if match update fails")
            print("4. Add logging to track when assignments succeed but match updates fail")
            
            # Show if issues are concentrated on specific referees
            if analysis['issues_by_referee']:
                total_referees_with_issues = len(analysis['issues_by_referee'])
                referees_with_multiple_issues = sum(1 for ref_data in analysis['issues_by_referee'].values() if ref_data['total_issues'] > 1)
                
                print(f"\n📊 Referee Impact Analysis:")
                print(f"   - Total referees affected: {total_referees_with_issues}")
                print(f"   - Referees with multiple issues: {referees_with_multiple_issues}")
                
                if referees_with_multiple_issues > 0:
                    print(f"   - This suggests the issue may be systemic rather than referee-specific")
                else:
                    print(f"   - Issues appear to be distributed across different referees")
        
    except Exception as e:
        print(f"❌ Error occurred: {str(e)}")
        raise
    finally:
        await checker.close()

if __name__ == "__main__":
    asyncio.run(main())
