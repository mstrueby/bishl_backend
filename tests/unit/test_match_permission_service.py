"""
Unit tests for MatchPermissionService.

Covers all 9 permission rules and all 10 permission gates defined in the spec.
Tests are self-contained — they mock the settings object and require no database.
"""

from datetime import date, datetime
from unittest.mock import patch, MagicMock

import pytest

from authentication import TokenPayload
from services.match_permission_service import MatchAction, MatchPermissionService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ALL_ACTIONS = list(MatchAction)

EDIT_ACTIONS = [
    MatchAction.EDIT_SCHEDULING,
    MatchAction.EDIT_STATUS_RESULT,
    MatchAction.EDIT_ROSTER_HOME,
    MatchAction.EDIT_ROSTER_AWAY,
    MatchAction.EDIT_SCORES_HOME,
    MatchAction.EDIT_SCORES_AWAY,
    MatchAction.EDIT_PENALTIES_HOME,
    MatchAction.EDIT_PENALTIES_AWAY,
    MatchAction.ACCESS_MATCH_CENTER,
    MatchAction.EDIT_SUPPLEMENTARY,
]

CURRENT_SEASON = "2026"
OTHER_SEASON = "2025"


def make_token(roles: list[str], club_id: str | None = None) -> TokenPayload:
    return TokenPayload(
        sub="user-1",
        roles=roles,
        firstName="Test",
        lastName="User",
        clubId=club_id,
    )


def make_match(
    match_date: date | None = None,
    status: str = "SCHEDULED",
    home_club_id: str = "home-club",
    away_club_id: str = "away-club",
    season_alias: str = CURRENT_SEASON,
) -> dict:
    start_dt: datetime | None = None
    if match_date is not None:
        start_dt = datetime(match_date.year, match_date.month, match_date.day, 18, 0)
    return {
        "startDate": start_dt,
        "matchStatus": {"key": status},
        "season": {"alias": season_alias},
        "home": {"clubId": home_club_id},
        "away": {"clubId": away_club_id},
        "tournament": {"alias": "bishl"},
        "round": {"alias": "regular"},
        "matchday": {"alias": "md-1"},
    }


def make_matchday_owner(club_id: str | None) -> dict | None:
    if club_id is None:
        return None
    return {"clubId": club_id, "clubName": "Owner Club"}


def _patch_settings(current_season: str = CURRENT_SEASON, environment: str = "production"):
    mock = MagicMock()
    mock.CURRENT_SEASON = current_season
    mock.ENVIRONMENT = environment
    return patch("services.match_permission_service.settings", mock)


def is_allowed(
    token: TokenPayload,
    match: dict,
    action: MatchAction,
    matchday_owner: dict | None = None,
    current_season: str = CURRENT_SEASON,
    environment: str = "production",
) -> bool:
    svc = MatchPermissionService(mongodb=None)
    with _patch_settings(current_season, environment):
        return svc.is_allowed(token, match, action, matchday_owner)


# ---------------------------------------------------------------------------
# Rule 9 — Season restriction (overrides everything, so test first)
# ---------------------------------------------------------------------------


