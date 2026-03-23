"""Unit tests for ImportService.import_hobby_players"""

import io
import textwrap
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from bson import ObjectId

CLUB_ID = str(ObjectId())
TEAM_ID = str(ObjectId())
PLAYER_ID = ObjectId()

CSV_HEADER = "Saison;clubAlias;teamAlias;updateMode;firstName;lastName;birthdate"


def _make_service():
    """Return a minimal ImportService with mocked db / session / token."""
    from services.import_service import ImportService

    with patch.object(ImportService, "__init__", lambda self, **kw: None):
        svc = ImportService.__new__(ImportService)

    svc.token = "fake-token"
    svc.headers = {"Authorization": "Bearer fake-token"}
    svc.base_url = "http://localhost:8000"

    # Mock MongoDB db
    svc.db = MagicMock()

    # Mock requests session
    svc.session = MagicMock()

    return svc


def _make_club_doc():
    return {
        "_id": ObjectId(CLUB_ID),
        "name": "Berlin Buffalos",
        "alias": "berlin-buffalos",
        "country": "DE",
        "ishdId": 0,
        "active": True,
        "teams": [],
    }


def _make_team_response():
    return {
        "_id": TEAM_ID,
        "name": "1. Hobby",
        "alias": "1-hobby",
        "fullName": "Berlin Buffalos 1. Hobby",
        "shortName": "Buffalos 1",
        "tinyName": "BUF1",
        "ageGroup": "HERREN",
        "teamNumber": 1,
        "teamType": "HOBBY",
        "ishdId": None,
        "active": True,
        "external": False,
        "teamPartnership": [],
    }


def _make_player_doc(assigned_teams=None):
    return {
        "_id": PLAYER_ID,
        "firstName": "John",
        "lastName": "Doe",
        "displayFirstName": "John",
        "displayLastName": "Doe",
        "birthdate": datetime(1988, 9, 10),
        "source": "BISHL",
        "position": "Skater",
        "sex": "männlich",
        "managedByISHD": False,
        "assignedTeams": assigned_teams or [],
        "suspensions": [],
        "stats": [],
        "playUpTrackings": [],
    }


def _csv(rows: list[str]) -> str:
    return CSV_HEADER + "\n" + "\n".join(rows)


# ---------------------------------------------------------------------------
# ADD tests
# ---------------------------------------------------------------------------


class TestHobbyPlayersAdd:
    def test_add_creates_new_player_and_assigns_team(self, tmp_path):
        svc = _make_service()

        csv_content = _csv(["2026;berlin-buffalos;1-hobby;ADD;John;Doe;10.09.1988"])
        csv_file = tmp_path / "hobby.csv"
        csv_file.write_text(csv_content, encoding="utf-8")

        # No existing player
        svc.db.__getitem__ = MagicMock(return_value=MagicMock())
        players_col = MagicMock()
        players_col.find_one.return_value = None
        players_col.update_one.return_value = MagicMock(matched_count=1, modified_count=1)

        svc.db.__getitem__.side_effect = lambda name: {
            "players": players_col,
        }.get(name, MagicMock())

        svc.db.clubs = MagicMock()
        svc.db.clubs.find_one.return_value = _make_club_doc()

        # Patch get_collection to return players_col
        svc.get_collection = MagicMock(return_value=players_col)

        # API: create player returns 201
        created_id = str(ObjectId())
        create_resp = MagicMock()
        create_resp.status_code = 201
        create_resp.json.return_value = {"_id": created_id}

        # API: fetch team returns 200
        team_resp = MagicMock()
        team_resp.status_code = 200
        team_resp.json.return_value = _make_team_response()

        svc.session.post.return_value = create_resp
        svc.session.get.return_value = team_resp

        # After creation, fetch player from DB
        player_doc_after_create = _make_player_doc()
        player_doc_after_create["_id"] = ObjectId(created_id)

        # find_one: first call returns None (player lookup), second returns new player
        players_col.find_one.side_effect = [None, player_doc_after_create]

        success, message = svc.import_hobby_players(str(csv_file), import_all=True)

        assert success is True
        assert "created" in message
        players_col.update_one.assert_called_once()

    def test_add_existing_player_gets_team_assigned(self, tmp_path):
        svc = _make_service()

        csv_content = _csv(["2026;berlin-buffalos;1-hobby;ADD;John;Doe;10.09.1988"])
        csv_file = tmp_path / "hobby.csv"
        csv_file.write_text(csv_content, encoding="utf-8")

        player_doc = _make_player_doc()
        players_col = MagicMock()
        players_col.find_one.return_value = player_doc
        players_col.update_one.return_value = MagicMock(matched_count=1, modified_count=1)
        svc.get_collection = MagicMock(return_value=players_col)

        svc.db.clubs = MagicMock()
        svc.db.clubs.find_one.return_value = _make_club_doc()

        team_resp = MagicMock()
        team_resp.status_code = 200
        team_resp.json.return_value = _make_team_response()
        svc.session.get.return_value = team_resp

        success, message = svc.import_hobby_players(str(csv_file), import_all=True)

        assert success is True
        players_col.update_one.assert_called_once()

    def test_add_missing_birthdate_records_error(self, tmp_path):
        svc = _make_service()

        csv_content = _csv(["2026;berlin-buffalos;1-hobby;ADD;John;Doe;"])
        csv_file = tmp_path / "hobby.csv"
        csv_file.write_text(csv_content, encoding="utf-8")

        players_col = MagicMock()
        svc.get_collection = MagicMock(return_value=players_col)

        success, message = svc.import_hobby_players(str(csv_file), import_all=True)

        assert success is True
        players_col.update_one.assert_not_called()


