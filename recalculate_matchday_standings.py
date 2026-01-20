import asyncio

from motor.motor_asyncio import AsyncIOMotorClient

from config import MONGODB_URI
from services.stats_service import StatsService


async def recalculate_standings(
    tournament_alias: str, season_alias: str, round_alias: str, matchday_alias: str
):
    """Manually recalculate standings for a specific matchday"""
    client = AsyncIOMotorClient(MONGODB_URI)
    db = client.bishl_db

    stats_service = StatsService(db)
    await stats_service.aggregate_matchday_standings(
        tournament_alias, season_alias, round_alias, matchday_alias
    )

    print(
        f"✓ Recalculated standings for {tournament_alias}/{season_alias}/{round_alias}/{matchday_alias}"
    )

    client.close()


if __name__ == "__main__":
    # Example usage - update these values for your matchday
    asyncio.run(
        recalculate_standings(
            tournament_alias="jugendliga",
            season_alias="2025",
            round_alias="hauptrunde",
            matchday_alias="eintracht-falkensee",  # Replace with your matchday alias
        )
    )
