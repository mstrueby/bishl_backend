import os
from datetime import datetime
from enum import Enum

from authentication import TokenPayload
from exceptions import AuthorizationException
from logging_config import logger

MATCH_WINDOW_MINUTES = 30


class MatchAction(str, Enum):
    EDIT_MATCH = "EDIT_MATCH"
    CHANGE_STATUS = "CHANGE_STATUS"
    EDIT_ROSTER_HOME = "EDIT_ROSTER_HOME"
    EDIT_ROSTER_AWAY = "EDIT_ROSTER_AWAY"
    EDIT_SCORES_HOME = "EDIT_SCORES_HOME"
    EDIT_SCORES_AWAY = "EDIT_SCORES_AWAY"
    EDIT_PENALTIES_HOME = "EDIT_PENALTIES_HOME"
    EDIT_PENALTIES_AWAY = "EDIT_PENALTIES_AWAY"
    EDIT_SUPPLEMENTARY = "EDIT_SUPPLEMENTARY"


class MatchPermissionService:

    def __init__(self, mongodb=None):
        self.mongodb = mongodb

    async def get_matchday_owner(
        self, match: dict
    ) -> dict | None:
        if self.mongodb is None:
            return None
        t_alias = (match.get("tournament") or {}).get("alias")
        s_alias = (match.get("season") or {}).get("alias")
        r_alias = (match.get("round") or {}).get("alias")
        md_alias = (match.get("matchday") or {}).get("alias")
        if not all([t_alias, s_alias, r_alias, md_alias]):
            return None
        tournament = await self.mongodb["tournaments"].find_one({"alias": t_alias})
        if not tournament:
            return None
        for season in tournament.get("seasons", []):
            if season.get("alias") == s_alias:
                for rnd in season.get("rounds", []):
                    if rnd.get("alias") == r_alias:
                        for md in rnd.get("matchdays", []):
                            if md.get("alias") == md_alias:
                                return md.get("owner")
        return None

    def check_permission(
        self,
        token_payload: TokenPayload,
        match: dict,
        action: MatchAction,
        matchday_owner: dict | None = None,
    ) -> None:
        allowed = self.is_allowed(token_payload, match, action, matchday_owner)
        if not allowed:
            raise AuthorizationException(
                message=f"You do not have permission to perform this action: {action.value}",
                details={
                    "action": action.value,
                    "user_roles": token_payload.roles,
                    "user_club_id": token_payload.clubId,
                },
            )

    def is_allowed(
        self,
        token_payload: TokenPayload,
        match: dict,
        action: MatchAction,
        matchday_owner: dict | None = None,
    ) -> bool:
        user_roles = token_payload.roles
        user_club_id = token_payload.clubId

        if "ADMIN" in user_roles or "LEAGUE_ADMIN" in user_roles:
            return True

        if "CLUB_ADMIN" not in user_roles:
            return False

        current_season = os.environ.get("CURRENT_SEASON", "")
        match_season = (match.get("season") or {}).get("alias", "")
        if current_season and match_season and match_season != current_season:
            return False

        now = datetime.now()
        match_start = match.get("startDate")

        match_date = match_start.date() if match_start else None
        today = now.date()

        is_match_in_past = match_date is not None and match_date < today
        is_match_day = match_date is not None and match_date == today

        match_status = (match.get("matchStatus") or {}).get("key", "SCHEDULED")
        is_in_progress = match_status == "INPROGRESS"
        is_scheduled = match_status == "SCHEDULED"
        is_finished = match_status in ["FINISHED", "CANCELLED", "FORFEITED"] or (not is_in_progress and not is_scheduled)

        if is_match_in_past and not is_match_day:
            return False

        if match_start:
            match_start_ts = match_start.timestamp()
            now_ts = now.timestamp()
            starts_within_window = match_start_ts < (now_ts + MATCH_WINDOW_MINUTES * 60)
        else:
            starts_within_window = False

        home_club_id = (match.get("home") or {}).get("clubId")
        away_club_id = (match.get("away") or {}).get("clubId")
        is_home_admin = user_club_id and user_club_id == home_club_id
        is_away_admin = user_club_id and user_club_id == away_club_id

        is_valid_matchday_owner = (
            matchday_owner is not None
            and matchday_owner.get("clubId") is not None
        )
        is_matchday_owner_admin = (
            is_valid_matchday_owner
            and user_club_id
            and matchday_owner.get("clubId") == user_club_id
            and is_match_day
        )

        if action == MatchAction.EDIT_ROSTER_HOME:
            if is_home_admin:
                return True
            if is_matchday_owner_admin:
                return True
            return False

        if action == MatchAction.EDIT_ROSTER_AWAY:
            if is_away_admin:
                if is_in_progress:
                    return False
                if starts_within_window:
                    roster = (match.get("away") or {}).get("roster") or {}
                    roster_status = roster.get("status", "DRAFT")
                    if roster_status not in ["DRAFT", "SUBMITTED"]:
                        return False
                if not is_finished:
                    return True
                if is_match_day:
                    return True
                return False
            if is_home_admin and starts_within_window and not is_valid_matchday_owner:
                return True
            if is_matchday_owner_admin:
                return True
            return False

        if action in (MatchAction.EDIT_SCORES_HOME, MatchAction.EDIT_SCORES_AWAY,
                       MatchAction.EDIT_PENALTIES_HOME, MatchAction.EDIT_PENALTIES_AWAY):
            if is_finished and is_match_day:
                if is_home_admin or is_matchday_owner_admin:
                    return True
            if starts_within_window:
                if is_home_admin and not is_valid_matchday_owner:
                    return True
                if is_matchday_owner_admin:
                    return True
            return False

        if action == MatchAction.CHANGE_STATUS:
            if is_home_admin and starts_within_window and not is_valid_matchday_owner:
                return True
            if is_matchday_owner_admin:
                return True
            return False

        if action == MatchAction.EDIT_SUPPLEMENTARY:
            if is_home_admin and starts_within_window and not is_valid_matchday_owner:
                return True
            if is_matchday_owner_admin:
                return True
            return False

        if action == MatchAction.EDIT_MATCH:
            return False

        return False

    def get_roster_action(self, team_flag: str) -> MatchAction:
        if team_flag == "home":
            return MatchAction.EDIT_ROSTER_HOME
        return MatchAction.EDIT_ROSTER_AWAY

    def get_scores_action(self, team_flag: str) -> MatchAction:
        if team_flag == "home":
            return MatchAction.EDIT_SCORES_HOME
        return MatchAction.EDIT_SCORES_AWAY

    def get_penalties_action(self, team_flag: str) -> MatchAction:
        if team_flag == "home":
            return MatchAction.EDIT_PENALTIES_HOME
        return MatchAction.EDIT_PENALTIES_AWAY
