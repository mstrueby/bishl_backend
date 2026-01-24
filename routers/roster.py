# filename: routers/roster.py
from fastapi import APIRouter, Body, Depends, Path, Request

from authentication import AuthHandler, TokenPayload
from models.matches import Roster, RosterPlayer, RosterUpdate
from models.responses import StandardResponse
from services.roster_service import RosterService

router = APIRouter()
auth = AuthHandler()


@router.get(
    "",
    response_description="Get complete roster of a team",
    response_model=StandardResponse[Roster],
)
async def get_roster(
    request: Request,
    match_id: str = Path(..., description="The match id of the roster"),
    team_flag: str = Path(..., description="The team flag (home/away) of the roster"),
) -> StandardResponse[Roster]:
    """
    Get the complete roster object for a team.
    
    Returns all roster data including players, status, published flag,
    eligibility info, coach, and staff in a single response.
    """
    mongodb = request.app.state.mongodb
    service = RosterService(mongodb)

    roster = await service.get_roster(match_id, team_flag)
    player_count = len(roster.players)
    
    return StandardResponse(
        success=True,
        data=roster,
        message=f"Retrieved roster with {player_count} players for {team_flag} team",
    )


@router.get(
    "/players",
    response_description="Get roster players only",
    response_model=StandardResponse[list[RosterPlayer]],
)
async def get_roster_players(
    request: Request,
    match_id: str = Path(..., description="The match id of the roster"),
    team_flag: str = Path(..., description="The team flag (home/away) of the roster"),
) -> StandardResponse[list[RosterPlayer]]:
    """
    Get only the player list from a roster.
    
    Backward-compatible endpoint for clients that only need player data.
    """
    mongodb = request.app.state.mongodb
    service = RosterService(mongodb)

    players = await service.get_roster_players(match_id, team_flag)
    
    return StandardResponse(
        success=True,
        data=players,
        message=f"Retrieved {len(players)} roster players for {team_flag} team",
    )


@router.put(
    "",
    response_description="Update roster of a team",
    response_model=StandardResponse[Roster],
)
async def update_roster(
    request: Request,
    match_id: str = Path(..., description="The match id of the roster"),
    team_flag: str = Path(..., description="The team flag (home/away) of the roster"),
    roster_update: RosterUpdate = Body(..., description="The roster fields to update"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> StandardResponse[Roster]:
    """
    Atomically update the roster for a team.
    
    This single endpoint handles all roster updates:
    - Players list (with duplicate and score/penalty consistency validation)
    - Status transitions (DRAFT → SUBMITTED → APPROVED workflow)
    - Published flag
    - Coach and staff
    - Eligibility metadata (auto-updated on APPROVED status)
    
    Only provided fields are updated; omitted fields remain unchanged.
    Jersey numbers are automatically synced to scores/penalties.
    """
    mongodb = request.app.state.mongodb
    service = RosterService(mongodb)

    updated_roster, was_modified = await service.update_roster(
        match_id=match_id,
        team_flag=team_flag,
        roster_update=roster_update,
        user_roles=token_payload.roles,
        user_id=token_payload.sub,
    )

    message = (
        f"Roster updated successfully for {team_flag} team"
        if was_modified
        else f"Roster unchanged for {team_flag} team (data identical)"
    )

    return StandardResponse(success=True, data=updated_roster, message=message)
