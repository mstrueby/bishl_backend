import os
from typing import List, Optional
from fastapi import APIRouter, Request, Body, status, HTTPException, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from models.tournaments import TournamentBase, TournamentDB, TournamentUpdate
from authentication import AuthHandler

router = APIRouter()
auth = AuthHandler()


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
  results = [
    TournamentDB(**raw_tournament) async for raw_tournament in full_query
  ]
  return results


# get tournament by ALIAS
@router.get("/{alias}", response_description="Get a single tournament")
async def get_tournament(alias: str, request: Request):
  if (tournament := await
      request.app.mongodb["tournaments"].find_one({"alias":
                                                   alias})) is not None:
    return TournamentDB(**tournament)
  raise HTTPException(status_code=404,
                      detail=f"Tournament with alias {alias} not found")


# create new tournament
@router.post("/", response_description="Add new tournament")
async def create_tournament(
    request: Request,
    tournament: TournamentBase = Body(...),
    userId=Depends(auth.auth_wrapper),
):
  tournament = jsonable_encoder(tournament)
  new_tournament = await request.app.mongodb["tournaments"].insert_one(
    tournament)
  created_tournament = await request.app.mongodb["tournaments"].find_one(
    {"_id": new_tournament.inserted_id})
  return JSONResponse(status_code=status.HTTP_201_CREATED,
                      content=created_tournament)


# update tournament
@router.patch("/{alias}", response_description="Update tournament")
async def update_tournament(request: Request,
                            alias: str,
                            tournament: TournamentUpdate = Body(...),
                            user_id=Depends(auth.auth_wrapper)):
  await request.app.mongodb['tournaments'].update_one(
    {"alias": alias}, {"$set": tournament.dict(exclude_unset=True)})
  if (tournament := await
      request.app.mongodb['tournaments'].find_one({"alias":
                                                   alias})) is not None:
    return TournamentDB(**tournament)
  raise HTTPException(status_code=404,
                      detail=f"Tournament with alias {alias} not found")


# delete tournament
@router.delete("/{alias}", response_description="Delete tournament")
async def delete_tournament(request: Request,
                            alias: str,
                            user_id=Depends(auth.auth_wrapper)):
  result = await request.app.mongodb['tournaments'].delete_one(
    {"alias": alias})
  if result.deleted_count == 1:
    return Response(status_code=status.HTTP_204_NO_CONTENT)
  raise HTTPException(status_code=404,
                      detail=f"Tournament with alias {alias} not found")