class TestRule9SeasonRestriction:
    """Rule 9: non-current season revokes ALL permissions, including for admins."""

    def test_admin_non_current_season_denied_all(self):
        token = make_token(["ADMIN"])
        match = make_match(match_date=date.today(), status="SCHEDULED", season_alias=OTHER_SEASON)
        for action in EDIT_ACTIONS:
            assert is_allowed(token, match, action, current_season=CURRENT_SEASON) is False, (
                f"{action} should be denied for admin on non-current season"
            )

    def test_league_admin_non_current_season_denied_all(self):
        token = make_token(["LEAGUE_ADMIN"])
        match = make_match(match_date=date.today(), status="FINISHED", season_alias=OTHER_SEASON)
        for action in EDIT_ACTIONS:
            assert is_allowed(token, match, action, current_season=CURRENT_SEASON) is False

    def test_club_admin_non_current_season_denied(self):
        token = make_token(["CLUB_ADMIN"], club_id="home-club")
        match = make_match(match_date=date.today(), season_alias=OTHER_SEASON)
        for action in EDIT_ACTIONS:
            assert is_allowed(token, match, action, current_season=CURRENT_SEASON) is False

    def test_admin_current_season_allowed_on_match_day(self):
        """Sanity: admin IS allowed when season is correct."""
        token = make_token(["ADMIN"])
        match = make_match(match_date=date.today(), status="SCHEDULED")
        assert is_allowed(token, match, MatchAction.EDIT_SCHEDULING) is True

    def test_no_season_configured_allows_all(self):
        """If CURRENT_SEASON is empty, season check is skipped."""
        token = make_token(["ADMIN"])
        match = make_match(match_date=date.today(), status="SCHEDULED", season_alias="2099")
        assert is_allowed(token, match, MatchAction.EDIT_SCHEDULING, current_season="") is True


# ---------------------------------------------------------------------------
# Rule 2 — Non-admins blocked from past matches
# ---------------------------------------------------------------------------


class TestRule2PastMatchBlocking:

    def _past_date(self) -> date:
        from datetime import timedelta
        return date.today() - timedelta(days=1)

    def test_club_admin_blocked_on_past_match(self):
        token = make_token(["CLUB_ADMIN"], club_id="home-club")
        match = make_match(match_date=self._past_date(), status="SCHEDULED")
        for action in EDIT_ACTIONS:
            assert is_allowed(token, match, action) is False, (
                f"{action} should be denied for club admin on past match"
            )

    def test_admin_allowed_on_past_scheduled_match(self):
        """ADMIN can edit scheduling and change status even for past scheduled matches."""
        token = make_token(["ADMIN"])
        match = make_match(match_date=self._past_date(), status="SCHEDULED")
        assert is_allowed(token, match, MatchAction.EDIT_SCHEDULING) is True
        assert is_allowed(token, match, MatchAction.EDIT_STATUS_RESULT) is True

    def test_league_admin_allowed_on_past_match(self):
        token = make_token(["LEAGUE_ADMIN"])
        match = make_match(match_date=self._past_date(), status="SCHEDULED")
        assert is_allowed(token, match, MatchAction.EDIT_SCHEDULING) is True

    def test_admin_on_past_finished_match_gets_all_ten(self):
        """Rule 8 + Rule 2 interaction: admin on past finished match gets all 10."""
        token = make_token(["ADMIN"])
        match = make_match(match_date=self._past_date(), status="FINISHED")
        for action in EDIT_ACTIONS:
            assert is_allowed(token, match, action) is True, (
                f"{action} should be granted to admin on past finished match"
            )


# ---------------------------------------------------------------------------
# Rule 3 — ADMIN / LEAGUE_ADMIN baseline
# ---------------------------------------------------------------------------


