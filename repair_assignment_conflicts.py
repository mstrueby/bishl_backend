#!/usr/bin/env python
import asyncio
import motor.motor_asyncio
import os
from dotenv import load_dotenv
import argparse

load_dotenv()

async def repair_assignment_conflicts(is_prod=False):
    """Repair conflicts between assignments and matches"""
    
    if is_prod:
        DB_URL = os.environ['DB_URL_PROD']
        DB_NAME = 'bishl'
    else:
        DB_URL = os.environ['DB_URL']
        DB_NAME = 'bishl_dev'
    
    client = motor.motor_asyncio.AsyncIOMotorClient(DB_URL)
    db = client[DB_NAME]
    
    print(f"Repairing assignment conflicts in {'PRODUCTION' if is_prod else 'DEVELOPMENT'} database...")
    
    # Get all ASSIGNED assignments
    assignments = await db.assignments.find({"status": "ASSIGNED"}).to_list(None)
    
    repaired = 0
    errors = 0
    
    for assignment in assignments:
        match_id = assignment.get('matchId')
        referee = assignment.get('referee', {})
        position = assignment.get('position')
        
        if not match_id or not referee.get('userId') or not position:
            print(f"Skipping assignment {assignment.get('_id')} - missing required fields")
            continue
        
        # Get the match
        match = await db.matches.find_one({"_id": match_id})
        if not match:
            print(f"Match {match_id} not found for assignment {assignment.get('_id')}")
            errors += 1
            continue
        
        # Check if referee is properly set in match
        match_referee = match.get(f'referee{position}')
        
        if not match_referee or match_referee.get('userId') != referee.get('userId'):
            # Fix the conflict using a transaction
            async with await client.start_session() as session:
                async with session.start_transaction():
                    try:
                        # Update match with correct referee
                        await db.matches.update_one(
                            {'_id': match_id},
                            {'$set': {
                                f'referee{position}': {
                                    'userId': referee['userId'],
                                    'firstName': referee['firstName'],
                                    'lastName': referee['lastName'],
                                    'clubId': referee.get('clubId'),
                                    'clubName': referee.get('clubName'),
                                    'logoUrl': referee.get('logoUrl'),
                                }
                            }},
                            session=session
                        )
                        
                        print(f"✓ Repaired: Assignment {assignment.get('_id')} - Match {match_id} - Position {position} - Referee {referee['firstName']} {referee['lastName']}")
                        repaired += 1
                        
                    except Exception as e:
                        print(f"✗ Error repairing assignment {assignment.get('_id')}: {str(e)}")
                        errors += 1
    
    client.close()
    
    print(f"\n{'='*80}")
    print(f"Repair Summary:")
    print(f"  Total ASSIGNED assignments: {len(assignments)}")
    print(f"  Conflicts repaired: {repaired}")
    print(f"  Errors: {errors}")
    print(f"{'='*80}")

async def main():
    parser = argparse.ArgumentParser(description='Repair assignment-match synchronization conflicts')
    parser.add_argument('--prod', action='store_true', 
                       help='Use production database (default: development)')
    
    args = parser.parse_args()
    
    await repair_assignment_conflicts(is_prod=args.prod)

if __name__ == "__main__":
    asyncio.run(main())
