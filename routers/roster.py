# filename: routers/roster.py
from datetime import datetime

from fastapi import APIRouter, Body, Depends, Path, Request
from fastapi.encoders import jsonable_encoder

from authentication import AuthHandler, TokenPayload
from exceptions import AuthorizationException, ResourceNotFoundException, ValidationException
from logging_config import logger
from models.matches import LicenseStatusEnum, Roster, RosterPlayer, RosterStatusEnum, RosterUpdate
from models.responses import StandardResponse
from services.player_assignment_service import PlayerAssignmentService
from services.roster_service import RosterService

router = APIRouter()
auth = AuthHandler()


def _get_team_club_id(match: dict, team_flag: str) -> str | None:
    """Get the clubId for a team in a match."""
    team = match.get(team_flag, {})
    return team.get("clubId")


def _check_club_admin_authorization(
    token_payload: TokenPayload,
    match: dict,
    team_flag: str,
    current_roster_status: RosterStatusEnum,
) -> None:
    """
    Check CLUB_ADMIN authorization for roster updates.

    Rules:
    - ADMIN/LEAGUE_ADMIN can always update
    - CLUB_ADMIN can update only their own team's roster
    - If roster status is SUBMITTED, only home team CLUB_ADMIN can update (not away)
    """
    user_roles = token_payload.roles

    if "ADMIN" in user_roles or "LEAGUE_ADMIN" in user_roles:
        return

    if "CLUB_ADMIN" not in user_roles:
        raise AuthorizationException(
            message="Admin, League Admin, or Club Admin role required",
            details={"user_roles": user_roles},
        )

    user_club_id = token_payload.clubId
    team_club_id = _get_team_club_id(match, team_flag)

    if not user_club_id or user_club_id != team_club_id:
        raise AuthorizationException(
            message="CLUB_ADMIN can only update their own team's roster",
            details={
                "user_club_id": user_club_id,
                "team_club_id": team_club_id,
                "team_flag": team_flag,
            },
        )

    if current_roster_status == RosterStatusEnum.SUBMITTED and team_flag != "home":
        raise AuthorizationException(
            message="Cannot modify SUBMITTED roster for away team. Only home team admin can modify.",
            details={
                "roster_status": current_roster_status.value,
                "team_flag": team_flag,
            },
        )


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

    This endpoint handles roster updates with proper authorization:
    - ADMIN/LEAGUE_ADMIN: Full access
    - CLUB_ADMIN: Can only update their own team's roster

    On save, roster status is explicitly set to DRAFT and eligibility metadata is reset.
    Jersey numbers are automatically synced to scores/penalties.
    """
    mongodb = request.app.state.mongodb
    service = RosterService(mongodb)

    team_flag = team_flag.lower()
    if team_flag not in ["home", "away"]:
        raise ValidationException(
            field="team_flag", message=f"Must be 'home' or 'away', got '{team_flag}'"
        )

    match = await mongodb["matches"].find_one({"_id": match_id})
    if not match:
        raise ResourceNotFoundException(resource_type="Match", resource_id=match_id)

    current_roster = await service.get_roster(match_id, team_flag)

    _check_club_admin_authorization(
        token_payload=token_payload,
        match=match,
        team_flag=team_flag,
        current_roster_status=current_roster.status,
    )

    force_draft_reset = False
    if roster_update.players is not None:
        force_draft_reset = True

    if force_draft_reset:
        roster_update.status = RosterStatusEnum.DRAFT
        roster_update.eligibilityTimestamp = None
        roster_update.eligibilityValidator = None

    updated_roster, was_modified = await service.update_roster(
        match_id=match_id,
        team_flag=team_flag,
        roster_update=roster_update,
        user_roles=token_payload.roles,
        user_id=token_payload.sub,
    )

    if was_modified and force_draft_reset:
        logger.info(
            f"Roster reset to DRAFT for {team_flag} team in match {match_id}",
            extra={"user": token_payload.sub, "club_id": token_payload.clubId},
        )

    message = (
        f"Roster updated successfully for {team_flag} team"
        if was_modified
        else f"Roster unchanged for {team_flag} team (data identical)"
    )

    return StandardResponse(success=True, data=updated_roster, message=message)


@router.post(
    "/validate",
    response_description="Validate roster player eligibility",
    response_model=StandardResponse[Roster],
)
async def validate_roster(
    request: Request,
    match_id: str = Path(..., description="The match id of the roster"),
    team_flag: str = Path(..., description="The team flag (home/away) of the roster"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> StandardResponse[Roster]:
    """
    Validate all roster players' eligibility and update roster status.

    For each player in the roster:
    - Runs full license validation (including suspension checks)
    - Updates player.eligibilityStatus with their current license status

    After validation:
    - If ALL players have VALID eligibilityStatus: rosterStatus = APPROVED
    - Otherwise: rosterStatus = INVALID

    Sets eligibilityTimestamp and eligibilityValidator for audit trail.
    """
    mongodb = request.app.state.mongodb
    roster_service = RosterService(mongodb)
    assignment_service = PlayerAssignmentService(mongodb)

    team_flag = team_flag.lower()
    if team_flag not in ["home", "away"]:
        raise ValidationException(
            field="team_flag", message=f"Must be 'home' or 'away', got '{team_flag}'"
        )

    match = await mongodb["matches"].find_one({"_id": match_id})
    if not match:
        raise ResourceNotFoundException(resource_type="Match", resource_id=match_id)

    current_roster = await roster_service.get_roster(match_id, team_flag)

    _check_club_admin_authorization(
        token_payload=token_payload,
        match=match,
        team_flag=team_flag,
        current_roster_status=current_roster.status,
    )

    team_data = match.get(team_flag, {})
    team_id = team_data.get("teamId")

    if not team_id:
        logger.warning(f"No teamId found for {team_flag} team in match {match_id}")

    all_valid = True
    updated_players = []

    for roster_player in current_roster.players:
        player_id = roster_player.player.playerId

        validated_player = await assignment_service.update_player_validation_in_db(player_id)

        if not validated_player:
            logger.warning(f"Player {player_id} not found during roster validation")
            roster_player.eligibilityStatus = LicenseStatusEnum.INVALID
            all_valid = False
            updated_players.append(roster_player)
            continue

        player_status = LicenseStatusEnum.INVALID
        team_found = False
        assigned_teams = validated_player.get("assignedTeams", [])

        if team_id:
            for club in assigned_teams:
                for team in club.get("teams", []):
                    if team.get("teamId") == team_id:
                        team_found = True
                        status_value = team.get("status", "UNKNOWN")
                        if isinstance(status_value, str):
                            try:
                                player_status = LicenseStatusEnum(status_value)
                            except ValueError:
                                player_status = LicenseStatusEnum.UNKNOWN
                        else:
                            player_status = status_value
                        break
                if team_found:
                    break

        if not team_found:
            logger.warning(
                f"Player {player_id} not assigned to team {team_id}, "
                f"marking as INVALID"
            )
            player_status = LicenseStatusEnum.INVALID

        roster_player.eligibilityStatus = player_status
        if player_status != LicenseStatusEnum.VALID:
            all_valid = False

        updated_players.append(roster_player)
        logger.info(
            f"Validated player {player_id} for team {team_id}: {player_status.value}"
        )

    new_status = RosterStatusEnum.APPROVED if all_valid else RosterStatusEnum.INVALID

    roster_update = RosterUpdate(
        players=updated_players,
        status=new_status,
        eligibilityTimestamp=datetime.utcnow(),
        eligibilityValidator=token_payload.sub,
    )

    updated_roster, _ = await roster_service.update_roster(
        match_id=match_id,
        team_flag=team_flag,
        roster_update=roster_update,
        user_roles=token_payload.roles,
        user_id=token_payload.sub,
        skip_status_validation=True,
    )

    valid_count = sum(
        1 for p in updated_players if p.eligibilityStatus == LicenseStatusEnum.VALID
    )
    invalid_count = len(updated_players) - valid_count

    logger.info(
        f"Roster validation complete for {team_flag} in match {match_id}: "
        f"{valid_count} valid, {invalid_count} invalid, status={new_status.value}",
        extra={"user": token_payload.sub},
    )

    message = (
        f"Roster validated: {valid_count}/{len(updated_players)} players eligible. "
        f"Status: {new_status.value}"
    )

    return StandardResponse(success=True, data=updated_roster, message=message)