class TestRule3AdminBaseline:

    def test_admin_always_gets_edit_scheduling(self):
        token = make_token(["ADMIN"])
        match = make_match(match_date=date.today(), status="SCHEDULED")
        assert is_allowed(token, match, MatchAction.EDIT_SCHEDULING) is True

    def test_admin_always_gets_change_status(self):
        token = make_token(["ADMIN"])
        match = make_match(match_date=date.today(), status="SCHEDULED")
        assert is_allowed(token, match, MatchAction.EDIT_STATUS_RESULT) is True

    def test_admin_gets_roster_on_match_day(self):
        token = make_token(["ADMIN"])
        match = make_match(match_date=date.today(), status="SCHEDULED")
        assert is_allowed(token, match, MatchAction.EDIT_ROSTER_HOME) is True
        assert is_allowed(token, match, MatchAction.EDIT_ROSTER_AWAY) is True

    def test_admin_gets_match_center_on_match_day(self):
        token = make_token(["ADMIN"])
        match = make_match(match_date=date.today(), status="SCHEDULED")
        assert is_allowed(token, match, MatchAction.ACCESS_MATCH_CENTER) is True
        assert is_allowed(token, match, MatchAction.EDIT_SUPPLEMENTARY) is True

    def test_admin_gets_roster_when_in_progress(self):
        """isMatchInProgress also triggers admin roster/match center access."""
        from datetime import timedelta
        token = make_token(["ADMIN"])
        match = make_match(match_date=date.today() - timedelta(days=1), status="INPROGRESS")
        assert is_allowed(token, match, MatchAction.EDIT_ROSTER_HOME) is True
        assert is_allowed(token, match, MatchAction.ACCESS_MATCH_CENTER) is True

    def test_admin_denied_roster_on_future_scheduled_match(self):
        """Admin does NOT get roster editing for a future scheduled match (Rule 3)."""
        from datetime import timedelta
        token = make_token(["ADMIN"])
        future_date = date.today() + timedelta(days=3)
        match = make_match(match_date=future_date, status="SCHEDULED")
        assert is_allowed(token, match, MatchAction.EDIT_ROSTER_HOME) is False
        assert is_allowed(token, match, MatchAction.EDIT_ROSTER_AWAY) is False
        assert is_allowed(token, match, MatchAction.ACCESS_MATCH_CENTER) is False
        assert is_allowed(token, match, MatchAction.EDIT_SUPPLEMENTARY) is False

    def test_admin_scheduling_allowed_on_future_match(self):
        from datetime import timedelta
        token = make_token(["ADMIN"])
        future_date = date.today() + timedelta(days=3)
        match = make_match(match_date=future_date, status="SCHEDULED")
        assert is_allowed(token, match, MatchAction.EDIT_SCHEDULING) is True
        assert is_allowed(token, match, MatchAction.EDIT_STATUS_RESULT) is True

    def test_league_admin_same_as_admin(self):
        token = make_token(["LEAGUE_ADMIN"])
        match = make_match(match_date=date.today(), status="SCHEDULED")
        assert is_allowed(token, match, MatchAction.EDIT_SCHEDULING) is True
        assert is_allowed(token, match, MatchAction.EDIT_ROSTER_HOME) is True


# ---------------------------------------------------------------------------
# Rule 4 — Home CLUB_ADMIN
# ---------------------------------------------------------------------------


class TestRule4HomeClubAdmin:

    def test_home_admin_always_gets_edit_roster_home(self):
        """Home admin can always edit home roster (regardless of match day, Rule 4)."""
        from datetime import timedelta
        token = make_token(["CLUB_ADMIN"], club_id="home-club")
        for delta_days in [-0, 1, 3]:
            match_date = date.today() + timedelta(days=delta_days)
            match = make_match(match_date=match_date, status="SCHEDULED")
            assert is_allowed(token, match, MatchAction.EDIT_ROSTER_HOME) is True, (
                f"Home admin should edit home roster (delta={delta_days})"
            )

    def test_home_admin_on_match_day_no_matchday_owner_gets_all(self):
        """Rule 4: on match day with no matchday owner, home admin gets full set."""
        token = make_token(["CLUB_ADMIN"], club_id="home-club")
        match = make_match(match_date=date.today(), status="SCHEDULED")
        owner = make_matchday_owner(None)
        assert is_allowed(token, match, MatchAction.EDIT_ROSTER_AWAY, owner) is True
        assert is_allowed(token, match, MatchAction.EDIT_STATUS_RESULT, owner) is True
        assert is_allowed(token, match, MatchAction.ACCESS_MATCH_CENTER, owner) is True
        assert is_allowed(token, match, MatchAction.EDIT_SUPPLEMENTARY, owner) is True

    def test_home_admin_on_match_day_with_matchday_owner_limited(self):
        """Rule 4: when a matchday owner is set, home admin does NOT get those extra gates."""
        token = make_token(["CLUB_ADMIN"], club_id="home-club")
        match = make_match(match_date=date.today(), status="SCHEDULED")
        owner = make_matchday_owner("matchday-owner-club")
        assert is_allowed(token, match, MatchAction.EDIT_ROSTER_AWAY, owner) is False
        assert is_allowed(token, match, MatchAction.EDIT_STATUS_RESULT, owner) is False
        assert is_allowed(token, match, MatchAction.ACCESS_MATCH_CENTER, owner) is False
        assert is_allowed(token, match, MatchAction.EDIT_SUPPLEMENTARY, owner) is False
        # BUT home roster editing is always allowed for home admin
        assert is_allowed(token, match, MatchAction.EDIT_ROSTER_HOME, owner) is True

    def test_home_admin_off_match_day_no_extra_gates(self):
        """Home admin on a non-match-day has only home roster editing."""
        from datetime import timedelta
        token = make_token(["CLUB_ADMIN"], club_id="home-club")
        future_date = date.today() + timedelta(days=2)
        match = make_match(match_date=future_date, status="SCHEDULED")
        assert is_allowed(token, match, MatchAction.EDIT_ROSTER_HOME) is True
        assert is_allowed(token, match, MatchAction.EDIT_ROSTER_AWAY) is False
        assert is_allowed(token, match, MatchAction.EDIT_STATUS_RESULT) is False
        assert is_allowed(token, match, MatchAction.ACCESS_MATCH_CENTER) is False
        assert is_allowed(token, match, MatchAction.EDIT_SUPPLEMENTARY) is False
        assert is_allowed(token, match, MatchAction.EDIT_SCHEDULING) is False


