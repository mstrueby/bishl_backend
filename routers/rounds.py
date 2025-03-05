# filename: routers/rounds.py
from typing import List
from fastapi import APIRouter, Request, Body, status, HTTPException, Depends, Path
from fastapi.responses import JSONResponse, Response
from models.tournaments import RoundBase, RoundDB, RoundUpdate
from authentication import AuthHandler, TokenPayload
from fastapi.encoders import jsonable_encoder
from utils import DEBUG_LEVEL, my_jsonable_encoder

router = APIRouter()
auth = AuthHandler()


# get all rounds of a season
@router.get('/',
            response_description="List all rounds for a season",
            response_model=List[RoundDB])
async def get_rounds_for_season(
    request: Request,
    tournament_alias: str = Path(
        ..., description="The alias of the tournament to list the rounds for"),
    season_alias: str = Path(...,
                             description="The alias of the season to get"),
) -> JSONResponse:
  mongodb = request.app.state.mongodb
  exclusion_projection = {"seasons.rounds.matchdays.matches": 0}
  if (tournament := await
      mongodb['tournaments'].find_one({"alias": tournament_alias},
                                      exclusion_projection)) is not None:
    for season in tournament.get("seasons", []):
      if season.get("alias") == season_alias:
        rounds = [
            RoundDB(**round)
            for round in sorted((season.get("rounds") or []),
                                key=lambda r: r.get("sortOrder", 0))
        ]
        return JSONResponse(status_code=status.HTTP_200_OK,
                            content=jsonable_encoder(rounds))
    raise HTTPException(
        status_code=404,
        detail=
        f"Season {season_alias} not found in tournament {tournament_alias}")
  raise HTTPException(
      status_code=404,
      detail=f"Tournament with alias {tournament_alias} not found")


# get one round of a season
@router.get('/{round_alias}',
            response_description="Get one round of a season",
            response_model=RoundDB)
async def get_round(
    request: Request,
    tournament_alias: str = Path(
        ...,
        description="The alias of the tournament to list the matchdays for"),
    season_alias: str = Path(...,
                             description="The alias of the season to get"),
    round_alias: str = Path(..., description="The alias of the round to get"),
) -> JSONResponse:
  mongodb = request.app.state.mongodb
  exclusion_projection = {"seasons.rounds.matchdays.matches": 0}
  if (tournament := await
      mongodb['tournaments'].find_one({"alias": tournament_alias},
                                      exclusion_projection)) is not None:
    for season in tournament.get("seasons", []):
      if season.get("alias") == season_alias:
        for round in season.get("rounds", []):
          if round.get("alias") == round_alias:
            round_response = RoundDB(**round)
            return JSONResponse(status_code=status.HTTP_200_OK,
                                content=jsonable_encoder(round_response))
    raise HTTPException(
        status_code=404,
        detail=
        f"Round with name {round_alias} not found in season {season_alias} of tournament {tournament_alias}"
    )
  raise HTTPException(
      status_code=404,
      detail=f"Tournament with alias {tournament_alias} not found")


# add new round to a season
@router.post('/',
             response_description="Add a new round to a season",
             response_model=RoundDB)
async def add_round(
    request: Request,
    tournament_alias: str = Path(
        ..., description="The alias of the tournament to add the round to"),
    season_alias: str = Path(...,
                             description="The alias of the season to add"),
    round: RoundBase = Body(..., description="The data of the round to add"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> JSONResponse:
  mongodb = request.app.state.mongodb
  if "ADMIN" not in token_payload.roles:
    raise HTTPException(status_code=403, detail="Nicht authorisiert")
  #print("add round, data: ", round)
  # Check if the tournament exists
  if (tournament := await
      mongodb['tournaments'].find_one({"alias": tournament_alias})) is None:
    raise HTTPException(
        status_code=404,
        detail=f"Tournament with alias {tournament_alias} not found")
  # Check if the season exists
  if (season :=
      next((s for s in tournament["seasons"] if s["alias"] == season_alias),
           None)) is None:
    raise HTTPException(
        status_code=404,
        detail=
        f"Season {season_alias} not found in tournament {tournament_alias}")
  # Check if the round already exists
  if any(r.get("alias") == round.alias for r in season.get("rounds", [])):
    raise HTTPException(
        status_code=409,
        detail=
        f"Round with alias {round.alias} already exists in season {season_alias} of tournament {tournament_alias}"
    )
  # Add the round to the season
  try:
    round_data = my_jsonable_encoder(round)
    #print("round_data: ", round_data)
    result = await mongodb['tournaments'].update_one(
        {
            "alias": tournament_alias,
            "seasons.alias": season_alias
        }, {"$push": {
            "seasons.$.rounds": round_data
        }})
    # get inserted round
    if result.modified_count == 1:
      updated_tournament = await mongodb['tournaments'].find_one({
          "alias":
          tournament_alias,
          "seasons.alias":
          season_alias
      })
      # update_tournament has only one season of tournament
      if updated_tournament and 'seasons' in updated_tournament:
        season_data = next((s for s in updated_tournament["seasons"]
                            if s.get('alias') == season_alias), None)
        if season_data and 'rounds' in season_data:
          new_round = next((r for r in season_data.get('rounds', [])
                            if r['alias'] == round.alias), None)
          if new_round:
            round_response = RoundDB(**new_round)
            return JSONResponse(status_code=status.HTTP_201_CREATED,
                                content=jsonable_encoder(round_response))
        else:
          raise HTTPException(
              status_code=404,
              detail=f"Newly added round {round.alias} not found")

    raise HTTPException(
        status_code=404,
        detail=
        f"Error adding round {round.alias} to season {season_alias} of tournament {tournament_alias}"
    )

  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))


