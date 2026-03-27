# filename: routers/roster.py
from datetime import datetime

from fastapi import APIRouter, Body, Depends, Path, Request
from pydantic import BaseModel

from authentication import AuthHandler, TokenPayload
from exceptions import ResourceNotFoundException, ValidationException
from logging_config import logger
from models.matches import LicenseStatus, Roster, RosterPlayer, RosterStatus, RosterUpdate
from models.players import LicenseInvalidReasonCode
from models.responses import StandardResponse
from models.tournaments import CallUpMode, CallUpType
from services.match_permission_service import MatchPermissionService
from services.match_settings_service import resolve_match_settings
from services.player_assignment_service import PlayerAssignmentService
from services.roster_service import RosterService


class GoalieAppearanceUpdate(BaseModel):
    periodsPlayed: list[int]


router = APIRouter()
auth = AuthHandler()


def _get_team_club_id(match: dict, team_flag: str) -> str | None:
    team = match.get(team_flag, {})
    return team.get("clubId")


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
    - CLUB_ADMIN: Permissions based on team ownership, match timing, and matchday owner rules

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

    perm_service = MatchPermissionService(mongodb)
    matchday_owner = await perm_service.get_matchday_owner(match)
    action = perm_service.get_roster_action(team_flag)
    perm_service.check_permission(token_payload, match, action, matchday_owner)

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


def _find_team_in_assigned_teams(assigned_teams: list[dict], target_team_id: str) -> dict | None:
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


def _count_called_matches(
    player: dict,
    to_team_id: str,
    tournament_alias: str,
    season_alias: str,
    call_up_type: CallUpType = CallUpType.MATCH,
) -> int:
    trackings = player.get("playUpTrackings", []) or []
    total = 0
    expected_occ_type = call_up_type.value
    for tracking in trackings:
        if (
            tracking.get("toTeamId") == to_team_id
            and tracking.get("tournamentAlias") == tournament_alias
            and tracking.get("seasonAlias") == season_alias
        ):
            for occ in tracking.get("occurrences", []):
                if occ.get("counted", True) and occ.get("type") == expected_occ_type:
                    total += 1
    return total