# ---------------------------------------------------------------------------
# REMOVE tests
# ---------------------------------------------------------------------------


class TestHobbyPlayersRemove:
    def _make_assigned_teams(self):
        return [
            {
                "clubId": CLUB_ID,
                "clubName": "Berlin Buffalos",
                "clubAlias": "berlin-buffalos",
                "clubIshdId": 0,
                "clubType": "MAIN",
                "teams": [
                    {
                        "teamId": TEAM_ID,
                        "teamName": "1. Hobby",
                        "teamAlias": "1-hobby",
                        "teamAgeGroup": "HERREN",
                        "teamIshdId": "",
                        "teamType": "COMPETITIVE",
                        "source": "BISHL",
                        "active": False,
                        "passNo": "H-LIGA",
                        "licenseType": "UNKNOWN",
                        "status": "UNKNOWN",
                        "invalidReasonCodes": [],
                        "adminOverride": False,
                        "isCallable": True,
                    }
                ],
            }
        ]

    def test_remove_strips_team_from_player(self, tmp_path):
        svc = _make_service()

        csv_content = _csv(["2026;berlin-buffalos;1-hobby;REMOVE;John;Doe;10.09.1988"])
        csv_file = tmp_path / "hobby.csv"
        csv_file.write_text(csv_content, encoding="utf-8")

        player_doc = _make_player_doc(assigned_teams=self._make_assigned_teams())
        players_col = MagicMock()
        players_col.find.return_value = [player_doc]
        players_col.update_one.return_value = MagicMock(matched_count=1, modified_count=1)
        svc.get_collection = MagicMock(return_value=players_col)

        success, message = svc.import_hobby_players(str(csv_file), import_all=True)

        assert success is True
        assert "removed" in message
        players_col.update_one.assert_called_once()
        # The update should set assignedTeams to [] (club dropped since no teams left)
        call_args = players_col.update_one.call_args
        updated_assigned = call_args[0][1]["$set"]["assignedTeams"]
        assert updated_assigned == []

    def test_remove_player_not_found_records_error(self, tmp_path):
        svc = _make_service()

        csv_content = _csv(["2026;berlin-buffalos;1-hobby;REMOVE;Jane;Smith;"])
        csv_file = tmp_path / "hobby.csv"
        csv_file.write_text(csv_content, encoding="utf-8")

        players_col = MagicMock()
        players_col.find.return_value = []
        svc.get_collection = MagicMock(return_value=players_col)

        success, message = svc.import_hobby_players(str(csv_file), import_all=True)

        assert success is True
        players_col.update_one.assert_not_called()


# ---------------------------------------------------------------------------
# MERGE tests
# ---------------------------------------------------------------------------


class TestHobbyPlayersMerge:
    def test_merge_skips_when_already_assigned(self, tmp_path):
        svc = _make_service()

        csv_content = _csv(["2026;berlin-buffalos;1-hobby;MERGE;John;Doe;10.09.1988"])
        csv_file = tmp_path / "hobby.csv"
        csv_file.write_text(csv_content, encoding="utf-8")

        assigned = [
            {
                "clubId": CLUB_ID,
                "clubName": "Berlin Buffalos",
                "clubAlias": "berlin-buffalos",
                "clubIshdId": 0,
                "clubType": "MAIN",
                "teams": [
                    {
                        "teamId": TEAM_ID,
                        "teamName": "1. Hobby",
                        "teamAlias": "1-hobby",
                        "teamAgeGroup": "HERREN",
                        "teamIshdId": "",
                        "teamType": "COMPETITIVE",
                        "source": "BISHL",
                        "active": False,
                        "passNo": "H-LIGA",
                        "licenseType": "UNKNOWN",
                        "status": "UNKNOWN",
                        "invalidReasonCodes": [],
                        "adminOverride": False,
                        "isCallable": True,
                    }
                ],
            }
        ]
        player_doc = _make_player_doc(assigned_teams=assigned)
        players_col = MagicMock()
        players_col.find_one.return_value = player_doc
        svc.get_collection = MagicMock(return_value=players_col)

        svc.db.clubs = MagicMock()
        svc.db.clubs.find_one.return_value = _make_club_doc()

        team_resp = MagicMock()
        team_resp.status_code = 200
        team_resp.json.return_value = _make_team_response()
        svc.session.get.return_value = team_resp

        success, message = svc.import_hobby_players(str(csv_file), import_all=True)

        assert success is True
        assert "skipped" in message
        players_col.update_one.assert_not_called()

    def test_merge_adds_when_not_yet_assigned(self, tmp_path):
        svc = _make_service()

        csv_content = _csv(["2026;berlin-buffalos;1-hobby;MERGE;John;Doe;10.09.1988"])
        csv_file = tmp_path / "hobby.csv"
        csv_file.write_text(csv_content, encoding="utf-8")

        player_doc = _make_player_doc()
        players_col = MagicMock()
        players_col.find_one.return_value = player_doc
        players_col.update_one.return_value = MagicMock(matched_count=1, modified_count=1)
        svc.get_collection = MagicMock(return_value=players_col)

        svc.db.clubs = MagicMock()
        svc.db.clubs.find_one.return_value = _make_club_doc()

        team_resp = MagicMock()
        team_resp.status_code = 200
        team_resp.json.return_value = _make_team_response()
        svc.session.get.return_value = team_resp

        success, message = svc.import_hobby_players(str(csv_file), import_all=True)

        assert success is True
        players_col.update_one.assert_called_once()
