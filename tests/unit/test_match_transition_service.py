import pytest
from fastapi import HTTPException

from services.match_transition_service import get_allowed_transitions, validate_match_transition


class TestGetAllowedTransitions:
    def test_admin_gets_all_other_statuses(self):
        allowed = get_allowed_transitions("SCHEDULED", ["ADMIN"])
        assert "INPROGRESS" in allowed
        assert "FINISHED" in allowed
        assert "CANCELLED" in allowed
        assert "FORFEITED" in allowed
        assert "SCHEDULED" not in allowed

    def test_admin_forfeited_gets_all_other_statuses(self):
        allowed = get_allowed_transitions("FORFEITED", ["ADMIN"])
        assert "SCHEDULED" in allowed
        assert "FINISHED" in allowed
        assert "FORFEITED" not in allowed

    def test_league_admin_scheduled(self):
        allowed = get_allowed_transitions("SCHEDULED", ["LEAGUE_ADMIN"])
        assert set(allowed) == {"INPROGRESS", "CANCELLED", "FORFEITED"}

    def test_league_admin_inprogress(self):
        allowed = get_allowed_transitions("INPROGRESS", ["LEAGUE_ADMIN"])
        assert allowed == ["FINISHED"]

    def test_league_admin_finished_can_forfeit(self):
        allowed = get_allowed_transitions("FINISHED", ["LEAGUE_ADMIN"])
        assert allowed == ["FORFEITED"]

    def test_league_admin_forfeited_can_reopen(self):
        allowed = get_allowed_transitions("FORFEITED", ["LEAGUE_ADMIN"])
        assert allowed == ["FINISHED"]

    def test_league_admin_cancelled_no_transitions(self):
        allowed = get_allowed_transitions("CANCELLED", ["LEAGUE_ADMIN"])
        assert allowed == []

    def test_club_admin_scheduled(self):
        allowed = get_allowed_transitions("SCHEDULED", ["CLUB_ADMIN"])
        assert allowed == ["INPROGRESS"]

    def test_club_admin_inprogress(self):
        allowed = get_allowed_transitions("CLUB_ADMIN", ["CLUB_ADMIN"])
        assert allowed == []

    def test_club_admin_finished_no_transitions(self):
        allowed = get_allowed_transitions("FINISHED", ["CLUB_ADMIN"])
        assert allowed == []

    def test_no_roles_returns_empty(self):
        allowed = get_allowed_transitions("SCHEDULED", [])
        assert allowed == []

    def test_league_admin_role_takes_precedence_over_club_admin(self):
        allowed = get_allowed_transitions("FINISHED", ["CLUB_ADMIN", "LEAGUE_ADMIN"])
        assert allowed == ["FORFEITED"]


class TestValidateMatchTransition:
    def test_same_status_always_allowed(self):
        validate_match_transition("SCHEDULED", "SCHEDULED", ["CLUB_ADMIN"])

    def test_admin_unrestricted(self):
        validate_match_transition("CANCELLED", "SCHEDULED", ["ADMIN"])

    def test_league_admin_valid_transition_passes(self):
        validate_match_transition("FINISHED", "FORFEITED", ["LEAGUE_ADMIN"])
        validate_match_transition("FORFEITED", "FINISHED", ["LEAGUE_ADMIN"])
        validate_match_transition("SCHEDULED", "INPROGRESS", ["LEAGUE_ADMIN"])

    def test_club_admin_valid_transition_passes(self):
        validate_match_transition("SCHEDULED", "INPROGRESS", ["CLUB_ADMIN"])
        validate_match_transition("INPROGRESS", "FINISHED", ["CLUB_ADMIN"])

    def test_club_admin_forbidden_transition_raises_403(self):
        with pytest.raises(HTTPException) as exc:
            validate_match_transition("FINISHED", "FORFEITED", ["CLUB_ADMIN"])
        assert exc.value.status_code == 403

    def test_club_admin_inprogress_to_cancelled_raises_400(self):
        with pytest.raises(HTTPException) as exc:
            validate_match_transition("INPROGRESS", "CANCELLED", ["CLUB_ADMIN"])
        assert exc.value.status_code == 400

    def test_invalid_transition_for_all_roles_raises_400(self):
        with pytest.raises(HTTPException) as exc:
            validate_match_transition("CANCELLED", "SCHEDULED", ["LEAGUE_ADMIN"])
        assert exc.value.status_code == 400

    def test_no_roles_raises_403_on_valid_but_unpermitted(self):
        with pytest.raises(HTTPException) as exc:
            validate_match_transition("SCHEDULED", "INPROGRESS", [])
        assert exc.value.status_code == 403