def _validate_called_player(
    validated_player: dict,
    roster_player: "RosterPlayer",
    match_team_id: str,
    match: dict,
    max_call_up_appearances: int = 5,
    call_up_type: CallUpType = CallUpType.MATCH,
) -> tuple[LicenseStatus, list[LicenseInvalidReasonCode]]:
    player_id = roster_player.player.playerId
    assigned_teams = validated_player.get("assignedTeams", [])
    reason_codes: list[LicenseInvalidReasonCode] = []

    origin_team_id = None
    if roster_player.calledFromTeam:
        origin_team_id = roster_player.calledFromTeam.teamId

    if not origin_team_id:
        logger.warning(
            f"Called player {player_id} has no calledFromTeam, " f"cannot validate origin license"
        )
        return LicenseStatus.INVALID, reason_codes

    origin_team = _find_team_in_assigned_teams(assigned_teams, origin_team_id)
    if not origin_team:
        logger.warning(
            f"Called player {player_id} origin team {origin_team_id} " f"not found in assignedTeams"
        )
        return LicenseStatus.INVALID, reason_codes

    origin_status, origin_reasons = _extract_status_and_reasons(origin_team)
    if origin_status != LicenseStatus.VALID:
        logger.info(f"Called player {player_id} origin license is {origin_status.value}")
        return LicenseStatus.INVALID, origin_reasons

    t_alias = (match.get("tournament") or {}).get("alias", "")
    s_alias = (match.get("season") or {}).get("alias", "")
    called_count = _count_called_matches(
        validated_player, match_team_id, t_alias, s_alias, call_up_type
    )
    if called_count >= max_call_up_appearances:
        logger.info(
            f"Called player {player_id} has {called_count} called matches "
            f"(limit: {max_call_up_appearances}), marking INVALID"
        )
        return LicenseStatus.INVALID, [LicenseInvalidReasonCode.CALLED_LIMIT_EXCEEDED]

    logger.info(
        f"Called player {player_id} validated via origin team {origin_team_id}: "
        f"VALID ({called_count}/{max_call_up_appearances} called matches)"
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
        logger.warning(f"Player {player_id} not assigned to team {team_id}, marking as INVALID")
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

    perm_service = MatchPermissionService(mongodb)
    matchday_owner = await perm_service.get_matchday_owner(match)
    action = perm_service.get_roster_action(team_flag)
    perm_service.check_permission(token_payload, match, action, matchday_owner)

    t_alias = (match.get("tournament") or {}).get("alias")
    s_alias = (match.get("season") or {}).get("alias")
    r_alias = (match.get("round") or {}).get("alias")
    md_alias = (match.get("matchday") or {}).get("alias")

    match_settings, _ = await resolve_match_settings(
        mongodb, t_alias, s_alias, r_alias, md_alias, match.get("matchSettings")
    )

    max_call_up_appearances = (
        match_settings.maxCallUpAppearances
        if match_settings and match_settings.maxCallUpAppearances is not None
        else 5
    )
    call_up_type = (
        match_settings.callUpType or CallUpType.MATCH if match_settings else CallUpType.MATCH
    )
    call_up_mode = (
        match_settings.callUpMode or CallUpMode.LOCKED if match_settings else CallUpMode.LOCKED
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
                validated_player,
                roster_player,
                team_id,
                match,
                max_call_up_appearances=max_call_up_appearances,
                call_up_type=call_up_type,
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

    updated_roster.callUpType = call_up_type
    updated_roster.callUpMode = call_up_mode

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


@router.patch(
    "/players/{player_id}/goalie-appearance",
    response_description="Update goalie period appearance for a roster player",
    response_model=StandardResponse[RosterPlayer],
)
async def update_goalie_appearance(
    request: Request,
    match_id: str = Path(..., description="The match id"),
    team_flag: str = Path(..., description="The team flag (home/away)"),
    player_id: str = Path(..., description="The player id"),
    appearance_update: GoalieAppearanceUpdate = Body(
        ..., description="Periods played by the goalie"
    ),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> StandardResponse[RosterPlayer]:
    """
    Update the periodsPlayed field for a goalie in a team roster.

    This endpoint records which periods a goalie was in net for a match.
    It performs a targeted update of only the periodsPlayed field — no draft
    reset, no validation trigger, and no other side effects.

    Protected by the same permission checks as the roster PUT endpoint.
    Returns 404 if the player is not found in the roster.
    """
    mongodb = request.app.state.mongodb

    team_flag = team_flag.lower()
    if team_flag not in ["home", "away"]:
        raise ValidationException(
            field="team_flag", message=f"Must be 'home' or 'away', got '{team_flag}'"
        )

    match = await mongodb["matches"].find_one({"_id": match_id})
    if not match:
        raise ResourceNotFoundException(resource_type="Match", resource_id=match_id)

    perm_service = MatchPermissionService(mongodb)
    matchday_owner = await perm_service.get_matchday_owner(match)
    action = perm_service.get_roster_action(team_flag)
    perm_service.check_permission(token_payload, match, action, matchday_owner)

    roster_data = match.get(team_flag, {}).get("roster", {})
    if isinstance(roster_data, dict):
        players = roster_data.get("players", [])
    else:
        players = roster_data if roster_data else []

    player_index = None
    for i, roster_player in enumerate(players):
        if roster_player.get("player", {}).get("playerId") == player_id:
            player_index = i
            break

    if player_index is None:
        raise ResourceNotFoundException(resource_type="RosterPlayer", resource_id=player_id)

    result = await mongodb["matches"].update_one(
        {"_id": match_id},
        {
            "$set": {
                f"{team_flag}.roster.players.{player_index}.periodsPlayed": appearance_update.periodsPlayed
            }
        },
    )

    if not result.acknowledged:
        raise ResourceNotFoundException(resource_type="RosterPlayer", resource_id=player_id)

    updated_match = await mongodb["matches"].find_one({"_id": match_id})
    updated_roster_data = updated_match.get(team_flag, {}).get("roster", {})
    if isinstance(updated_roster_data, dict):
        updated_players = updated_roster_data.get("players", [])
    else:
        updated_players = updated_roster_data if updated_roster_data else []

    updated_player_data = updated_players[player_index]
    updated_roster_player = RosterPlayer(**updated_player_data)

    logger.info(
        f"Updated goalie appearance for player {player_id} in match {match_id} "
        f"({team_flag}): periodsPlayed={appearance_update.periodsPlayed}",
        extra={"user": token_payload.sub},
    )

    return StandardResponse(
        success=True,
        data=updated_roster_player,
        message=f"Updated goalie appearance for player {player_id}: periods {appearance_update.periodsPlayed}",
    )