# ---------------------------------------------------------------------------
# Rule 5 — Away CLUB_ADMIN
# ---------------------------------------------------------------------------


class TestRule5AwayClubAdmin:

    def test_away_admin_can_edit_roster_before_match_day(self):
        """Away admin can edit their roster for a future match (not past, not today)."""
        from datetime import timedelta
        token = make_token(["CLUB_ADMIN"], club_id="away-club")
        future_date = date.today() + timedelta(days=2)
        match = make_match(match_date=future_date, status="SCHEDULED")
        assert is_allowed(token, match, MatchAction.EDIT_ROSTER_AWAY) is True

    def test_away_admin_can_edit_roster_on_match_day_before_start(self):
        """Away admin can edit roster on match day as long as match hasn't started."""
        token = make_token(["CLUB_ADMIN"], club_id="away-club")
        match = make_match(match_date=date.today(), status="SCHEDULED")
        assert is_allowed(token, match, MatchAction.EDIT_ROSTER_AWAY) is True

    def test_away_admin_cannot_edit_roster_once_in_progress(self):
        """Away admin loses roster edit access once match is INPROGRESS."""
        token = make_token(["CLUB_ADMIN"], club_id="away-club")
        match = make_match(match_date=date.today(), status="INPROGRESS")
        assert is_allowed(token, match, MatchAction.EDIT_ROSTER_AWAY) is False

    def test_away_admin_cannot_edit_home_roster(self):
        token = make_token(["CLUB_ADMIN"], club_id="away-club")
        match = make_match(match_date=date.today(), status="SCHEDULED")
        assert is_allowed(token, match, MatchAction.EDIT_ROSTER_HOME) is False

    def test_away_admin_no_match_center_access(self):
        """Away admin never gets match center, status, or supplementary access."""
        from datetime import timedelta
        token = make_token(["CLUB_ADMIN"], club_id="away-club")
        for delta in [0, 1, 3]:
            match_date = date.today() + timedelta(days=delta)
            match = make_match(match_date=match_date, status="SCHEDULED")
            assert is_allowed(token, match, MatchAction.ACCESS_MATCH_CENTER) is False
            assert is_allowed(token, match, MatchAction.EDIT_SUPPLEMENTARY) is False
            assert is_allowed(token, match, MatchAction.EDIT_STATUS_RESULT) is False


# ---------------------------------------------------------------------------
# Rule 6 — Matchday owner CLUB_ADMIN
# ---------------------------------------------------------------------------


