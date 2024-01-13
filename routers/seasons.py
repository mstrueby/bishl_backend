# filename: routers/seasons.py
from fastapi import APIRouter, Request, Body, status, HTTPException, Depends, Path
from models.tournaments import Seasons
from authentication import AuthHandler
from fastapi.encoders import jsonable_encoder

router = APIRouter()
auth = AuthHandler()


# get all seasons of a tournament
@router.get('/', response_description="List all seasons for a tournament")
async def get_seasons_for_tournament(
  request: Request,
  tournament_alias: str = Path(
    ..., description="The ALIAS of the tournament to list the seasons for"),
):
  exclusion_projection = {"seasons.rounds.matchdays": 0}
  if (tournament := await
      request.app.mongodb['tournaments'].find_one({"alias": tournament_alias}, exclusion_projection)) is not None:
    return tournament.get("seasons", [])
  raise HTTPException(
    status_code=404,
    detail=f"Tournament with alias {tournament_alias} not found")


# get one season of a tournament
@router.get('/{season_year}', response_description="Get a single season")
async def get_season(
  request: Request,
  tournament_alias: str = Path(
    ..., description="The ALIAS of the tournament to list the seasons for"),
  season_year: int = Path(..., description="The year of the season to get"),
):
  exclusion_projection = {"seasons.rounds.matchdays": 0}
  if (tournament := await
      request.app.mongodb['tournaments'].find_one({"alias": tournament_alias}, exclusion_projection)) is not None:
    for season in tournament.get("seasons", []):
      if season.get("year") == season_year:
        return season
    raise HTTPException(
      status_code=404,
      detail=f"Season with year {season_year} not found in tournament {tournament_alias}")
                                                  

# add new season to tournament
@router.post('/', response_description="Add new season to tournament")
async def add_season(
    request: Request,
    tournament_alias: str = Path(
      ..., description="The ALIAS of the tournament to add a season to"),
    season: Seasons = Body(..., description="Season data"),
    user_id: str = Depends(auth.auth_wrapper),
):
  season = jsonable_encoder(season)
  tournament = await request.app.mongodb['tournaments'].find_one(
    {"alias": tournament_alias})

  if not tournament:
    raise HTTPException(status_code=404, detail="Tournament not found")

  # Check for existing season with the same year as the one to add
  existing_seasons = tournament.get('seasons', [])
  if any(existing_season['year'] == season['year']
         for existing_season in existing_seasons):
    raise HTTPException(
      status_code=409,
      detail=
      f"Season with year {season['year']} already exists in this tournament.")

  # Here you'd append the new season data to the tournament's seasons array
  updated_tournament = await request.app.mongodb['tournaments'].update_one(
    {"alias": tournament_alias}, {"$push": {
      "seasons": season
    }})
  if not updated_tournament.acknowledged:
    raise HTTPException(status_code=500, detail="Season could not be added")

  # Return the updated tournament
  return await request.app.mongodb['tournaments'].find_one(
    {"alias": tournament_alias})


# update season in tournament
@router.patch('/{season_year}', response_description="Update season in tournament")
async def update_season(
    request: Request,
    tournament_alias: str = Path(
      ..., description="The ALIAS of the tournament to update the season in"),
    season_year: int = Path(..., description="The year of the season to get"),
    season: Seasons = Body(..., description="Season data"),
    user_id: str = Depends(auth.auth_wrapper),
):
  season = jsonable_encoder(season)
  tournament = await request.app.mongodb['tournaments'].find_one(
    {"alias": tournament_alias})
  if not tournament:
    raise HTTPException(status_code=404, detail="Tournament not found")
