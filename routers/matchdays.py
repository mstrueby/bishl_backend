# filename: routers/matchdays.py
from typing import List
from fastapi import APIRouter, Request, Body, status, HTTPException, Depends, Path
from fastapi.responses import JSONResponse, Response
from models.tournaments import MatchdayBase, MatchdayDB, MatchdayUpdate
from authentication import AuthHandler
from fastapi.encoders import jsonable_encoder
from utils import parse_datetime, my_jsonable_encoder

router = APIRouter()
auth = AuthHandler()


# get all matchdays of a round
@router.get('/', response_description="List all matchdays for a round")
async def get_matchdays_for_round(
  request: Request,
  tournament_alias: str = Path(
    ..., description="The alias of the tournament to list the matchdays for"),
  season_alias: str = Path(..., description="The alias of the season to get"),
  round_alias: str = Path(..., description="The alias of the round to get"),
) -> List[MatchdayDB]:
  exclusion_projection = {}  # display all matches
  if (tournament := await request.app.mongodb['tournaments'].find_one(
    {"alias": tournament_alias}, exclusion_projection)) is not None:
    for season in tournament.get("seasons", []):
      if season.get("alias") == season_alias:
        for round in season.get("rounds", []):
          if round.get("alias") == round_alias:
            matchdays = [
              MatchdayDB(**matchday)
              for matchday in round.get("matchdays", [])
            ]
            return JSONResponse(status_code=status.HTTP_200_OK,
                                content=jsonable_encoder(matchdays))
        raise HTTPException(
          status_code=404,
          detail=
          f"Round with name {round_alias} not found in season {season_alias} of tournament {tournament_alias}"
        )
    raise HTTPException(
      status_code=404,
      detail=f"Season {season_alias} not found in tournament {tournament_alias}"
    )
  raise HTTPException(
    status_code=404,
    detail=f"Tournament with alias {tournament_alias} not found")


# get one matchday of a round
@router.get('/{matchday_alias}',
            response_description="Get one matchday of a round")
async def get_matchday(
  request: Request,
  tournament_alias: str = Path(
    ..., description="The ALIAS of the tournament to list the matchdays for"),
  season_alias: str = Path(..., description="The alias of the season to get"),
  round_alias: str = Path(..., description="The alias of the round to get"),
  matchday_alias: str = Path(...,
                             description="The alias of the matchday to get"),
) -> MatchdayDB:
  exclusion_projection = {}
  if (tournament := await request.app.mongodb['tournaments'].find_one(
    {"alias": tournament_alias}, exclusion_projection)) is not None:
    for season in tournament.get("seasons", []):
      if season.get("alias") == season_alias:
        for round in season.get("rounds", []):
          if round.get("alias") == round_alias:
            for matchday in round.get("matchdays", []):
              if matchday.get("alias") == matchday_alias:
                matchday_response = MatchdayDB(**matchday)
                return JSONResponse(
                  status_code=status.HTTP_200_OK,
                  content=jsonable_encoder(matchday_response))
            raise HTTPException(
              status_code=404,
              detail=
              f"Matchday {matchday_alias} not found in round {round_alias} of season {season_alias} of tournament {tournament_alias}"
            )


# add new matchday to a round
@router.post('/', response_description="Add a new matchday to a round")
async def add_matchday(
    request: Request,
    tournament_alias: str = Path(
      ..., description="The alias of the tournament to add the matchday to"),
    season_alias: str = Path(...,
                             description="The alias of the season to add"),
    round_alias: str = Path(..., description="The alias of the round to add"),
    matchday: MatchdayBase = Body(..., description="The matchday to add"),
    user_id: str = Depends(auth.auth_wrapper),
) -> MatchdayDB:
  print("add matchday")
  # check if tournament exists
  if (tournament := await request.app.mongodb['tournaments'].find_one(
    {"alias": tournament_alias})) is None:
    raise HTTPException(status_code=404,
                        detail=f"Tournament {tournament_alias} not found")
  # check if season exists
  if (season := next(s for s in tournament["seasons"]
                     if s.get("alias") == season_alias)) is None:
    raise HTTPException(status_code=404,
                        detail=f"Season {season_alias} not found")
  # check if round exists
  if (round := next(
      r for r in season["rounds"] if r.get("alias") == round_alias)) is None:

    raise HTTPException(status_code=404,
                        detail=f"Round {round_alias} not found")
  # check if matchday already exiists
  if any(
      md.get("alias") == matchday.alias for md in round.get("matchdays", [])):
    raise HTTPException(
      status_code=404,
      detail=
      f"Matchday {matchday.alias} already exists in round {round_alias} in seasion {season_alias} of tournament {tournament_alias}"
    )

  # add matchday to round
  try:
    matchday_data = my_jsonable_encoder(matchday)
    filter = {"alias": tournament_alias}
    new_values = {
      "$push": {
        "seasons.$[s].rounds.$[r].matchdays": matchday_data
      }
    }
    array_filters = [{"s.alias": season_alias}, {"r.alias": round_alias}]
    result = await request.app.mongodb['tournaments'].update_one(
      filter=filter,
      update=new_values,
      array_filters=array_filters,
      upsert=False)
    # get inserted matchday
    if result.modified_count == 1:
      updated_tournament = await request.app.mongodb['tournaments'].find_one(
        {
          "alias": tournament_alias,
          "seasons.alias": season_alias,
        }, {
          "_id": 0,
          "seasons.$": 1
        })
      # update_tournament has only one season of tournament
      if updated_tournament and 'seasons' in updated_tournament:
        season_data = updated_tournament['seasons'][0]
        if 'rounds' in season_data:
          round_data = season_data['rounds'][0]
          if 'matchdays' in round_data:
            matchday_data = round_data['matchdays'][-1]
            return JSONResponse(status_code=status.HTTP_201_CREATED,
                                content=jsonable_encoder(
                                  MatchdayDB(**matchday_data)))
  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))


