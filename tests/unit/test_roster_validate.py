"""Unit tests for roster validation helper functions and called player logic"""

from models.matches import CalledFromTeam, EventPlayer, LicenseStatus, RosterPlayer
from models.players import LicenseInvalidReasonCode
from routers.roster import (
    CALLED_MATCH_LIMIT,
    _count_called_matches,
    _extract_status_and_reasons,
    _find_team_in_assigned_teams,
    _validate_called_player,
    _validate_regular_player,
)


def _make_roster_player(
    player_id="player1",
    called=False,
    called_from_team=None,
):
    return RosterPlayer(
        player=EventPlayer(
            playerId=player_id,
            firstName="Test",
            lastName="Player",
            jerseyNumber=10,
        ),
        playerPosition={"pos": "forward"},
        passNumber="PASS001",
        called=called,
        calledFromTeam=called_from_team,
    )


def _make_assigned_teams(teams_data):
    return [
        {
            "clubId": "club1",
            "clubName": "Test Club",
            "teams": teams_data,
        }
    ]


class TestFindTeamInAssignedTeams:

    def test_finds_matching_team(self):
        assigned = _make_assigned_teams(
            [
                {"teamId": "team-a", "status": "VALID"},
                {"teamId": "team-b", "status": "INVALID"},
            ]
        )
        result = _find_team_in_assigned_teams(assigned, "team-a")
        assert result is not None
        assert result["teamId"] == "team-a"

    def test_returns_none_when_not_found(self):
        assigned = _make_assigned_teams(
            [
                {"teamId": "team-a", "status": "VALID"},
            ]
        )
        result = _find_team_in_assigned_teams(assigned, "team-x")
        assert result is None

    def test_searches_across_multiple_clubs(self):
        assigned = [
            {"clubId": "club1", "teams": [{"teamId": "team-a"}]},
            {"clubId": "club2", "teams": [{"teamId": "team-b"}]},
        ]
        result = _find_team_in_assigned_teams(assigned, "team-b")
        assert result is not None
        assert result["teamId"] == "team-b"


class TestExtractStatusAndReasons:

    def test_valid_status_no_reasons(self):
        team = {"status": "VALID", "invalidReasonCodes": []}
        status, codes = _extract_status_and_reasons(team)
        assert status == LicenseStatus.VALID
        assert codes == []

    def test_invalid_status_with_reasons(self):
        team = {
            "status": "INVALID",
            "invalidReasonCodes": ["SUSPENDED", "AGE_GROUP_VIOLATION"],
        }
        status, codes = _extract_status_and_reasons(team)
        assert status == LicenseStatus.INVALID
        assert LicenseInvalidReasonCode.SUSPENDED in codes
        assert LicenseInvalidReasonCode.AGE_GROUP_VIOLATION in codes

    def test_unknown_status_value(self):
        team = {"status": "GARBAGE"}
        status, codes = _extract_status_and_reasons(team)
        assert status == LicenseStatus.UNKNOWN
        assert codes == []

    def test_missing_status_defaults_unknown(self):
        team = {}
        status, codes = _extract_status_and_reasons(team)
        assert status == LicenseStatus.UNKNOWN
        assert codes == []

    def test_enum_values_passed_directly(self):
        team = {
            "status": LicenseStatus.VALID,
            "invalidReasonCodes": [LicenseInvalidReasonCode.SUSPENDED],
        }
        status, codes = _extract_status_and_reasons(team)
        assert status == LicenseStatus.VALID
        assert codes == [LicenseInvalidReasonCode.SUSPENDED]


