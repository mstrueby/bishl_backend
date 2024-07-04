# filename: routers/seasons.py
from typing import List
from fastapi import APIRouter, Request, Body, status, HTTPException, Depends, Path
from fastapi.responses import Response, JSONResponse
from models.tournaments import SeasonBase, SeasonDB, SeasonUpdate
from authentication import AuthHandler, TokenPayload
from fastapi.encoders import jsonable_encoder

router = APIRouter()
auth = AuthHandler()


# get all seasons of a tournament
@router.get('/', response_description="List all seasons for a tournament")
async def get_seasons_for_tournament(
  request: Request,
  tournament_alias: str = Path(
    ..., description="The alias of the tournament to list the seasons for"),
) -> List[SeasonDB]:
  exclusion_projection = {"seasons.rounds.matchdays": 0}
  if (tournament := await request.app.mongodb['tournaments'].find_one(
    {"alias": tournament_alias}, exclusion_projection)) is not None:
    seasons = [
      SeasonDB(**season) for season in (tournament.get("seasons") or [])
    ]
    return JSONResponse(status_code=status.HTTP_200_OK,
                        content=jsonable_encoder(seasons))
  raise HTTPException(
    status_code=404,
    detail=f"Tournament with alias {tournament_alias} not found")


# get one season of a tournament
@router.get('/{season_alias}', response_description="Get a single season")
async def get_season(
  request: Request,
  tournament_alias: str = Path(
    ..., description="The alias of the tournament to list the seasons for"),
  season_alias: str = Path(..., description="The alias of the season to get"),
) -> SeasonDB:
  exclusion_projection = {"seasons.rounds.matchdays": 0}
  if (tournament := await request.app.mongodb['tournaments'].find_one(
    {"alias": tournament_alias}, exclusion_projection)) is not None:
    for season in tournament.get("seasons", []):
      if season.get("alias") == season_alias:
        season_response = SeasonDB(**season)
        return JSONResponse(status_code=status.HTTP_200_OK,
                            content=jsonable_encoder(season_response))
    raise HTTPException(
      status_code=404,
      detail=f"Season {season_alias} not found in tournament {tournament_alias}"
    )


# add new season to tournament
@router.post('/', response_description="Add new season to tournament")
async def create_season(
    request: Request,
    tournament_alias: str = Path(
      ..., description="The alias of the tournament to add a season to"),
    season: SeasonBase = Body(..., description="Season data"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> SeasonDB:
  if token_payload.roles not in [["ADMIN"]]:
    raise HTTPException(status_code=403, detail="Not authorized")
  print("add season")
  # Check if the tournament exists
  if (tournament := await request.app.mongodb['tournaments'].find_one(
    {"alias": tournament_alias})) is None:
    raise HTTPException(
      status_code=404,
      detail=f"Tournament with alias {tournament_alias} not found")
  # Check for existing season with the same alias as the one to add
  if any(
      s.get("alias") == season.alias for s in tournament.get("seasons", [])):
    raise HTTPException(
      status_code=409,
      detail=
      f"Season {season.alias} already exists in tournament {tournament_alias}")

  # Here you'd append the new season data to the tournament's seasons array
  try:
    season_data = jsonable_encoder(season)
    result = await request.app.mongodb['tournaments'].update_one(
      {"alias": tournament_alias}, {"$push": {
        "seasons": season_data
      }})
    if result.modified_count == 1:
      # get inserted season
      updated_tournament = await request.app.mongodb['tournaments'].find_one(
        {
          "alias": tournament_alias,
          "seasons.alias": season.alias
        }, {
          "_id": 0,
          "seasons.$": 1
        })
      # updated_tournament has only one season
      if updated_tournament and "seasons" in updated_tournament:
        season = updated_tournament["seasons"][0]
        season_response = SeasonDB(**season)
        return JSONResponse(status_code=status.HTTP_201_CREATED,
                            content=jsonable_encoder(season_response))
      else:
        raise HTTPException(
          status_code=404,
          detail=
          f"Season {season.alias} not found in tournament {tournament_alias}")
    else:
      raise HTTPException(
        status_code=404,
        detail=
        f"Season {season.alias} or tournament {tournament_alias} not found")

  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))