class TestRule6MatchdayOwner:

    def test_matchday_owner_on_match_day_gets_full_set(self):
        """Rule 6: matchday owner on match day gets rosters, status, match center, supplementary."""
        token = make_token(["CLUB_ADMIN"], club_id="owner-club")
        match = make_match(match_date=date.today(), status="SCHEDULED")
        owner = make_matchday_owner("owner-club")
        assert is_allowed(token, match, MatchAction.EDIT_ROSTER_HOME, owner) is True
        assert is_allowed(token, match, MatchAction.EDIT_ROSTER_AWAY, owner) is True
        assert is_allowed(token, match, MatchAction.EDIT_STATUS_RESULT, owner) is True
        assert is_allowed(token, match, MatchAction.ACCESS_MATCH_CENTER, owner) is True
        assert is_allowed(token, match, MatchAction.EDIT_SUPPLEMENTARY, owner) is True

    def test_matchday_owner_off_match_day_gets_nothing_extra(self):
        """Matchday owner gets no extra gates outside of match day."""
        from datetime import timedelta
        token = make_token(["CLUB_ADMIN"], club_id="owner-club")
        future_date = date.today() + timedelta(days=2)
        match = make_match(match_date=future_date, status="SCHEDULED")
        owner = make_matchday_owner("owner-club")
        assert is_allowed(token, match, MatchAction.ACCESS_MATCH_CENTER, owner) is False
        assert is_allowed(token, match, MatchAction.EDIT_STATUS_RESULT, owner) is False
        assert is_allowed(token, match, MatchAction.EDIT_SUPPLEMENTARY, owner) is False

    def test_matchday_owner_supersedes_home_admin_on_match_day(self):
        """When a matchday owner is set, the home admin does NOT get change-status etc."""
        home_token = make_token(["CLUB_ADMIN"], club_id="home-club")
        match = make_match(match_date=date.today(), home_club_id="home-club")
        owner = make_matchday_owner("owner-club")
        # Home admin loses status/match center when a matchday owner is assigned
        assert is_allowed(home_token, match, MatchAction.EDIT_STATUS_RESULT, owner) is False
        assert is_allowed(home_token, match, MatchAction.ACCESS_MATCH_CENTER, owner) is False
        # But home admin keeps home roster editing
        assert is_allowed(home_token, match, MatchAction.EDIT_ROSTER_HOME, owner) is True

    def test_non_owner_club_admin_denied_matchday_owner_gates(self):
        """A club admin whose club is NOT the matchday owner gets nothing extra."""
        token = make_token(["CLUB_ADMIN"], club_id="some-other-club")
        match = make_match(match_date=date.today(), status="SCHEDULED")
        owner = make_matchday_owner("owner-club")
        assert is_allowed(token, match, MatchAction.ACCESS_MATCH_CENTER, owner) is False
        assert is_allowed(token, match, MatchAction.EDIT_STATUS_RESULT, owner) is False

    def test_matchday_owner_scores_on_match_day(self):
        """Matchday owner on match day can edit scores (via ACCESS_MATCH_CENTER)."""
        token = make_token(["CLUB_ADMIN"], club_id="owner-club")
        match = make_match(match_date=date.today(), status="INPROGRESS")
        owner = make_matchday_owner("owner-club")
        assert is_allowed(token, match, MatchAction.EDIT_SCORES_HOME, owner) is True
        assert is_allowed(token, match, MatchAction.EDIT_SCORES_AWAY, owner) is True


# ---------------------------------------------------------------------------
# Rule 7 — Non-production scheduling
# ---------------------------------------------------------------------------


