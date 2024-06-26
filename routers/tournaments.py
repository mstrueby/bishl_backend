# filename: routers/tournaments.py
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
async def get_tournaments(request: Request, ) -> List[TournamentDB]:
  exclusion_projection = {"seasons.rounds": 0}
  query = {}
  full_query = request.app.mongodb["tournaments"].find(
    query, projection=exclusion_projection).sort("name", 1)
  if (tournaments :=
      [TournamentDB(**tournament)
       async for tournament in full_query]) is not None:
    return JSONResponse(status_code=status.HTTP_200_OK,
                        content=jsonable_encoder(tournaments))
  raise HTTPException(status_code=404, detail="No tournaments found")


# get one tournament by Alias
@router.get("/{tournament_alias}",
            response_description="Get a single tournament")
async def get_tournament(
  request: Request,
  tournament_alias: str,
) -> TournamentDB:
  exclusion_projection = {"seasons.rounds": 0}
  if (tournament := await request.app.mongodb["tournaments"].find_one(
    {"alias": tournament_alias}, exclusion_projection)) is not None:
    return TournamentDB(**tournament)
  raise HTTPException(
    status_code=404,
    detail=f"Tournament with alias {tournament_alias} not found")


# create new tournament
@router.post("/", response_description="Add new tournament")
async def create_tournament(
    request: Request,
    tournament: TournamentBase = Body(...),
    user_id=Depends(auth.auth_wrapper),
) -> TournamentDB:
  print("tournament: ", tournament)
  tournament = jsonable_encoder(tournament)

  # DB processing
  try:
    new_tournament = await request.app.mongodb["tournaments"].insert_one(
      tournament)
    exclusioin_projection = {"seasons.rounds": 0}
    created_tournament = await request.app.mongodb["tournaments"].find_one(
      {"_id": new_tournament.inserted_id}, exclusioin_projection)
    return JSONResponse(status_code=status.HTTP_201_CREATED,
                        content=created_tournament)
  except DuplicateKeyError:
    raise HTTPException(
      status_code=400,
      detail=f"Tournament {tournament['name']} already exists.")


# update tournament
@router.patch("/{tournament_id}", response_description="Update tournament")
async def update_tournament(
  request: Request,
  tournament_id: str,
  tournament: TournamentUpdate = Body(...),
  user_id=Depends(auth.auth_wrapper)
) -> TournamentDB:
  print("tournament pre exclude: ", tournament)
  tournament = tournament.dict(exclude_unset=True)
  tournament.pop("id", None)
  print("tournament: ", tournament)

  existing_tournament = await request.app.mongodb['tournaments'].find_one(
    {"_id": tournament_id})
  if existing_tournament is None:
    raise HTTPException(status_code=404,
                        detail=f"Tournament with id {tournament_id} not found")
  # Exclude unchanged data
  tournament_to_update = {
    k: v
    for k, v in tournament.items() if v != existing_tournament.get(k)
  }
  if tournament_to_update:
    try:
      print("to update: ", tournament_to_update)
      update_result = await request.app.mongodb['tournaments'].update_one(
        {"_id": tournament_id}, {"$set": tournament_to_update})
      if update_result.modified_count == 0:
        raise HTTPException(
          status_code=404,
          detail=f"Update: Tournament with id {tournament_id} not found")
    except DuplicateKeyError:
      raise HTTPException(
        status_code=400,
        detail=f"Tournament {tournament.get('name', '')} already exists.")
    except Exception as e:
      raise HTTPException(status_code=500,
                          detail=f"An unexpected error occurred: {str(e)}")
  else:
    print("No update needed")

  exclusion_projection = {"seasons.rounds": 0}
  updated_tournament = await request.app.mongodb['tournaments'].find_one(
    {"_id": tournament_id}, exclusion_projection)
  if updated_tournament is not None:
    tournament_respomse = TournamentDB(**updated_tournament)
    return JSONResponse(status_code=status.HTTP_200_OK,
                        content=jsonable_encoder(tournament_respomse))
  else:
    raise HTTPException(
      status_code=404,
      detail=f"Fetch: Tournament with id {tournament_id} not found")


# delete tournament
@router.delete("/{tournament_alias}", response_description="Delete tournament")
async def delete_tournament(
  request: Request, tournament_alias: str,
  user_id=Depends(auth.auth_wrapper)) -> None:
  result = await request.app.mongodb['tournaments'].delete_one(
    {"alias": tournament_alias})
  if result.deleted_count == 1:
    return Response(status_code=status.HTTP_204_NO_CONTENT)
  raise HTTPException(
    status_code=404,
    detail=f"Tournament with alias {tournament_alias} not found")
