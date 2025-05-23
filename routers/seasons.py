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
@router.get('/',
            response_description="List all seasons for a tournament",
            response_model=List[SeasonDB])
async def get_seasons_for_tournament(
    request: Request,
    tournament_alias: str = Path(
        ...,
        description="The alias of the tournament to list the seasons for"),
) -> JSONResponse:
  mongodb = request.app.state.mongodb
  exclusion_projection = {"seasons.rounds.matchdays": 0}
  if (tournament := await mongodb['tournaments'].find_one(
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
@router.get('/{season_alias}',
            response_description="Get a single season",
            response_model=SeasonDB)
async def get_season(
    request: Request,
    tournament_alias: str = Path(
        ...,
        description="The alias of the tournament to list the seasons for"),
    season_alias: str = Path(...,
                             description="The alias of the season to get"),
) -> JSONResponse:
  mongodb = request.app.state.mongodb
  exclusion_projection = {"seasons.rounds.matchdays": 0}
  if (tournament := await mongodb['tournaments'].find_one(
      {"alias": tournament_alias}, exclusion_projection)) is not None:
    for season in tournament.get("seasons", []):
      if season.get("alias") == season_alias:
        season_response = SeasonDB(**season)
        return JSONResponse(status_code=status.HTTP_200_OK,
                            content=jsonable_encoder(season_response))
    raise HTTPException(
        status_code=404,
        detail=
        f"Season {season_alias} not found in tournament {tournament_alias}")
  raise HTTPException(
      status_code=404,
      detail=f"Tournament with alias {tournament_alias} not found")


# add new season to tournament
@router.post('/', response_description="Add new season to tournament", response_model=SeasonDB)
async def create_season(
    request: Request,
    tournament_alias: str = Path(
        ..., description="The alias of the tournament to add a season to"),
    season: SeasonBase = Body(..., description="Season data"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> JSONResponse:
  mongodb = request.app.state.mongodb
  if "ADMIN" not in token_payload.roles:
    raise HTTPException(status_code=403, detail="Nicht authorisiert")
  #print("add season")
  # Check if the tournament exists
  if (tournament := await
      mongodb['tournaments'].find_one({"alias":
                                                   tournament_alias})) is None:
    raise HTTPException(
        status_code=404,
        detail=f"Tournament with alias {tournament_alias} not found")
  # Check for existing season with the same alias as the one to add
  if any(
      s.get("alias") == season.alias for s in tournament.get("seasons", [])):
    raise HTTPException(
        status_code=409,
        detail=
        f"Season {season.alias} already exists in tournament {tournament_alias}"
    )

  # Here you'd append the new season data to the tournament's seasons array
  try:
    season_data = jsonable_encoder(season)
    result = await mongodb['tournaments'].update_one(
        {"alias": tournament_alias}, {"$push": {
            "seasons": season_data
        }})
    if result.modified_count == 1:
      # get inserted season
      updated_tournament = await mongodb['tournaments'].find_one(
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
        season_response = SeasonDB(**season_data)
        return JSONResponse(status_code=status.HTTP_201_CREATED,
                            content=jsonable_encoder(season_response))
      else:
        raise HTTPException(
            status_code=404,
            detail=
            f"Season {season.alias} not found in tournament {tournament_alias}"
        )
    else:
      raise HTTPException(
          status_code=404,
          detail=
          f"Season {season.alias} or tournament {tournament_alias} not found")

  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))


# update season in tournament
@router.patch('/{season_id}',
              response_description="Update a season in tournament",
             response_model=SeasonDB)
async def update_season(
    request: Request,
    season_id: str,
    tournament_alias: str = Path(
        ...,
        description="The ALIAS of the tournament to update the season in"),
    season: SeasonUpdate = Body(..., description="Season data to update"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
):
  mongodb = request.app.state.mongodb
  if "ADMIN" not in token_payload.roles:
    raise HTTPException(status_code=403, detail="Nicht authorisiert")
  print("input season: ", season)
  # exclude unset
  season_dict = season.dict(exclude_unset=True)
  print("exclude unset: ", season_dict)

  # Find the tournament by alias
  tournament = await mongodb['tournaments'].find_one(
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
        f"Season with id {season_id} not found in tournament {tournament_alias}"
    )

  # Prepare the update by excluding unchanged data
  update_data = {"$set": {}}
  for field in season_dict:
    if field != "_id" and season_dict[field] != tournament["seasons"][
        season_index].get(field):
      update_data["$set"][f"seasons.{season_index}.{field}"] = season_dict[field]
  print("updated data: ", update_data)

  # Proceed with the update only if there are changes
  if update_data["$set"]:
    print("do update")
    # Update season in tournament
    try:
      result = await mongodb['tournaments'].update_one(
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
    return Response(status_code=status.HTTP_304_NOT_MODIFIED)

  # Fetch the current season data
  tournament = await mongodb['tournaments'].find_one(
      {"alias": tournament_alias}, {
          '_id': 0,
          "seasons": {
              "$elemMatch": {
                  "_id": season_id
              }
          }
      })
  if tournament and "seasons" in tournament:
    updated_season = tournament["seasons"][0]
    if "rounds" in updated_season and updated_season["rounds"] is not None:
      for round in updated_season["rounds"]:
        if "matchdays" in round:
          del round["matchdays"]
    season_response = SeasonDB(**updated_season)
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
) -> Response:
  mongodb = request.app.state.mongodb
  if "ADMIN" not in token_payload.roles:
    raise HTTPException(status_code=403, detail="Nicht authorisiert")
  delete_result = await mongodb['tournaments'].update_one(
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
