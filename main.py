#!/usr/bin/env python
import os
from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient
#import uvicorn
from routers.root import router as root_router
from routers.configs import router as configs_router
from routers.venues import router as venues_router
from routers.clubs import router as clubs_router
from routers.teams import router as teams_router
from routers.tournaments import router as tournaments_router
from routers.seasons import router as seasons_router
from routers.rounds import router as rounds_router
from routers.matchdays import router as matchdays_router
from routers.users import router as users_router
from routers.matches import router as matches_router
from routers.roster import router as roster_router
from routers.scores import router as scores_router
from routers.penalties import router as penalties_router
from routers.messages import router as messages_router
from fastapi.middleware.cors import CORSMiddleware
import certifi

#from decouple import config
#DB_URL = config('DB_URL', cast=str)
#DB_NAME = config('DB_NAME', cast=str)

DB_URL = os.environ["DB_URL"]
DB_NAME = os.environ["DB_NAME"]

origins = ["*"]

app = FastAPI()
app.add_middleware(
  CORSMiddleware,
  allow_origins=origins,
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)


@app.on_event("startup")
async def startup_db_client():
  app.mongodb_client = AsyncIOMotorClient(DB_URL, tlsCAFile=certifi.where())
  app.mongodb = app.mongodb_client[DB_NAME]


@app.on_event("shutdown")
async def shutdown_db_client():
  app.mongodb_client.close()

app.include_router(root_router, prefix="", tags=["root"])
app.include_router(configs_router, prefix="/configs", tags=["configs"])
app.include_router(venues_router, prefix="/venues", tags=["venues"])
app.include_router(clubs_router, prefix="/clubs", tags=["clubs"])
app.include_router(teams_router, prefix="/clubs/{club_alias}/teams", tags=["teams"])
app.include_router(tournaments_router,
                   prefix="/tournaments",
                   tags=["tournaments"])
app.include_router(seasons_router,
                   prefix="/tournaments/{tournament_alias}/seasons",
                   tags=["seasons"])
app.include_router(rounds_router, prefix="/tournaments/{tournament_alias}/seasons/{season_alias}/rounds", tags=["rounds"])
app.include_router(matchdays_router, prefix="/tournaments/{tournament_alias}/seasons/{season_alias}/rounds/{round_alias}/matchdays", tags=["matchdays"])
app.include_router(matches_router, prefix="/matches", tags=["matches"])
app.include_router(roster_router, prefix="/matches/{match_id}/{team_flag}/roster", tags=["roster"])
app.include_router(scores_router, prefix="/matches/{match_id}/{team_flag}/scores", tags=["scores"])
app.include_router(penalties_router, prefix="/matches/{match_id}/{team_flag}/penalties", tags=["penalties"])
app.include_router(users_router, prefix="/users", tags=["users"])
app.include_router(messages_router, prefix="/messages", tags=["messages"])

#if __name__ == "__main__":
#    uvicorn.run("main:app", reload=True)