class TestRule7NonProductionScheduling:

    def test_home_admin_can_reschedule_in_non_prod(self):
        from datetime import timedelta
        token = make_token(["CLUB_ADMIN"], club_id="home-club")
        future_date = date.today() + timedelta(days=3)
        match = make_match(match_date=future_date, status="SCHEDULED")
        assert is_allowed(token, match, MatchAction.EDIT_SCHEDULING, environment="development") is True

    def test_matchday_owner_can_reschedule_in_non_prod(self):
        from datetime import timedelta
        token = make_token(["CLUB_ADMIN"], club_id="owner-club")
        future_date = date.today() + timedelta(days=3)
        match = make_match(match_date=future_date, status="SCHEDULED")
        owner = make_matchday_owner("owner-club")
        assert (
            is_allowed(token, match, MatchAction.EDIT_SCHEDULING, owner, environment="development")
            is True
        )

    def test_home_admin_cannot_reschedule_in_production(self):
        from datetime import timedelta
        token = make_token(["CLUB_ADMIN"], club_id="home-club")
        future_date = date.today() + timedelta(days=3)
        match = make_match(match_date=future_date, status="SCHEDULED")
        assert is_allowed(token, match, MatchAction.EDIT_SCHEDULING, environment="production") is False

    def test_away_admin_cannot_reschedule_even_in_non_prod(self):
        from datetime import timedelta
        token = make_token(["CLUB_ADMIN"], club_id="away-club")
        future_date = date.today() + timedelta(days=3)
        match = make_match(match_date=future_date, status="SCHEDULED")
        assert is_allowed(token, match, MatchAction.EDIT_SCHEDULING, environment="development") is False

    def test_non_prod_does_not_override_season_lock(self):
        from datetime import timedelta
        token = make_token(["CLUB_ADMIN"], club_id="home-club")
        future_date = date.today() + timedelta(days=3)
        match = make_match(match_date=future_date, status="SCHEDULED", season_alias=OTHER_SEASON)
        assert (
            is_allowed(token, match, MatchAction.EDIT_SCHEDULING, environment="development") is False
        )


# ---------------------------------------------------------------------------
# Rule 8 — Finished match overrides
# ---------------------------------------------------------------------------


