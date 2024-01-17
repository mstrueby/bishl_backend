# filename: routers/matchdays.py
from fastapi import APIRouter, Request, Body, status, HTTPException, Depends, Path
from fastapi.responses import JSONResponse, Response
from models.tournaments import MatchdayBase, MatchdayDB, MatchdayUpdate
from authentication import AuthHandler
from fastapi.encoders import jsonable_encoder

router = APIRouter()
auth = AuthHandler()


# get all matchdays of a round
@router.get('/', response_description="List all matchdays for a round")
async def get_matchdays_for_round(
    request: Request,
    tournament_alias: str = Path(
      ...,
      description="The alias of the tournament to list the matchdays for"),
    season_year: int = Path(..., description="The year of the season to get"),
    round_alias: str = Path(..., description="The alias of the round to get"),
):
  exclusion_projection = {}  # display all matches
  if (tournament := await request.app.mongodb['tournaments'].find_one(
    {"alias": tournament_alias}, exclusion_projection)) is not None:
    for season in tournament.get("seasons", []):
      if season.get("year") == season_year:
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
          f"Round with name {round_alias} not found in season {season_year} of tournament {tournament_alias}"
        )
    raise HTTPException(
      status_code=404,
      detail=
      f"Season with year {season_year} not found in tournament {tournament_alias}"
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
  season_year: int = Path(..., description="The year of the season to get"),
  round_alias: str = Path(..., description="The alias of the round to get"),
  matchday_alias: str = Path(...,
                             description="The alias of the matchday to get"),
):
  exclusion_projection = {}
  if (tournament := await request.app.mongodb['tournaments'].find_one(
    {"alias": tournament_alias}, exclusion_projection)) is not None:
    for season in tournament.get("seasons", []):
      if season.get("year") == season_year:
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
              f"Matchday {matchday_alias} not found in round {round_alias} of season {season_year} of tournament {tournament_alias}"
            )