# update matchday of a round
@router.patch('/{matchday_id}',
              response_description="Update a matchday of a round")
async def update_matchday(
    request: Request,
    matchday_id: str = Path(...,
                            description="The ID of the matchday to update"),
    tournament_alias: str = Path(
      ...,
      description="The alias of the tournament to update the matchday of"),
    season_alias: str = Path(...,
                             description="The alias of the season to update"),
    round_alias: str = Path(...,
                            description="The alias of the round to update"),
    matchday: MatchdayUpdate = Body(..., description="The matchday to update"),
    user_id: str = Depends(auth.auth_wrapper),
) -> MatchdayDB:
  print("update matchday: ", matchday)
  matchday = matchday.dict(exclude_unset=True)
  print("excluded unset: ", matchday)
  # check if tournament exists
  tournament = await request.app.mongodb['tournaments'].find_one(
    {"alias": tournament_alias})
  if tournament is None:
    raise HTTPException(status_code=404,
                        detail=f"Tournament {tournament_alias} not found")
  # check if season exists
  season_index = next((i for i, s in enumerate(tournament["seasons"])
                       if s["alias"] == season_alias), None)
  if season_index is None:
    raise HTTPException(
      status_code=404,
      detail=f"Season {season_alias} not found in tournament {tournament_alias}"
    )
  print("season_index: ", season_index)
  # check if round exists
  round_index = next(
    (i for i, r in enumerate(tournament["seasons"][season_index]["rounds"])
     if r.get("alias") == round_alias), None)
  print("round_index: ", round_index)
  if round_index is None:
    raise HTTPException(
      status_code=404,
      detail=
      f"Round {round_alias} not found in season {season_alias} of tournament {tournament_alias}"
    )
  # check if matchday exists
  round = tournament["seasons"][season_index]["rounds"][round_index]
  matchday_index = next(
    (i for i, md in enumerate(round["matchdays"]) if md["_id"] == matchday_id),
    None)
  print("matchday_index: ", matchday_index)
  if matchday_index is None:
    raise HTTPException(
      status_code=404,
      detail=
      f"Matchday {matchday_id} not found in round {round_alias} of season {season_alias} of tournament {tournament_alias}"
    )

  # update matchday
  # prepare
  update_data = {"$set": {}}
  for field in matchday:
    if field != "_id" and matchday[field] != tournament["seasons"][
        season_index]["rounds"][round_index]["matchdays"][matchday_index].get(
          field):
      update_data["$set"][
        f"seasons.{season_index}.rounds.{round_index}.matchdays.{matchday_index}.{field}"] = matchday[
          field]
  print("update_data: ", update_data)

  # update matchday
  if update_data.get("$set"):
    try:
      result = await request.app.mongodb['tournaments'].update_one(
        {
          "alias": tournament_alias,
          "seasons.alias": season_alias,
          "seasons.rounds.alias": round_alias,
          "seasons.rounds.matchdays._id": matchday_id
        }, update_data)
      if result.modified_count == 0:
        raise HTTPException(
          status_code=404,
          detail=
          f"Matchday {matchday_id} not found in round {round_alias} of season {season_alias} of tournament {tournament_alias}"
        )
    except Exception as e:
      raise HTTPException(status_code=500, detail=str(e))
  else:
    print("no update needed")

  # Fetch the updated matchday
  tournament = await request.app.mongodb['tournaments'].find_one(
    {
      "alias": tournament_alias,
      "seasons.alias": season_alias,
    }, {
      "_id": 0,
      "seasons.$": 1
    })
  if tournament and "seasons" in tournament:
    season = tournament["seasons"][0]
    round = next(
      (r for r in season.get("rounds", []) if r.get("alias") == round_alias),
      None)
    if round and "matchdays" in round:
      matchday = next((md for md in round.get("matchdays", [])
                       if str(md.get("_id")) == matchday_id), None)
      if matchday:
        return JSONResponse(status_code=status.HTTP_200_OK,
                            content=jsonable_encoder(MatchdayDB(**matchday)))
      else:
        raise HTTPException(
          status_code=404,
          detail=
          f"Fetch: Matchday {matchday_id} not found in round {round_alias} of season {season_alias} of tournament {tournament_alias}"
        )


# delete matchday of a round
@router.delete('/{matchday_alias}',
               response_description="Delete a matchday of a round")
async def delete_matchday(
    request: Request,
    tournament_alias: str = Path(
      ...,
      description="The alias of the tournament to delete the matchday of"),
    season_alias: str = Path(...,
                             description="The alias of the season to delete"),
    round_alias: str = Path(...,
                            description="The alias of the round to delete"),
    matchday_alias: str = Path(
      ..., description="The alias of the matchday to delete"),
    user_id: str = Depends(auth.auth_wrapper),
) -> None:
  result = await request.app.mongodb['tournaments'].update_one(
    {
      "alias": tournament_alias,
      "seasons.alias": season_alias,
      "seasons.rounds.alias": round_alias,
      "seasons.rounds.matchdays.alias": matchday_alias
    }, {
      "$pull": {
        "seasons.$[s].rounds.$[r].matchdays": {
          "alias": matchday_alias
        }
      }
    },
    array_filters=[{
      "s.alias": season_alias
    }, {
      "r.alias": round_alias
    }])
  if result.modified_count == 1:
    return Response(status_code=status.HTTP_204_NO_CONTENT)
  else:
    raise HTTPException(
      status_code=404,
      detail=
      f"Matchday with alias {matchday_alias} not found in round {round_alias} of season {season_alias} of tournament {tournament_alias}"
    )