class TestCountCalledMatches:

    def test_no_trackings(self):
        player = {"playUpTrackings": []}
        assert _count_called_matches(player, "team-higher") == 0

    def test_none_trackings(self):
        player = {"playUpTrackings": None}
        assert _count_called_matches(player, "team-higher") == 0

    def test_missing_trackings(self):
        player = {}
        assert _count_called_matches(player, "team-higher") == 0

    def test_counts_matching_team_occurrences(self):
        player = {
            "playUpTrackings": [
                {
                    "toTeamId": "team-higher",
                    "fromTeamId": "team-lower",
                    "occurrences": [
                        {"matchId": "m1", "counted": True},
                        {"matchId": "m2", "counted": True},
                        {"matchId": "m3", "counted": True},
                    ],
                }
            ]
        }
        assert _count_called_matches(player, "team-higher") == 3

    def test_ignores_different_team(self):
        player = {
            "playUpTrackings": [
                {
                    "toTeamId": "team-other",
                    "fromTeamId": "team-lower",
                    "occurrences": [
                        {"matchId": "m1", "counted": True},
                    ],
                }
            ]
        }
        assert _count_called_matches(player, "team-higher") == 0

    def test_skips_uncounted_occurrences(self):
        player = {
            "playUpTrackings": [
                {
                    "toTeamId": "team-higher",
                    "fromTeamId": "team-lower",
                    "occurrences": [
                        {"matchId": "m1", "counted": True},
                        {"matchId": "m2", "counted": False},
                        {"matchId": "m3", "counted": True},
                    ],
                }
            ]
        }
        assert _count_called_matches(player, "team-higher") == 2

    def test_sums_across_multiple_trackings(self):
        player = {
            "playUpTrackings": [
                {
                    "toTeamId": "team-higher",
                    "fromTeamId": "team-lower-a",
                    "occurrences": [{"matchId": "m1", "counted": True}],
                },
                {
                    "toTeamId": "team-higher",
                    "fromTeamId": "team-lower-b",
                    "occurrences": [
                        {"matchId": "m2", "counted": True},
                        {"matchId": "m3", "counted": True},
                    ],
                },
            ]
        }
        assert _count_called_matches(player, "team-higher") == 3

    def test_exactly_at_limit(self):
        player = {
            "playUpTrackings": [
                {
                    "toTeamId": "team-higher",
                    "fromTeamId": "team-lower",
                    "occurrences": [
                        {"matchId": f"m{i}", "counted": True} for i in range(CALLED_MATCH_LIMIT)
                    ],
                }
            ]
        }
        assert _count_called_matches(player, "team-higher") == CALLED_MATCH_LIMIT


class TestValidateCalledPlayer:

    def test_first_time_called_player_valid(self):
        roster_player = _make_roster_player(
            player_id="p1",
            called=True,
            called_from_team=CalledFromTeam(
                teamId="team-lower", teamName="Lower Team", teamAlias="lower"
            ),
        )
        validated_player = {
            "_id": "p1",
            "assignedTeams": _make_assigned_teams(
                [
                    {
                        "teamId": "team-lower",
                        "status": "VALID",
                        "invalidReasonCodes": [],
                    }
                ]
            ),
            "playUpTrackings": [],
        }

        status, codes = _validate_called_player(validated_player, roster_player, "team-higher", {})
        assert status == LicenseStatus.VALID
        assert codes == []

    def test_called_player_with_4_prior_calls_valid(self):
        roster_player = _make_roster_player(
            player_id="p1",
            called=True,
            called_from_team=CalledFromTeam(
                teamId="team-lower", teamName="Lower Team", teamAlias="lower"
            ),
        )
        validated_player = {
            "_id": "p1",
            "assignedTeams": _make_assigned_teams(
                [
                    {
                        "teamId": "team-lower",
                        "status": "VALID",
                        "invalidReasonCodes": [],
                    }
                ]
            ),
            "playUpTrackings": [
                {
                    "toTeamId": "team-higher",
                    "fromTeamId": "team-lower",
                    "occurrences": [{"matchId": f"m{i}", "counted": True} for i in range(4)],
                }
            ],
        }

        status, codes = _validate_called_player(validated_player, roster_player, "team-higher", {})
        assert status == LicenseStatus.VALID
        assert codes == []

    def test_called_player_with_5_prior_calls_invalid(self):
        roster_player = _make_roster_player(
            player_id="p1",
            called=True,
            called_from_team=CalledFromTeam(
                teamId="team-lower", teamName="Lower Team", teamAlias="lower"
            ),
        )
        validated_player = {
            "_id": "p1",
            "assignedTeams": _make_assigned_teams(
                [
                    {
                        "teamId": "team-lower",
                        "status": "VALID",
                        "invalidReasonCodes": [],
                    }
                ]
            ),
            "playUpTrackings": [
                {
                    "toTeamId": "team-higher",
                    "fromTeamId": "team-lower",
                    "occurrences": [{"matchId": f"m{i}", "counted": True} for i in range(5)],
                }
            ],
        }

        status, codes = _validate_called_player(validated_player, roster_player, "team-higher", {})
        assert status == LicenseStatus.INVALID
        assert codes == [LicenseInvalidReasonCode.CALLED_LIMIT_EXCEEDED]

    def test_called_player_with_6_prior_calls_invalid(self):
        roster_player = _make_roster_player(
            player_id="p1",
            called=True,
            called_from_team=CalledFromTeam(
                teamId="team-lower", teamName="Lower Team", teamAlias="lower"
            ),
        )
        validated_player = {
            "_id": "p1",
            "assignedTeams": _make_assigned_teams(
                [
                    {
                        "teamId": "team-lower",
                        "status": "VALID",
                        "invalidReasonCodes": [],
                    }
                ]
            ),
            "playUpTrackings": [
                {
                    "toTeamId": "team-higher",
                    "fromTeamId": "team-lower",
                    "occurrences": [{"matchId": f"m{i}", "counted": True} for i in range(6)],
                }
            ],
        }

        status, codes = _validate_called_player(validated_player, roster_player, "team-higher", {})
        assert status == LicenseStatus.INVALID
        assert codes == [LicenseInvalidReasonCode.CALLED_LIMIT_EXCEEDED]

    def test_called_player_origin_license_invalid(self):
        roster_player = _make_roster_player(
            player_id="p1",
            called=True,
            called_from_team=CalledFromTeam(
                teamId="team-lower", teamName="Lower Team", teamAlias="lower"
            ),
        )
        validated_player = {
            "_id": "p1",
            "assignedTeams": _make_assigned_teams(
                [
                    {
                        "teamId": "team-lower",
                        "status": "INVALID",
                        "invalidReasonCodes": ["SUSPENDED"],
                    }
                ]
            ),
            "playUpTrackings": [],
        }

        status, codes = _validate_called_player(validated_player, roster_player, "team-higher", {})
        assert status == LicenseStatus.INVALID
        assert LicenseInvalidReasonCode.SUSPENDED in codes

    def test_called_player_no_called_from_team(self):
        roster_player = _make_roster_player(
            player_id="p1",
            called=True,
            called_from_team=None,
        )
        validated_player = {
            "_id": "p1",
            "assignedTeams": _make_assigned_teams(
                [{"teamId": "team-lower", "status": "VALID", "invalidReasonCodes": []}]
            ),
        }

        status, codes = _validate_called_player(validated_player, roster_player, "team-higher", {})
        assert status == LicenseStatus.INVALID
        assert codes == []

    def test_called_player_origin_team_not_in_assigned(self):
        roster_player = _make_roster_player(
            player_id="p1",
            called=True,
            called_from_team=CalledFromTeam(
                teamId="team-nonexistent", teamName="Gone Team", teamAlias="gone"
            ),
        )
        validated_player = {
            "_id": "p1",
            "assignedTeams": _make_assigned_teams(
                [{"teamId": "team-lower", "status": "VALID", "invalidReasonCodes": []}]
            ),
        }

        status, codes = _validate_called_player(validated_player, roster_player, "team-higher", {})
        assert status == LicenseStatus.INVALID
        assert codes == []

    def test_uncounted_occurrences_dont_count_towards_limit(self):
        roster_player = _make_roster_player(
            player_id="p1",
            called=True,
            called_from_team=CalledFromTeam(
                teamId="team-lower", teamName="Lower Team", teamAlias="lower"
            ),
        )
        validated_player = {
            "_id": "p1",
            "assignedTeams": _make_assigned_teams(
                [
                    {
                        "teamId": "team-lower",
                        "status": "VALID",
                        "invalidReasonCodes": [],
                    }
                ]
            ),
            "playUpTrackings": [
                {
                    "toTeamId": "team-higher",
                    "fromTeamId": "team-lower",
                    "occurrences": [
                        {"matchId": "m1", "counted": True},
                        {"matchId": "m2", "counted": True},
                        {"matchId": "m3", "counted": True},
                        {"matchId": "m4", "counted": True},
                        {"matchId": "m5", "counted": False},
                        {"matchId": "m6", "counted": False},
                    ],
                }
            ],
        }

        status, codes = _validate_called_player(validated_player, roster_player, "team-higher", {})
        assert status == LicenseStatus.VALID
        assert codes == []


