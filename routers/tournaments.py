import os
from typing import List
from fastapi import APIRouter, Request, Body, status, HTTPException, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from models.tournaments import TournamentBase, TournamentDB, TournamentUpdate
from authentication import AuthHandler
from pymongo.errors import DuplicateKeyError

router = APIRouter()
auth = AuthHandler()


# get all tournaments
@router.get("/", response_description="List all tournaments")
async def list_tournaments(
  request: Request,
  # active: bool=True,
  page: int = 1,
) -> List[TournamentDB]:
  RESULTS_PER_PAGE = int(os.environ['RESULTS_PER_PAGE'])
  skip = (page - 1) * RESULTS_PER_PAGE
  # query = {"active":active}
  query = {}
  full_query = request.app.mongodb["tournaments"].find(query).sort(
    "name", 1).skip(skip).limit(RESULTS_PER_PAGE)
  results = [
    TournamentDB(**raw_tournament) async for raw_tournament in full_query
  ]
  return results


# get one tournament by Alias
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

  # DB processing
  try:
    new_tournament = await request.app.mongodb["tournaments"].insert_one(
      tournament)
    created_tournament = await request.app.mongodb["tournaments"].find_one(
      {"_id": new_tournament.inserted_id})
    return JSONResponse(status_code=status.HTTP_201_CREATED,
                        content=created_tournament)
  except DuplicateKeyError:
    raise HTTPException(
      status_code=400,
      detail=f"Tournament {tournament['name']} already exists.")


# update tournament
@router.patch("/{id}", response_description="Update tournament")
async def update_tournament(request: Request,
                            id: str,
                            tournament: TournamentUpdate = Body(...),
                            user_id=Depends(auth.auth_wrapper)):
  print("input: ", tournament)
  tournament = tournament.dict(exclude_unset=True)
  print("exclude unset: ", tournament)
  existing_tournament = await request.app.mongodb['tournaments'].find_one(
    {"_id": id})
  if existing_tournament is None:
    raise HTTPException(status_code=404,
                        detail=f"Tournament with id {id} not found")
  # Exclude unchanged data
  tournament_to_update = {
    k: v
    for k, v in tournament.items() if v != existing_tournament.get(k)
  }
  if not tournament_to_update:
    print("no update needed")
    return TournamentDB(
      **existing_tournament)  # No update needed as no values have changed
  try:
    print("to update: ", tournament_to_update)
    update_result = await request.app.mongodb['tournaments'].update_one(
      {"_id": id}, {"$set": tournament_to_update})
    if update_result.modified_count == 1:
      if (updated_tournament := await
          request.app.mongodb['tournaments'].find_one({"_id":
                                                       id})) is not None:
        return TournamentDB(**updated_tournament)
    return TournamentDB(
      **existing_tournament
    )  # No update occurred if no attributes had different values
  except DuplicateKeyError:
    raise HTTPException(
      status_code=400,
      detail=
      f"Tournament with name {tournament.get('name', '')} already exists.")
  except Exception as e:
    raise HTTPException(status_code=500,
                        detail=f"An unexpected error occurred: {str(e)}")


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
