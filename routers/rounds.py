# filename: routers/rounds.py
from fastapi import APIRouter, Request, Body, status, HTTPException, Depends, Path
from fastapi.responses import JSONResponse, Response
from models.tournaments import RoundBase, RoundDB, RoundUpdate
from authentication import AuthHandler
from fastapi.encoders import jsonable_encoder

router = APIRouter()
auth = AuthHandler()


# get all rounds of a season
@router.get('/', response_description="List all rounds for a season")
async def get_rounds_for_season(
    request: Request,
    tournament_alias: str = Path(
      ..., description="The alias of the tournament to list the rounds for"),
    season_year: int = Path(..., description="The year of the season to get"),
):
  exclusion_projection = {"seasons.rounds.matchdays.matches": 0}
  if (tournament := await request.app.mongodb['tournaments'].find_one(
    {"alias": tournament_alias}, exclusion_projection)) is not None:
    for season in tournament.get("seasons", []):
      if season.get("year") == season_year:
        rounds = [RoundDB(**round) for round in (season.get("rounds") or [])]
        return rounds
    raise HTTPException(
      status_code=404,
      detail=f"Season {season_year} not found in tournament {tournament_alias}"
    )
  raise HTTPException(
    status_code=404,
    detail=f"Tournament with alias {tournament_alias} not found")


# get one round of a season
@router.get('/{round_alias}', response_description="Get one round of a season")
async def get_round(
    request: Request,
    tournament_alias: str = Path(
      ...,
      description="The alias of the tournament to list the matchdays for"),
    season_year: int = Path(..., description="The year of the season to get"),
    round_alias: str = Path(..., description="The alias of the round to get"),
):
  exclusion_projection = {"seasons.rounds.matchdays.matches": 0}
  if (tournament := await request.app.mongodb['tournaments'].find_one(
    {"alias": tournament_alias}, exclusion_projection)) is not None:
    for season in tournament.get("seasons", []):
      if season.get("year") == season_year:
        for round in season.get("rounds", []):
          if round.get("alias") == round_alias:
            return RoundDB(**round)
        raise HTTPException(
          status_code=404,
          detail=
          f"Round with name {round_alias} not found in season {season_year} of tournament {tournament_alias}"
        )


# add new round to a season
@router.post('/', response_description="Add a new round to a season")
async def add_round(
    request: Request,
    tournament_alias: str = Path(
      ..., description="The alias of the tournament to add the round to"),
    season_year: int = Path(..., description="The year of the season to add"),
    round: RoundBase = Body(..., description="The data of the round to add"),
    user_id: str = Depends(auth.auth_wrapper),
):
  print("add round")
  # Check if the tournament exists
  if (tournament := await request.app.mongodb['tournaments'].find_one(
    {"alias": tournament_alias})) is None:
    raise HTTPException(
      status_code=404,
      detail=f"Tournament with alias {tournament_alias} not found")
  # Check if the season exists
  if (season := next(
    (s for s in tournament["seasons"] if s["year"] == season_year),
      None)) is None:
    raise HTTPException(
      status_code=404,
      detail=f"Season {season_year} not found in tournament {tournament_alias}"
    )
  # Check if the round already exists
  if any(r.get("alias") == round.alias for r in season.get("rounds", [])):
    raise HTTPException(
      status_code=409,
      detail=
      f"Round with alias {round.alias} already exists in season {season_year} of tournament {tournament_alias}"
    )
  # Add the round to the season
  round_json = jsonable_encoder(round)
  await request.app.mongodb['tournaments'].update_one(
    {
      "alias": tournament_alias,
      "seasons.year": season_year
    }, {"$push": {
      "seasons.$.rounds": round_json
    }})
  round_response = RoundDB(**round_json)
  return JSONResponse(status_code=status.HTTP_201_CREATED,
                      content=jsonable_encoder(round_response))