# update season in tournament
@router.patch('/{season_id}',
              response_description="Update a season in tournament")
async def update_season(
    request: Request,
    season_id: str,
    tournament_alias: str = Path(
      ..., description="The ALIAS of the tournament to update the season in"),
    season: SeasonUpdate = Body(..., description="Season data to update"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> SeasonDB:
  if token_payload.roles not in [["ADMIN"]]:
    raise HTTPException(status_code=403, detail="Not authorized")
  print("input season: ", season)
  # exclude unset
  season = season.dict(exclude_unset=True)
  print("exclude unset: ", season)

  # Find the tournament by alias
  tournament = await request.app.mongodb['tournaments'].find_one(
    {"alias": tournament_alias})
  if not tournament:
    raise HTTPException(
      status_code=404,
      detail=f"Tournament with alias {tournament_alias} not found")

  # Find the index of the season to update
  season_index = next((index for (index, d) in enumerate(tournament["seasons"])
                       if d["_id"] == season_id), None)
  if season_index is None:
    raise HTTPException(
      status_code=404,
      detail=
      f"Season with id {season_id} not found in tournament {tournament_alias}")

  # Encode season data for MongoDB
  season = jsonable_encoder(season)
  #print("encoded season: ", season)

  # Prepare the update by excluding unchanged data
  update_data = {"$set": {}}
  for field in season:
    if field != "_id" and season[field] != tournament["seasons"][
        season_index].get(field):
      update_data["$set"][f"seasons.{season_index}.{field}"] = season[field]
  print("updated data: ", update_data)

  # Proceed with the update only if there are changes
  if update_data["$set"]:
    print("do update")
    # Update season in tournament
    try:
      result = await request.app.mongodb['tournaments'].update_one(
        {
          "_id": tournament["_id"],
          f"seasons.{season_index}._id": season_id
        }, update_data)
      if result.modified_count == 0:
        raise HTTPException(
          status_code=404,
          detail=
          f"Update: Season with id {season_id} not found in tournament {tournament_alias}"
        )
    except Exception as e:
      raise HTTPException(status_code=500, detail=str(e))

  else:
    print("no update")

  # Fetch the current season data
  tournament = await request.app.mongodb['tournaments'].find_one(
    {"alias": tournament_alias}, {
      '_id': 0,
      "seasons": {
        "$elemMatch": {
          "_id": season_id
        }
      }
    })
  if tournament and "seasons" in tournament:
    season = tournament["seasons"][0]
    if "rounds" in season and season["rounds"] is not None:
      for round in season["rounds"]:
        if "matchdays" in round:
          del round["matchdays"]
    season_response = SeasonDB(**season)
    return JSONResponse(status_code=status.HTTP_200_OK,
                        content=jsonable_encoder(season_response))
  else:
    raise HTTPException(
      status_code=404,
      detail=
      f"Fetch: Season with id {season_id} not found in tournament {tournament_alias}"
    )


# delete season from tournament
@router.delete('/{season_alias}',
               response_description="Delete a single season from a tournament")
async def delete_season(
    request: Request,
    tournament_alias: str = Path(
      ...,
      description="The alias of the tournament to delete the season from"),
    season_alias: str = Path(...,
                             description="The alias of the season to delete"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> None:
  if token_payload.roles not in [["ADMIN"]]:
    raise HTTPException(status_code=403, detail="Not authorized")
  delete_result = await request.app.mongodb['tournaments'].update_one(
    {"alias": tournament_alias},
    {"$pull": {
      "seasons": {
        "alias": season_alias
      }
    }})
  if delete_result.modified_count == 1:
    return Response(status_code=status.HTTP_204_NO_CONTENT)

  raise HTTPException(
    status_code=404,
    detail=
    f"Season with alias {season_alias} not found in tournament {tournament_alias}"
  )
