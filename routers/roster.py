# filename: routers/roster.py
from datetime import datetime

from fastapi import APIRouter, Body, Depends, Path, Request

from authentication import AuthHandler, TokenPayload
from exceptions import AuthorizationException, ResourceNotFoundException, ValidationException
from logging_config import logger
from models.matches import LicenseStatus, Roster, RosterPlayer, RosterStatus, RosterUpdate
from models.players import LicenseInvalidReasonCode
from models.responses import StandardResponse
from services.player_assignment_service import PlayerAssignmentService
from services.roster_service import RosterService

CALLED_MATCH_LIMIT = 5

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
    current_roster_status: RosterStatus,
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

    if current_roster_status == RosterStatus.SUBMITTED and team_flag != "home":
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
    if roster_update.players is not None and roster_update.status != RosterStatus.SUBMITTED:
        force_draft_reset = True

    if force_draft_reset:
        roster_update.status = RosterStatus.DRAFT
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


def _find_team_in_assigned_teams(
    assigned_teams: list[dict], target_team_id: str
) -> dict | None:
    for club in assigned_teams:
        for team in club.get("teams", []):
            if team.get("teamId") == target_team_id:
                return team
    return None


def _extract_status_and_reasons(
    team_data: dict,
) -> tuple[LicenseStatus, list[LicenseInvalidReasonCode]]:
    status_value = team_data.get("status", "UNKNOWN")
    if isinstance(status_value, str):
        try:
            status = LicenseStatus(status_value)
        except ValueError:
            status = LicenseStatus.UNKNOWN
    else:
        status = status_value

    raw_codes = team_data.get("invalidReasonCodes", [])
    reason_codes = []
    for code in raw_codes:
        if isinstance(code, str):
            try:
                reason_codes.append(LicenseInvalidReasonCode(code))
            except ValueError:
                pass
        else:
            reason_codes.append(code)

    return status, reason_codes


def _count_called_matches(player: dict, to_team_id: str) -> int:
    trackings = player.get("playUpTrackings", []) or []
    total = 0
    for tracking in trackings:
        if tracking.get("toTeamId") == to_team_id:
            for occ in tracking.get("occurrences", []):
                if occ.get("counted", True):
                    total += 1
    return total


def _validate_called_player(
    validated_player: dict,
    roster_player: "RosterPlayer",
    match_team_id: str,
    match: dict,
) -> tuple[LicenseStatus, list[LicenseInvalidReasonCode]]:
    player_id = roster_player.player.playerId
    assigned_teams = validated_player.get("assignedTeams", [])
    reason_codes: list[LicenseInvalidReasonCode] = []

    origin_team_id = None
    if roster_player.calledFromTeam:
        origin_team_id = roster_player.calledFromTeam.teamId

    if not origin_team_id:
        logger.warning(
            f"Called player {player_id} has no calledFromTeam, "
            f"cannot validate origin license"
        )
        return LicenseStatus.INVALID, reason_codes

    origin_team = _find_team_in_assigned_teams(assigned_teams, origin_team_id)
    if not origin_team:
        logger.warning(
            f"Called player {player_id} origin team {origin_team_id} "
            f"not found in assignedTeams"
        )
        return LicenseStatus.INVALID, reason_codes

    origin_status, origin_reasons = _extract_status_and_reasons(origin_team)
    if origin_status != LicenseStatus.VALID:
        logger.info(
            f"Called player {player_id} origin license is {origin_status.value}"
        )
        return LicenseStatus.INVALID, origin_reasons

    called_count = _count_called_matches(validated_player, match_team_id)
    if called_count >= CALLED_MATCH_LIMIT:
        logger.info(
            f"Called player {player_id} has {called_count} called matches "
            f"(limit: {CALLED_MATCH_LIMIT}), marking INVALID"
        )
        return LicenseStatus.INVALID, [LicenseInvalidReasonCode.CALLED_LIMIT_EXCEEDED]

    logger.info(
        f"Called player {player_id} validated via origin team {origin_team_id}: "
        f"VALID ({called_count}/{CALLED_MATCH_LIMIT} called matches)"
    )
    return LicenseStatus.VALID, []


def _validate_regular_player(
    validated_player: dict,
    player_id: str,
    team_id: str,
) -> tuple[LicenseStatus, list[LicenseInvalidReasonCode]]:
    assigned_teams = validated_player.get("assignedTeams", [])

    if not team_id:
        return LicenseStatus.INVALID, []

    team = _find_team_in_assigned_teams(assigned_teams, team_id)
    if not team:
        logger.warning(
            f"Player {player_id} not assigned to team {team_id}, marking as INVALID"
        )
        return LicenseStatus.INVALID, []

    return _extract_status_and_reasons(team)


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
            roster_player.eligibilityStatus = LicenseStatus.INVALID
            roster_player.invalidReasonCodes = []
            all_valid = False
            updated_players.append(roster_player)
            continue

        if roster_player.called:
            player_status, reason_codes = _validate_called_player(
                validated_player, roster_player, team_id, match
            )
        else:
            player_status, reason_codes = _validate_regular_player(
                validated_player, player_id, team_id
            )

        roster_player.eligibilityStatus = player_status
        roster_player.invalidReasonCodes = reason_codes
        if player_status != LicenseStatus.VALID:
            all_valid = False

        updated_players.append(roster_player)
        logger.info(f"Validated player {player_id} for team {team_id}: {player_status.value}")

    new_status = RosterStatus.APPROVED if all_valid else RosterStatus.INVALID

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

    valid_count = sum(1 for p in updated_players if p.eligibilityStatus == LicenseStatus.VALID)
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