class TestRule8FinishedMatch:

    def test_admin_finished_match_gets_all_ten(self):
        """Admin on a finished match gets all 10 gates."""
        token = make_token(["ADMIN"])
        match = make_match(match_date=date.today(), status="FINISHED")
        for action in EDIT_ACTIONS:
            assert is_allowed(token, match, action) is True, (
                f"Admin should have {action} on finished match"
            )

    def test_league_admin_finished_match_gets_all_ten(self):
        token = make_token(["LEAGUE_ADMIN"])
        match = make_match(match_date=date.today(), status="FINISHED")
        for action in EDIT_ACTIONS:
            assert is_allowed(token, match, action) is True

    def test_home_admin_finished_match_on_match_day_gets_scores_penalties(self):
        """Home admin on match day + finished match can edit scores and penalties."""
        token = make_token(["CLUB_ADMIN"], club_id="home-club")
        match = make_match(match_date=date.today(), status="FINISHED")
        assert is_allowed(token, match, MatchAction.EDIT_SCORES_HOME) is True
        assert is_allowed(token, match, MatchAction.EDIT_SCORES_AWAY) is True
        assert is_allowed(token, match, MatchAction.EDIT_PENALTIES_HOME) is True
        assert is_allowed(token, match, MatchAction.EDIT_PENALTIES_AWAY) is True

    def test_home_admin_finished_match_on_match_day_cannot_edit_roster_or_status(self):
        """Rule 8: roster/status/match-center revoked for non-admins in finished match."""
        token = make_token(["CLUB_ADMIN"], club_id="home-club")
        match = make_match(match_date=date.today(), status="FINISHED")
        assert is_allowed(token, match, MatchAction.EDIT_ROSTER_HOME) is False
        assert is_allowed(token, match, MatchAction.EDIT_ROSTER_AWAY) is False
        assert is_allowed(token, match, MatchAction.EDIT_STATUS_RESULT) is False
        assert is_allowed(token, match, MatchAction.ACCESS_MATCH_CENTER) is False
        assert is_allowed(token, match, MatchAction.EDIT_SUPPLEMENTARY) is False

    def test_matchday_owner_finished_match_on_match_day_gets_scores_penalties(self):
        """Matchday owner on match day + finished can edit scores/penalties (Rule 8)."""
        token = make_token(["CLUB_ADMIN"], club_id="owner-club")
        match = make_match(match_date=date.today(), status="FINISHED")
        owner = make_matchday_owner("owner-club")
        assert is_allowed(token, match, MatchAction.EDIT_SCORES_HOME, owner) is True
        assert is_allowed(token, match, MatchAction.EDIT_PENALTIES_AWAY, owner) is True

    def test_away_admin_finished_match_gets_no_scores_penalties(self):
        """Away admin is not home/matchday owner so Rule 8 doesn't grant scores."""
        token = make_token(["CLUB_ADMIN"], club_id="away-club")
        match = make_match(match_date=date.today(), status="FINISHED")
        assert is_allowed(token, match, MatchAction.EDIT_SCORES_HOME) is False
        assert is_allowed(token, match, MatchAction.EDIT_SCORES_AWAY) is False
        assert is_allowed(token, match, MatchAction.EDIT_PENALTIES_HOME) is False
        assert is_allowed(token, match, MatchAction.EDIT_PENALTIES_AWAY) is False

    def test_home_admin_finished_match_off_match_day_no_scores_penalties(self):
        """Rule 8: home admin + finished but NOT match day → no scores/penalties."""
        from datetime import timedelta
        token = make_token(["CLUB_ADMIN"], club_id="home-club")
        yesterday = date.today() - timedelta(days=1)
        match = make_match(match_date=yesterday, status="FINISHED")
        # Rule 2 blocks non-admins on past matches → all denied
        for action in EDIT_ACTIONS:
            assert is_allowed(token, match, action) is False

    def test_cancelled_match_treated_as_finished(self):
        """CANCELLED status is treated as finished (not SCHEDULED/INPROGRESS)."""
        token = make_token(["CLUB_ADMIN"], club_id="home-club")
        match = make_match(match_date=date.today(), status="CANCELLED")
        # Non-admin on finished match: scores/penalties granted for home admin on match day
        assert is_allowed(token, match, MatchAction.EDIT_SCORES_HOME) is True
        # Roster revoked
        assert is_allowed(token, match, MatchAction.EDIT_ROSTER_HOME) is False

    def test_forfeited_match_treated_as_finished(self):
        token = make_token(["CLUB_ADMIN"], club_id="home-club")
        match = make_match(match_date=date.today(), status="FORFEITED")
        assert is_allowed(token, match, MatchAction.EDIT_SCORES_HOME) is True
        assert is_allowed(token, match, MatchAction.EDIT_ROSTER_HOME) is False


# ---------------------------------------------------------------------------
# Rule 8 + Rule 9 interaction
# ---------------------------------------------------------------------------


class TestRule8Rule9Interaction:

    def test_season_restriction_overrides_admin_finished_match(self):
        """Rule 9 overrides Rule 8: admin on finished non-current-season match is denied."""
        token = make_token(["ADMIN"])
        match = make_match(match_date=date.today(), status="FINISHED", season_alias=OTHER_SEASON)
        for action in EDIT_ACTIONS:
            assert is_allowed(token, match, action, current_season=CURRENT_SEASON) is False

    def test_season_restriction_overrides_home_admin_finished_match(self):
        token = make_token(["CLUB_ADMIN"], club_id="home-club")
        match = make_match(match_date=date.today(), status="FINISHED", season_alias=OTHER_SEASON)
        for action in EDIT_ACTIONS:
            assert is_allowed(token, match, action, current_season=CURRENT_SEASON) is False


# ---------------------------------------------------------------------------
# Live match (INPROGRESS) scenarios
# ---------------------------------------------------------------------------


