import os
from typing import List, Optional
from fastapi import APIRouter, Request, Body, status, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from models.tournaments import TournamentBase, TournamentDB, TournamentUpdate

router = APIRouter()

# list all tournaments
@router.get("/", response_description="List all tournaments")
async def list_tournaments(
  request: Request,
  # active: bool=True,
  page: int = 1,
  alias: Optional[str] = None,
  year: Optional[int] = None,
) -> List[TournamentDB]:

  RESULTS_PER_PAGE = int(os.environ['RESULTS_PER_PAGE'])
  skip = (page - 1) * RESULTS_PER_PAGE
  # query = {"active":active}
  query = {}
  if alias:
    query["alias"] = alias
  if year:
    query["year"] = year
  full_query = request.app.mongodb["tournaments"].find(query).sort(
    "year", -1).skip(skip).limit(RESULTS_PER_PAGE)
  results = [TournamentDB(**raw_tournament) async for raw_tournament in full_query]
  return results


# get tournament by ID
@router.get("/{id}", response_description="Get a single tournament")
async def get_tournament(id: str, request: Request):
  if (tournament := await
      request.app.mongodb["tournaments"].find_one({"_id": id})) is not None:
    return TournamentDB(**tournament)
  raise HTTPException(status_code=404, detail=f"Tournament with {id} not found")


# create new tournament
@router.post("/", response_description="Add new tournament")
async def create_tournament(request: Request, tournament: TournamentBase = Body(...)):
  tournament = jsonable_encoder(tournament)
  new_tournament = await request.app.mongodb["tournaments"].insert_one(tournament)
  created_tournament = await request.app.mongodb["tournaments"].find_one(
    {"_id": new_tournament.inserted_id})
  return JSONResponse(status_code=status.HTTP_201_CREATED,
                      content=created_tournament)


# update tournament
@router.patch("/{id}", response_description="Update tournament")
async def update_tournament(request: Request,
                        id: str,
                        tournament: TournamentUpdate = Body(...)):
  await request.app.mongodb['tournaments'].update_one(
    {"_id": id}, {"$set": tournament.dict(exclude_unset=True)})
  if (tournament := await
      request.app.mongodb['tournaments'].find_one({"_id": id})) is not None:
    return TournamentDB(**tournament)
  raise HTTPException(status_code=404, detail=f"Tournament with {id} not found")


# delete tournament
@router.delete("/{id}", response_description="Delete tournament")
async def delete_tournament(request: Request, id: str):
  result = await request.app.mongodb['tournaments'].delete_one({"_id": id})
  if result.deleted_count == 1:
    return JSONResponse(status_code=status.HTTP_204_NO_CONTENT, content=None)
  raise HTTPException(status_code=404, detail=f"Tournament with {id} not found")
