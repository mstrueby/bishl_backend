# filename: routers/roster.py
from fastapi import APIRouter, Body, Depends, Path, Request

from authentication import AuthHandler, TokenPayload
from models.matches import RosterPlayer
from models.responses import StandardResponse
from services.roster_service import RosterService

router = APIRouter()
auth = AuthHandler()


# get roster of a team
@router.get(
    "",
    response_description="Get roster of a team",
    response_model=StandardResponse[list[RosterPlayer]],
)
async def get_roster(
    request: Request,
    match_id: str = Path(..., description="The match id of the roster"),
    team_flag: str = Path(..., description="The team flag (home/away) of the roster"),
) -> StandardResponse[list[RosterPlayer]]:
    mongodb = request.app.state.mongodb
    service = RosterService(mongodb)

    roster_players = await service.get_roster(match_id, team_flag)
    return StandardResponse(
        success=True,
        data=roster_players,
        message=f"Retrieved {len(roster_players)} roster players for {team_flag} team",
    )


# update roster of a team
@router.put(
    "",
    response_description="Update roster of a team",
    response_model=StandardResponse[list[RosterPlayer]],
)
async def update_roster(
    request: Request,
    match_id: str = Path(..., description="The match id of the roster"),
    team_flag: str = Path(..., description="The team flag (home/away) of the roster"),
    roster: list[RosterPlayer] = Body(..., description="The roster to be updated"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> StandardResponse[list[RosterPlayer]]:
    mongodb = request.app.state.mongodb
    service = RosterService(mongodb)

    updated_roster, was_modified = await service.update_roster(
        match_id=match_id,
        team_flag=team_flag,
        roster_data=roster,
        user_roles=token_payload.roles,
    )

    message = (
        f"Roster updated successfully for {team_flag} team"
        if was_modified
        else f"Roster unchanged for {team_flag} team (data identical)"
    )

    return StandardResponse(success=True, data=updated_roster, message=message)
