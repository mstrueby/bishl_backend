from typing import List
from fastapi import APIRouter, Request, Body, status, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from models import SeasonBase, SeasonDB, SeasonUpdate

router = APIRouter()

# list all seasons
@router.get("/", response_description="List all seasons")
async def list_seasons(
    request: Request,
    # active: bool=True,
    page: int=1,
    ) -> List[SeasonDB]:

    RESULTS_PER_PAGE = 50
    skip = (page - 1) * RESULTS_PER_PAGE
    # query = {"active":active}
    query = {}
    full_query = request.app.mongodb["seasons"].find(query).sort("year",1).skip(skip).limit(RESULTS_PER_PAGE)
    results = [SeasonDB(**raw_season) async for raw_season in full_query]
    return results
