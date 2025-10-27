# filename: routers/rounds.py

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response

from authentication import AuthHandler, TokenPayload
from exceptions import (
  AuthorizationException,
  DatabaseOperationException,
  ResourceNotFoundException,
  ValidationException,
)
from logging_config import logger
from models.tournaments import RoundBase, RoundDB, RoundUpdate
from utils import DEBUG_LEVEL, my_jsonable_encoder

router = APIRouter()
auth = AuthHandler()


# get all rounds of a season
@router.get('/',
            response_description="List all rounds for a season",
            response_model=list[RoundDB])
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
    raise ResourceNotFoundException(
        resource_type="Season",
        resource_id=season_alias,
        details={"tournament_alias": tournament_alias})
  raise ResourceNotFoundException(
      resource_type="Tournament",
      resource_id=tournament_alias)


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
    raise ResourceNotFoundException(
        resource_type="Round",
        resource_id=round_alias,
        details={"season_alias": season_alias, "tournament_alias": tournament_alias})
  raise ResourceNotFoundException(
      resource_type="Tournament",
      resource_id=tournament_alias)


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
    raise AuthorizationException(
        message="Admin role required to add rounds",
        details={"user_roles": token_payload.roles})

  logger.info(f"Adding round to {tournament_alias}/{season_alias}", extra={
      "round_alias": round.alias,
      "tournament_alias": tournament_alias,
      "season_alias": season_alias
  })

  # Check if the tournament exists
  if (tournament := await
      mongodb['tournaments'].find_one({"alias": tournament_alias})) is None:
    raise ResourceNotFoundException(
        resource_type="Tournament",
        resource_id=tournament_alias)
  # Check if the season exists
  if (season :=
      next((s for s in tournament["seasons"] if s["alias"] == season_alias),
           None)) is None:
    raise ResourceNotFoundException(
        resource_type="Season",
        resource_id=season_alias,
        details={"tournament_alias": tournament_alias})
  # Check if the round already exists
  if any(r.get("alias") == round.alias for r in season.get("rounds", [])):
    raise ValidationException(
        field="alias",
        message=f"Round with alias '{round.alias}' already exists",
        details={"season_alias": season_alias, "tournament_alias": tournament_alias})
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

    raise DatabaseOperationException(
        operation="add_round",
        collection="tournaments",
        details={
            "round_alias": round.alias,
            "season_alias": season_alias,
            "tournament_alias": tournament_alias
        })

  except Exception as e:
    logger.error(f"Failed to add round {round.alias}", extra={
        "error": str(e),
        "season_alias": season_alias,
        "tournament_alias": tournament_alias
    })
    raise DatabaseOperationException(
        operation="insert_round",
        collection="tournaments",
        details={"error": str(e)})


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
    raise AuthorizationException(
        message="Admin role required to update rounds",
        details={"user_roles": token_payload.roles})

  round_dict = round.model_dump(exclude_unset=True)
  logger.info(f"Updating round {round_id}", extra={
      "tournament_alias": tournament_alias,
      "season_alias": season_alias,
      "fields": list(round_dict.keys())
  })

  # Check if the tournament exists
  tournament = await mongodb['tournaments'].find_one(
      {"alias": tournament_alias})
  if tournament is None:
    raise ResourceNotFoundException(
        resource_type="Tournament",
        resource_id=tournament_alias)
  # Check if the season exists
  season_index = next((i for i, s in enumerate(tournament["seasons"])
                       if s["alias"] == season_alias), None)
  if season_index is None:
    raise ResourceNotFoundException(
        resource_type="Season",
        resource_id=season_alias,
        details={"tournament_alias": tournament_alias})
  if DEBUG_LEVEL > 20:
    print("season_index: ", season_index)
  # Find the index of the round in the season
  round_index = next(
      (i for i, r in enumerate(tournament["seasons"][season_index].get(
          "rounds", [])) if r.get("_id") == round_id), None)
  if DEBUG_LEVEL > 20:
    print("round_index: ", round_index)
  if round_index is None:
    raise ResourceNotFoundException(
        resource_type="Round",
        resource_id=round_id,
        details={"season_alias": season_alias, "tournament_alias": tournament_alias})

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
  if DEBUG_LEVEL > 10:
    print("update data", update_data)

  # Update the round in the season
  if update_data.get("$set"):
    if DEBUG_LEVEL > 10:
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
        raise DatabaseOperationException(
            operation="update_round",
            collection="tournaments",
            details={
                "round_id": round_id,
                "season_alias": season_alias,
                "tournament_alias": tournament_alias,
                "reason": "No documents modified"
            })

    except DatabaseOperationException:
      raise
    except Exception as e:
      logger.error(f"Failed to update round {round_id}", extra={
          "error": str(e),
          "season_alias": season_alias,
          "tournament_alias": tournament_alias
      })
      raise DatabaseOperationException(
          operation="update_round",
          collection="tournaments",
          details={"error": str(e)})
  else:
    if DEBUG_LEVEL > 10:
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
    raise AuthorizationException(
        message="Admin role required to delete rounds",
        details={"user_roles": token_payload.roles})

  logger.info(f"Deleting round {round_alias}", extra={
      "tournament_alias": tournament_alias,
      "season_alias": season_alias
  })

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
    logger.info(f"Successfully deleted round {round_alias}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

  raise ResourceNotFoundException(
      resource_type="Round",
      resource_id=round_alias,
      details={"season_alias": season_alias, "tournament_alias": tournament_alias})