# update a round of a season
@router.patch('/{round_id}',
              response_description="Update a round of a season",
              response_model=RoundDB)
async def update_round(
    request: Request,
    round_id: str = Path(..., description="The id of the round to update"),
    tournament_alias: str = Path(
        ..., description="The alias of the tournament to update the round in"),
    season_alias: str = Path(
        ..., description="The alias of the season to update the round in"),
    round: RoundUpdate = Body(...,
                              description="The data of the round to update"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
):
  mongodb = request.app.state.mongodb
  if "ADMIN" not in token_payload.roles:
    raise HTTPException(status_code=403, detail="Nicht authorisiert")
  round_dict = round.dict(exclude_unset=True)
  print("round: ", round_dict)
  # Check if the tournament exists
  tournament = await mongodb['tournaments'].find_one(
      {"alias": tournament_alias})
  if tournament is None:
    raise HTTPException(
        status_code=404,
        detail=f"Tournament with alias {tournament_alias} not found")
  # Check if the season exists
  season_index = next((i for i, s in enumerate(tournament["seasons"])
                       if s["alias"] == season_alias), None)
  if season_index is None:
    raise HTTPException(
        status_code=404,
        detail=
        f"Season {season_alias} not found in tournament {tournament_alias}")
  print("season_index: ", season_index)
  # Find the index of the round in the season
  round_index = next(
      (i for i, r in enumerate(tournament["seasons"][season_index].get(
          "rounds", [])) if r.get("_id") == round_id), None)
  print("round_index: ", round_index)
  if round_index is None:
    raise HTTPException(
        status_code=404,
        detail=
        f"Round with id {round_id} not found in season {season_alias} of tournament {tournament_alias}"
    )

  # Get matches for this round to determine start/end dates
  matches = await mongodb["matches"].find({
      "tournament.alias": tournament_alias,
      "season.alias": season_alias,
      "round.alias": tournament["seasons"][season_index]["rounds"][round_index]["alias"]
  }).sort("startDate", 1).to_list(None)
  if matches:
      # Ignore matches where startDate is None
      start_dates = [match['startDate'] for match in matches if match['startDate'] is not None]
      if start_dates:
          round_dict["startDate"] = min(start_dates)
          round_dict["endDate"] = max(start_dates)

  # Prepare the update by excluding unchanged data
  update_data = {"$set": {}}
  for field in round_dict:
    if field != "_id" and round_dict[field] != tournament["seasons"][
        season_index]["rounds"][round_index].get(field):
      update_data["$set"][
          f"seasons.{season_index}.rounds.{round_index}.{field}"] = round_dict[
              field]
  print("update data", update_data)

  # Update the round in the season
  if update_data.get("$set"):
    print("to update: ", update_data)
    try:

      # Update the round in the tournament's season
      result = await mongodb['tournaments'].update_one(
          {
              "alias": tournament_alias,
              "seasons.alias": season_alias,
              "seasons.rounds._id": round_id
          }, update_data)
      if result.modified_count == 0:
        raise HTTPException(
            status_code=404,
            detail=
            f"Update: Round with id {round_id} not found in season {season_alias} of tournament {tournament_alias}."
        )

    except Exception as e:
      raise HTTPException(status_code=500, detail=str(e))
  else:
    print("no update needed")
    return Response(status_code=status.HTTP_304_NOT_MODIFIED)

  # Fetch the currrent round data
  updated_tournament = await mongodb['tournaments'].find_one({
      "alias":
      tournament_alias,
      "seasons.alias":
      season_alias
  })
  if updated_tournament and "seasons" in updated_tournament:
    season_data = next((s for s in updated_tournament["seasons"]
                        if s.get("alias") == season_alias), None)
    if season_data and "rounds" in season_data:
      updated_round = next((r for r in season_data.get("rounds", [])
                            if str(r.get("_id")) == round_id), None)
      if updated_round and 'matchdays' in updated_round:
        if 'matchdays' in updated_round and updated_round[
            'matchdays'] is not None:
          for matchday in updated_round['matchdays']:
            if 'matches' in matchday:
              del matchday['matches']
        round_response = RoundDB(**updated_round)
        return JSONResponse(status_code=status.HTTP_200_OK,
                            content=jsonable_encoder(round_response))
    else:
      raise HTTPException(
          status_code=404,
          detail=
          f"Fetch: Round with id {round_id} not found in season {season_alias} of tournament {tournament_alias}"
      )
  else:
    raise HTTPException(
        status_code=404,
        detail=
        f"Fetch: Season {season_alias} not found in tournament {tournament_alias}"
    )


# delete round from a season
@router.delete('/{round_alias}',
               response_description="Delete a single round from a season")
async def delete_round(
    request: Request,
    tournament_alias: str = Path(
        ...,
        description="The alias of the tournament to delete the round from"),
    season_alias: str = Path(
        ..., description="The alias of the season to delete the round from"),
    round_alias: str = Path(...,
                            description="The alias of the round to delete"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> Response:
  mongodb = request.app.state.mongodb
  if "ADMIN" not in token_payload.roles:
    raise HTTPException(status_code=403, detail="Nicht authorisiert")
  delete_result = await mongodb['tournaments'].update_one(
      {
          "alias": tournament_alias,
          "seasons.alias": season_alias
      }, {"$pull": {
          "seasons.$.rounds": {
              "alias": round_alias
          }
      }})
  if delete_result.modified_count == 1:
    return Response(status_code=status.HTTP_204_NO_CONTENT)

  raise HTTPException(
      status_code=404,
      detail=
      f"Round with alias {round_alias} not found in season {season_alias} of tournament {tournament_alias}"
  )
