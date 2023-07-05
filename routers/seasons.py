from typing import List, Optional
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
  page: int = 1,
  alias: Optional[str] = None,
  year: Optional[int] = None,
) -> List[SeasonDB]:

  RESULTS_PER_PAGE = 50
  skip = (page - 1) * RESULTS_PER_PAGE
  # query = {"active":active}
  query = {}
  if alias:
    query["alias"] = alias
  if year:
    query["year"] = year
  full_query = request.app.mongodb["seasons"].find(query).sort(
    "year", -1).skip(skip).limit(RESULTS_PER_PAGE)
  results = [SeasonDB(**raw_season) async for raw_season in full_query]
  return results


# get season by ID
@router.get("/{id}", response_description="Get a single season")
async def get_season(id: str, request: Request):
  if (season := await
      request.app.mongodb["seasons"].find_one({"_id": id})) is not None:
    return SeasonDB(**season)
  raise HTTPException(status_code=404, detail=f"Season with {id} not found")


# create new season
@router.post("/", response_description="Add new season")
async def create_season(request: Request, season: SeasonBase = Body(...)):
  season = jsonable_encoder(season)
  new_season = await request.app.mongodb["seasons"].insert_one(season)
  created_season = await request.app.mongodb["seasons"].find_one(
    {"_id": new_season.inserted_id})
  return JSONResponse(status_code=status.HTTP_201_CREATED,
                      content=created_season)


# update season
@router.patch("/{id}", response_description="Update season")
async def update_season(request: Request,
                        id: str,
                        season: SeasonUpdate = Body(...)):
  await request.app.mongodb['seasons'].update_one(
    {"_id": id}, {"$set": season.dict(exclude_unset=True)})
  if (season := await
      request.app.mongodb['seasons'].find_one({"_id": id})) is not None:
    return SeasonDB(**season)
  raise HTTPException(status_code=404, detail=f"Season with {id} not found")


# delete season
@router.delete("/{id}", response_description="Delete season")
async def delete_season(request: Request, id: str):
  result = await request.app.mongodb['seasons'].delete_one({"_id": id})
  if result.deleted_count == 1:
    return JSONResponse(status_code=status.HTTP_204_NO_CONTENT, content=None)
  raise HTTPException(status_code=404, detail=f"Season with {id} not found")