# update a round of a season
@router.patch('/{round_id}', response_description="Update a round of a season")
async def update_round(
    request: Request,
    round_id: str = Path(..., description="The id of the round to update"),
    tournament_alias: str = Path(
      ..., description="The alias of the tournament to update the round in"),
    season_year: int = Path(
      ..., description="The year of the season to update the round in"),
    round: RoundUpdate = Body(...,
                              description="The data of the round to update"),
    user_id: str = Depends(auth.auth_wrapper),
):
  print("update round: ", round)
  round = round.dict(exclude_unset=True)
  print("excluded unset: ", round)
  # Check if the tournament exists
  if (tournament := await request.app.mongodb['tournaments'].find_one(
    {"alias": tournament_alias})) is None:
    raise HTTPException(
      status_code=404,
      detail=f"Tournament with alias {tournament_alias} not found")
  print("tournament: ", tournament)
  # Check if the season exists
  if (season := next(
    (s for s in tournament["seasons"] if s["year"] == season_year),
      None)) is None:
    raise HTTPException(
      status_code=404,
      detail=f"Season {season_year} not found in tournament {tournament_alias}"
    )
  print("season: ", season)
  # Find the index of the round in the season
  round_index = next((i for i, r in enumerate(season.get("rounds", []))
                      if r.get("_id") == round_id), None)
  print("round_index: ", round_index)
  if round_index is None:
    raise HTTPException(
      status_code=404,
      detail=
      f"Round with id {round_id} not found in season {season_year} of tournament {tournament_alias}"
    )
  # Prepare the update by excluding unchanged data
  #round_json = jsonable_encoder(round)
  update_data = {"$set": {}}
  for field in round:
    if field != "_id" and round[field] != season.get(
        "rounds")[round_index].get(field):
      update_data["$set"][
        f"seasons.{season_year}.rounds.{round_index}.{field}"] = round[field]
  print("update data", update_data)

  # Update the round in the season
  if update_data.get("$set"):
    # Update the round in the tournament's season
    update_result = await request.app.mongodb['tournaments'].update_one(
      {
        "alias": tournament_alias,
        "seasons.year": season_year,
        "seasons.rounds._id": round_id
      }, update_data)
    if update_result.modified_count == 1:
      # Fetch the updated round data
      tournament = await request.app.mongodb['tournaments'].find_one(
        {
          "alias": tournament_alias,
          "seasons.year": season_year
        }, {
          "_id": 0,
          "seasons.$": 1
        })
      updated_round = None
      if tournament and "seasons" in tournament:
        season = tournament["seasons"][0]
        updated_round = next(
          (r
           for r in season.get("rounds", []) if str(r.get("_id")) == round_id),
          None)

      if updated_round:
        # Format the response using the RoundDB model, excluding matches data
        updated_round["_id"] = str(updated_round["_id"])
        round_response = jsonable_encoder(RoundDB(**updated_round).dict(exclude={'matches'}))
        return JSONResponse(status_code=status.HTTP_200_OK,
                            content=round_response)
      else:
        raise HTTPException(
          status_code=404,
          detail=
          f"Round with id {round_id} not found in season {season_year} of tournament {tournament_alias}"
        )
  else:
    print("no update needed")
    # return round without matches
    #return JSONResponse(status_code=status.HTTP_200_OK,
    #                    content=RoundDB(**season.get(
    #                      "rounds")[round_index]).dict(exclude={'matches'}))
    


# delete round from a season
@router.delete('/{round_id}',
               response_description="Delete a single round from a season")
async def delete_round(
    request: Request,
    tournament_alias: str = Path(
      ..., description="The alias of the tournament to delete the round from"),
    season_year: int = Path(
      ..., description="The year of the season to delete the round from"),
    round_id: str = Path(..., description="The id of the round to delete"),
    user_id: str = Depends(auth.auth_wrapper),
):
  print("delete round")
  delete_result = await request.app.mongodb['tournaments'].update_one(
    {
      "alias": tournament_alias,
      "seasons.year": season_year
    }, {"$pull": {
      "seasons.$.rounds": {
        "_id": round_id
      }
    }})

  print("delete result:", delete_result)

  if delete_result.modified_count == 1:
    return Response(status_code=status.HTTP_204_NO_CONTENT)

  raise HTTPException(
    status_code=404,
    detail=
    f"Round with id {round_id} not found in season {season_year} of tournament {tournament_alias}"
  )
