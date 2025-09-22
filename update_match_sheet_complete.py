
#!/usr/bin/env python
import os
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
import certifi

DB_URL = os.environ["DB_URL"]
DB_NAME = os.environ["DB_NAME"]

async def update_match_sheet_complete():
    """
    Loop through all matches and compare length of scores with stats.goalsFor 
    for home and away teams. If they match, set matchSheetComplete = True.
    """
    client = AsyncIOMotorClient(DB_URL, tlsCAFile=certifi.where())
    db = client[DB_NAME]
    
    try:
        # Get all matches
        matches = await db["matches"].find({}).to_list(None)
        
        updated_count = 0
        total_count = len(matches)
        
        print(f"Processing {total_count} matches...")
        
        for match in matches:
            match_id = match["_id"]
            
            # Get home team data
            home_team = match.get("home", {})
            home_scores = home_team.get("scores", [])
            home_stats = home_team.get("stats", {})
            home_goals_for = home_stats.get("goalsFor", 0)
            
            # Get away team data
            away_team = match.get("away", {})
            away_scores = away_team.get("scores", [])
            away_stats = away_team.get("stats", {})
            away_goals_for = away_stats.get("goalsFor", 0)
            
            # Compare scores length with goalsFor
            home_scores_count = len(home_scores) if home_scores else 0
            away_scores_count = len(away_scores) if away_scores else 0
            
            # Check if match sheet is complete
            is_complete = (home_scores_count == home_goals_for and 
                          away_scores_count == away_goals_for)
            
            current_complete = match.get("matchSheetComplete", False)
            
            # Only update if the value has changed
            if is_complete != current_complete:
                await db["matches"].update_one(
                    {"_id": match_id},
                    {"$set": {"matchSheetComplete": is_complete}}
                )
                updated_count += 1
                
                print(f"Match {match_id}: Updated matchSheetComplete to {is_complete}")
                print(f"  Home: {home_scores_count} scores vs {home_goals_for} goals")
                print(f"  Away: {away_scores_count} scores vs {away_goals_for} goals")
            else:
                print(f"Match {match_id}: No change needed (already {current_complete})")
        
        print(f"\nCompleted! Updated {updated_count} out of {total_count} matches.")
        
    except Exception as e:
        print(f"Error: {str(e)}")
    finally:
        client.close()

if __name__ == "__main__":
    asyncio.run(update_match_sheet_complete())