class TestInProgressMatch:

    def test_home_admin_no_matchday_owner_can_access_match_center_inprogress(self):
        token = make_token(["CLUB_ADMIN"], club_id="home-club")
        match = make_match(match_date=date.today(), status="INPROGRESS")
        assert is_allowed(token, match, MatchAction.ACCESS_MATCH_CENTER) is True
        assert is_allowed(token, match, MatchAction.EDIT_SCORES_HOME) is True
        assert is_allowed(token, match, MatchAction.EDIT_PENALTIES_HOME) is True

    def test_away_admin_cannot_edit_roster_while_inprogress(self):
        token = make_token(["CLUB_ADMIN"], club_id="away-club")
        match = make_match(match_date=date.today(), status="INPROGRESS")
        assert is_allowed(token, match, MatchAction.EDIT_ROSTER_AWAY) is False

    def test_matchday_owner_can_access_match_center_inprogress(self):
        token = make_token(["CLUB_ADMIN"], club_id="owner-club")
        match = make_match(match_date=date.today(), status="INPROGRESS")
        owner = make_matchday_owner("owner-club")
        assert is_allowed(token, match, MatchAction.ACCESS_MATCH_CENTER, owner) is True
        assert is_allowed(token, match, MatchAction.EDIT_SCORES_HOME, owner) is True

    def test_admin_gets_scores_while_inprogress(self):
        token = make_token(["ADMIN"])
        match = make_match(match_date=date.today(), status="INPROGRESS")
        assert is_allowed(token, match, MatchAction.EDIT_SCORES_HOME) is True
        assert is_allowed(token, match, MatchAction.EDIT_SCORES_AWAY) is True


# ---------------------------------------------------------------------------
# Unauthenticated / unknown role
# ---------------------------------------------------------------------------


class TestUnknownRole:

    def test_user_with_no_relevant_role_denied_all(self):
        token = make_token(["REFEREE"])
        match = make_match(match_date=date.today(), status="SCHEDULED")
        for action in EDIT_ACTIONS:
            assert is_allowed(token, match, action) is False

    def test_empty_roles_denied_all(self):
        token = make_token([])
        match = make_match(match_date=date.today(), status="SCHEDULED")
        for action in EDIT_ACTIONS:
            assert is_allowed(token, match, action) is False


# ---------------------------------------------------------------------------
# New action enum members exist
# ---------------------------------------------------------------------------


class TestEnumCompleteness:

    def test_access_match_center_in_enum(self):
        assert MatchAction.ACCESS_MATCH_CENTER in MatchAction

    def test_edit_supplementary_in_enum(self):
        assert MatchAction.EDIT_SUPPLEMENTARY in MatchAction

    def test_all_ten_spec_gates_present(self):
        spec_gates = {
            "EDIT_SCHEDULING",
            "EDIT_STATUS_RESULT",
            "EDIT_ROSTER_HOME",
            "EDIT_ROSTER_AWAY",
            "EDIT_SCORES_HOME",
            "EDIT_SCORES_AWAY",
            "EDIT_PENALTIES_HOME",
            "EDIT_PENALTIES_AWAY",
            "ACCESS_MATCH_CENTER",
            "EDIT_SUPPLEMENTARY",
        }
        action_values = {a.value for a in MatchAction}
        assert spec_gates.issubset(action_values)


# ---------------------------------------------------------------------------
# check_permission raises AuthorizationException on denial
# ---------------------------------------------------------------------------


class TestCheckPermission:

    def test_raises_on_denial(self):
        from exceptions import AuthorizationException

        svc = MatchPermissionService(mongodb=None)
        token = make_token(["CLUB_ADMIN"], club_id="some-club")
        match = make_match(match_date=date.today(), status="SCHEDULED")

        with _patch_settings():
            with pytest.raises(AuthorizationException):
                svc.check_permission(token, match, MatchAction.EDIT_SCHEDULING)

    def test_no_exception_on_grant(self):
        from exceptions import AuthorizationException

        svc = MatchPermissionService(mongodb=None)
        token = make_token(["ADMIN"])
        match = make_match(match_date=date.today(), status="SCHEDULED")

        with _patch_settings():
            try:
                svc.check_permission(token, match, MatchAction.EDIT_SCHEDULING)
            except AuthorizationException:
                pytest.fail("AuthorizationException raised unexpectedly for ADMIN")
