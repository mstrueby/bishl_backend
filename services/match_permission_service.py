from datetime import datetime
from enum import Enum

from authentication import TokenPayload
from config import settings
from exceptions import AuthorizationException


class MatchAction(str, Enum):
    EDIT_SCHEDULING = "EDIT_SCHEDULING"
    EDIT_STATUS_RESULT = "EDIT_STATUS_RESULT"
    EDIT_MATCH_DATA = "EDIT_MATCH_DATA"
    EDIT_ROSTER_HOME = "EDIT_ROSTER_HOME"
    EDIT_ROSTER_AWAY = "EDIT_ROSTER_AWAY"
    EDIT_SCORES_HOME = "EDIT_SCORES_HOME"
    EDIT_SCORES_AWAY = "EDIT_SCORES_AWAY"
    EDIT_PENALTIES_HOME = "EDIT_PENALTIES_HOME"
    EDIT_PENALTIES_AWAY = "EDIT_PENALTIES_AWAY"
    ACCESS_MATCH_CENTER = "ACCESS_MATCH_CENTER"
    EDIT_SUPPLEMENTARY = "EDIT_SUPPLEMENTARY"


class MatchPermissionService:

    def __init__(self, mongodb=None):
        self.mongodb = mongodb

    async def get_matchday_owner(self, match: dict) -> dict | None:
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

        # --- Derive all boolean flags ---
        is_admin_or_league_admin = "ADMIN" in user_roles or "LEAGUE_ADMIN" in user_roles
        is_club_admin = "CLUB_ADMIN" in user_roles

        now = datetime.now()
        match_start = match.get("startDate")
        match_date = match_start.date() if match_start else None
        today = now.date()

        is_match_day = match_date is not None and match_date == today
        is_match_in_past = match_date is not None and match_date < today

        match_status = (match.get("matchStatus") or {}).get("key", "SCHEDULED")
        is_match_in_progress = match_status == "INPROGRESS"
        is_match_scheduled = match_status == "SCHEDULED"
        is_match_finished = not is_match_in_progress and not is_match_scheduled

        home_club_id = (match.get("home") or {}).get("clubId")
        away_club_id = (match.get("away") or {}).get("clubId")
        is_home_club_admin = is_club_admin and bool(user_club_id) and user_club_id == home_club_id
        is_away_club_admin = is_club_admin and bool(user_club_id) and user_club_id == away_club_id

        has_matchday_owner = matchday_owner is not None and bool(matchday_owner.get("clubId"))
        is_matchday_owner = (
            is_club_admin
            and bool(user_club_id)
            and has_matchday_owner
            and matchday_owner.get("clubId") == user_club_id
        )

        match_season = (match.get("season") or {}).get("alias", "")
        current_season = settings.CURRENT_SEASON
        is_current_season = not current_season or not match_season or match_season == current_season

        # All permissions default to False (deny by default)
        perms: dict[MatchAction, bool] = {a: False for a in MatchAction}

        # Rule 1 — Unauthenticated: no roles → deny everything (handled by auth_wrapper upstream,
        # but if someone has no meaningful role they won't match any grant below)

        # Rule 2 — Non-admins blocked from past matches
        if is_match_in_past and not is_admin_or_league_admin:
            # Skip Rules 3-8; jump straight to Rule 9
            pass
        else:
            # Rule 3 — ADMIN / LEAGUE_ADMIN baseline
            if is_admin_or_league_admin:
                perms[MatchAction.EDIT_SCHEDULING] = True
                perms[MatchAction.EDIT_STATUS_RESULT] = True
                perms[MatchAction.EDIT_MATCH_DATA] = True
                if is_match_day or is_match_in_progress:
                    perms[MatchAction.EDIT_ROSTER_HOME] = True
                    perms[MatchAction.EDIT_ROSTER_AWAY] = True
                    perms[MatchAction.ACCESS_MATCH_CENTER] = True
                    perms[MatchAction.EDIT_SUPPLEMENTARY] = True
                    perms[MatchAction.EDIT_SCORES_HOME] = True
                    perms[MatchAction.EDIT_SCORES_AWAY] = True
                    perms[MatchAction.EDIT_PENALTIES_HOME] = True
                    perms[MatchAction.EDIT_PENALTIES_AWAY] = True

            # Rule 4 — Home CLUB_ADMIN
            if is_home_club_admin:
                perms[MatchAction.EDIT_ROSTER_HOME] = True
                if is_match_day:
                    perms[MatchAction.EDIT_ROSTER_AWAY] = True
                    perms[MatchAction.EDIT_STATUS_RESULT] = True
                    perms[MatchAction.ACCESS_MATCH_CENTER] = True
                    perms[MatchAction.EDIT_SUPPLEMENTARY] = True
                    perms[MatchAction.EDIT_MATCH_DATA] = True

            # Rule 5 — Away CLUB_ADMIN
            if is_away_club_admin:
                if not is_match_day and not is_match_in_past:
                    perms[MatchAction.EDIT_ROSTER_AWAY] = True
                if is_match_day and not is_match_in_progress:
                    perms[MatchAction.EDIT_ROSTER_AWAY] = True

            # Rule 6 — Matchday owner CLUB_ADMIN
            if is_matchday_owner and is_match_day:
                perms[MatchAction.EDIT_ROSTER_HOME] = True
                perms[MatchAction.EDIT_ROSTER_AWAY] = True
                perms[MatchAction.EDIT_STATUS_RESULT] = True
                perms[MatchAction.ACCESS_MATCH_CENTER] = True
                perms[MatchAction.EDIT_SUPPLEMENTARY] = True
                perms[MatchAction.EDIT_MATCH_DATA] = True

            # Grant scores/penalties to anyone with match center access
            # (live match event recording is a match-center-level operation)
            if perms[MatchAction.ACCESS_MATCH_CENTER]:
                perms[MatchAction.EDIT_SCORES_HOME] = True
                perms[MatchAction.EDIT_SCORES_AWAY] = True
                perms[MatchAction.EDIT_PENALTIES_HOME] = True
                perms[MatchAction.EDIT_PENALTIES_AWAY] = True

            # Rule 7 — Non-production only: home/matchday owner admin may edit scheduling
            if settings.ENVIRONMENT != "production":
                if is_home_club_admin:
                    perms[MatchAction.EDIT_SCHEDULING] = True
                if is_matchday_owner:
                    perms[MatchAction.EDIT_SCHEDULING] = True

            # Rule 8 — Finished match overrides (applied last within the non-past block)
            if is_match_finished:
                if is_admin_or_league_admin:
                    # Grant all ten permissions
                    for k in perms:
                        perms[k] = True
                else:
                    # Revoke the non-score/penalty gates for non-admins
                    perms[MatchAction.EDIT_SCHEDULING] = False
                    perms[MatchAction.EDIT_ROSTER_HOME] = False
                    perms[MatchAction.EDIT_ROSTER_AWAY] = False
                    perms[MatchAction.EDIT_STATUS_RESULT] = False
                    perms[MatchAction.ACCESS_MATCH_CENTER] = False
                    perms[MatchAction.EDIT_SUPPLEMENTARY] = False
                    perms[MatchAction.EDIT_MATCH_DATA] = False
                    # Restore full match-day gates to home club admin or matchday owner
                    if is_match_day and (is_home_club_admin or is_matchday_owner):
                        perms[MatchAction.EDIT_STATUS_RESULT] = True
                        perms[MatchAction.ACCESS_MATCH_CENTER] = True
                        perms[MatchAction.EDIT_ROSTER_HOME] = True
                        perms[MatchAction.EDIT_ROSTER_AWAY] = True
                        perms[MatchAction.EDIT_SUPPLEMENTARY] = True
                        perms[MatchAction.EDIT_SCORES_HOME] = True
                        perms[MatchAction.EDIT_SCORES_AWAY] = True
                        perms[MatchAction.EDIT_PENALTIES_HOME] = True
                        perms[MatchAction.EDIT_PENALTIES_AWAY] = True
                    else:
                        perms[MatchAction.EDIT_SCORES_HOME] = False
                        perms[MatchAction.EDIT_SCORES_AWAY] = False
                        perms[MatchAction.EDIT_PENALTIES_HOME] = False
                        perms[MatchAction.EDIT_PENALTIES_AWAY] = False

        # Rule 9 — Season restriction: always applied last, overrides everything
        if not is_current_season:
            for k in perms:
                perms[k] = False

        return perms.get(action, False)

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