class TestValidateRegularPlayer:

    def test_valid_player(self):
        validated_player = {
            "assignedTeams": _make_assigned_teams(
                [{"teamId": "team-a", "status": "VALID", "invalidReasonCodes": []}]
            )
        }
        status, codes = _validate_regular_player(validated_player, "p1", "team-a")
        assert status == LicenseStatus.VALID
        assert codes == []

    def test_invalid_player_with_reasons(self):
        validated_player = {
            "assignedTeams": _make_assigned_teams(
                [
                    {
                        "teamId": "team-a",
                        "status": "INVALID",
                        "invalidReasonCodes": ["SUSPENDED"],
                    }
                ]
            )
        }
        status, codes = _validate_regular_player(validated_player, "p1", "team-a")
        assert status == LicenseStatus.INVALID
        assert codes == [LicenseInvalidReasonCode.SUSPENDED]

    def test_player_not_assigned_to_team(self):
        validated_player = {
            "assignedTeams": _make_assigned_teams(
                [{"teamId": "team-other", "status": "VALID", "invalidReasonCodes": []}]
            )
        }
        status, codes = _validate_regular_player(validated_player, "p1", "team-a")
        assert status == LicenseStatus.INVALID
        assert codes == []

    def test_no_team_id(self):
        validated_player = {"assignedTeams": []}
        status, codes = _validate_regular_player(validated_player, "p1", "")
        assert status == LicenseStatus.INVALID
        assert codes == []
