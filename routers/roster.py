# filename: routers/roster.py
from fastapi import APIRouter, Body, Depends, Path, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from authentication import AuthHandler, TokenPayload
from models.matches import RosterPlayer
from services.roster_service import RosterService

router = APIRouter()
auth = AuthHandler()


# get roster of a team
@router.get("/", response_description="Get roster of a team", response_model=list[RosterPlayer])
async def get_roster(
    request: Request,
    match_id: str = Path(..., description="The match id of the roster"),
    team_flag: str = Path(..., description="The team flag (home/away) of the roster"),
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    service = RosterService(mongodb)

    roster_players = await service.get_roster(match_id, team_flag)
    return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(roster_players))


# update roster of a team
@router.put("/", response_description="Update roster of a team", response_model=list[RosterPlayer])
async def update_roster(
    request: Request,
    match_id: str = Path(..., description="The match id of the roster"),
    team_flag: str = Path(..., description="The team flag (home/away) of the roster"),
    roster: list[RosterPlayer] = Body(..., description="The roster to be updated"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    service = RosterService(mongodb)

    updated_roster = await service.update_roster(
        match_id=match_id,
        team_flag=team_flag,
        roster_data=roster,
        user_roles=token_payload.roles,
    )

    return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(updated_roster))