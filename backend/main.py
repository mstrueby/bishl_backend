#!/usr/bin/env python

from decouple import config
from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient
import uvicorn
from routers.venues import router as venues_router
from routers.clubs import router as clubs_router
from fastapi.middleware.cors import CORSMiddleware
import certifi


DB_URL = config('DB_URL', cast=str)
DB_NAME = config('DB_NAME', cast=str)
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

app.include_router(venues_router, prefix="/venues", tags=["venues"])
app.include_router(clubs_router, prefix="/clubs", tags=["clubs"])

if __name__ == "__main__":
    uvicorn.run("main:app", reload=True)
