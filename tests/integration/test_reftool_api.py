"""Integration tests for reftool API endpoints"""

from datetime import datetime, timedelta

import pytest
from bson import ObjectId
from httpx import AsyncClient

from authentication import AuthHandler
from tests.fixtures.data_fixtures import create_test_match


def _oid():
    return str(ObjectId())


def make_test_referee(ref_id=None, level="S2", active=True):
    ref_id = ref_id or str(ObjectId())
    return {
        "_id": ref_id,
        "email": f"{ref_id}@test.com",
        "firstName": "Ref",
        "lastName": ref_id[:4],
        "roles": ["REFEREE"],
        "referee": {"level": level, "active": active, "points": 0},
    }


def make_assignment(match_id, ref_id, status="REQUESTED", level="S2", position=None):
    return {
        "_id": str(ObjectId()),
        "matchId": match_id,
        "status": status,
        "position": position,
        "referee": {
            "userId": ref_id,
            "firstName": "Ref",
            "lastName": "Test",
            "clubId": None,
            "clubName": None,
            "logoUrl": None,
            "points": 0,
            "level": level,
        },
        "statusHistory": [],
    }


class TestReftoolMatchesEndpoint:

    @pytest.mark.asyncio
    async def test_get_matches_returns_200_with_correct_shape(self, client: AsyncClient, mongodb, admin_token):
        """GET /reftool/matches returns HTTP 200 with grouped matches and refSummary"""
        match_dt = datetime.now() + timedelta(days=1)
        match = create_test_match()
        match["startDate"] = match_dt
        await mongodb["matches"].insert_one(match)

        start = (datetime.now()).strftime("%Y-%m-%d")
        end = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

        response = await client.get(
            f"/reftool/matches?start_date={start}&end_date={end}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)

    @pytest.mark.asyncio
    async def test_get_matches_ref_summary_counts(self, client: AsyncClient, mongodb, admin_token):
        """GET /reftool/matches refSummary counts are correct"""
        match_dt = datetime.now() + timedelta(days=1)
        match = create_test_match()
        match["startDate"] = match_dt
        await mongodb["matches"].insert_one(match)

        ref = make_test_referee()
        await mongodb["users"].insert_one(ref)

        assignment = make_assignment(match["_id"], ref["_id"], status="REQUESTED")
        await mongodb["assignments"].insert_one(assignment)

        start = datetime.now().strftime("%Y-%m-%d")
        end = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

        response = await client.get(
            f"/reftool/matches?start_date={start}&end_date={end}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        day_groups = data["data"]
        assert len(day_groups) >= 1

        all_matches = [m for group in day_groups for m in group["matches"]]
        target = next((m for m in all_matches if m["_id"] == match["_id"]), None)
        assert target is not None
        assert target["refSummary"]["requestedCount"] == 1

    @pytest.mark.asyncio
    async def test_get_matches_invalid_date_returns_400(self, client: AsyncClient, mongodb, admin_token):
        """GET /reftool/matches with invalid date format returns HTTP 400"""
        response = await client.get(
            "/reftool/matches?start_date=not-a-date&end_date=2026-03-07",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_get_matches_range_exceeds_30_days_returns_400(self, client: AsyncClient, mongodb, admin_token):
        """GET /reftool/matches with range >= 30 days returns HTTP 400"""
        response = await client.get(
            "/reftool/matches?start_date=2026-01-01&end_date=2026-01-31",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_get_matches_unauthorized_returns_403(self, client: AsyncClient, mongodb):
        """GET /reftool/matches without allowed role returns 403"""
        auth = AuthHandler()
        user = {
            "_id": str(ObjectId()),
            "email": "club@test.com",
            "firstName": "Club",
            "lastName": "Admin",
            "roles": ["CLUB_ADMIN"],
        }
        token = auth.encode_token(user)

        response = await client.get(
            "/reftool/matches?start_date=2026-01-01&end_date=2026-01-07",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_get_matches_empty_returns_valid_structure(self, client: AsyncClient, mongodb, admin_token):
        """GET /reftool/matches with no matches returns empty data list"""
        response = await client.get(
            "/reftool/matches?start_date=2020-01-01&end_date=2020-01-07",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"] == []

    @pytest.mark.asyncio
    async def test_get_matches_referee_role_allowed(self, client: AsyncClient, mongodb):
        """GET /reftool/matches with REFEREE role is allowed"""
        auth = AuthHandler()
        referee_user = {
            "_id": str(ObjectId()),
            "email": "referee@test.com",
            "firstName": "John",
            "lastName": "Referee",
            "roles": ["REFEREE"],
        }
        token = auth.encode_token(referee_user)

        response = await client.get(
            "/reftool/matches?start_date=2020-01-01&end_date=2020-01-07",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200


class TestReftoolMatchSidepanelEndpoint:

    @pytest.mark.asyncio
    async def test_get_match_referee_options_returns_200(self, client: AsyncClient, mongodb, admin_token):
        """GET /reftool/matches/{match_id} returns 200 with correct shape"""
        match = create_test_match()
        match["startDate"] = datetime.now() + timedelta(days=1)
        await mongodb["matches"].insert_one(match)

        ref = make_test_referee()
        await mongodb["users"].insert_one(ref)

        assignment = make_assignment(match["_id"], ref["_id"], status="REQUESTED")
        await mongodb["assignments"].insert_one(assignment)

        response = await client.get(
            f"/reftool/matches/{match['_id']}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        result = data["data"]
        assert "assigned" in result
        assert "requested" in result
        assert "available" in result
        assert result["matchId"] == match["_id"]

    @pytest.mark.asyncio
    async def test_get_match_referee_options_unknown_id_returns_404(self, client: AsyncClient, mongodb, admin_token):
        """GET /reftool/matches/{match_id} with unknown ID returns 404"""
        response = await client.get(
            "/reftool/matches/nonexistent-match-id",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_match_referee_options_level_filter(self, client: AsyncClient, mongodb, admin_token):
        """GET /reftool/matches/{match_id} with levelFilter filters available referees"""
        match = create_test_match()
        match["startDate"] = datetime.now() + timedelta(days=1)
        await mongodb["matches"].insert_one(match)

        ref_s2 = make_test_referee(level="S2")
        ref_s1 = make_test_referee(level="S1")
        await mongodb["users"].insert_many([ref_s2, ref_s1])

        response = await client.get(
            f"/reftool/matches/{match['_id']}?levelFilter=S2",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        available = data["data"]["available"]
        assert all(r["level"] == "S2" for r in available)

    @pytest.mark.asyncio
    async def test_get_match_referee_options_unauthorized_returns_403(self, client: AsyncClient, mongodb):
        """GET /reftool/matches/{match_id} without correct role returns 403"""
        auth = AuthHandler()
        user = {
            "_id": str(ObjectId()),
            "email": "club@test.com",
            "firstName": "Club",
            "lastName": "Admin",
            "roles": ["CLUB_ADMIN"],
        }
        token = auth.encode_token(user)

        response = await client.get(
            "/reftool/matches/some-match-id",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_get_match_referee_options_scope_filter(self, client: AsyncClient, mongodb, admin_token):
        """GET /reftool/matches/{match_id} with scope filters available referees by club"""
        match = create_test_match()
        match["startDate"] = datetime.now() + timedelta(days=1)
        await mongodb["matches"].insert_one(match)

        club_id = "test-club-scope"

        ref_in_scope = {
            "_id": _oid(),
            "firstName": "In",
            "lastName": "Scope",
            "roles": ["REFEREE"],
            "referee": {"level": "S2", "active": True, "club": {"clubId": club_id, "clubName": "TestClub"}},
        }
        ref_out_of_scope = {
            "_id": _oid(),
            "firstName": "Out",
            "lastName": "Scope",
            "roles": ["REFEREE"],
            "referee": {"level": "S2", "active": True, "club": {"clubId": "other-club", "clubName": "Other"}},
        }
        await mongodb["users"].insert_many([ref_in_scope, ref_out_of_scope])

        response = await client.get(
            f"/reftool/matches/{match['_id']}?scope={club_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200
        data = response.json()["data"]
        available_ids = [r["userId"] for r in data["available"]]
        assert ref_in_scope["_id"] in available_ids
        assert ref_out_of_scope["_id"] not in available_ids

    @pytest.mark.asyncio
    async def test_get_match_referee_options_assigned_and_available_split(
        self, client: AsyncClient, mongodb, admin_token
    ):
        """Assigned referee appears in 'assigned', unassigned active referee in 'available'"""
        match = create_test_match()
        match["startDate"] = datetime.now() + timedelta(days=1)
        await mongodb["matches"].insert_one(match)

        assigned_ref = make_test_referee()
        available_ref = make_test_referee()
        await mongodb["users"].insert_many([assigned_ref, available_ref])

        assignment = make_assignment(match["_id"], assigned_ref["_id"], status="ASSIGNED", position=1)
        await mongodb["assignments"].insert_one(assignment)

        response = await client.get(
            f"/reftool/matches/{match['_id']}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assigned_ids = [r["userId"] for r in data["assigned"]]
        available_ids = [r["userId"] for r in data["available"]]
        assert assigned_ref["_id"] in assigned_ids
        assert available_ref["_id"] in available_ids


class TestReftoolDayStripEndpoint:

    @pytest.mark.asyncio
    async def test_get_day_strip_returns_200_with_correct_shape(self, client: AsyncClient, mongodb, admin_token):
        """GET /reftool/day-strip returns HTTP 200 with per-day summaries for days with matches"""
        # Insert a match on the first day only
        test_match = create_test_match()
        test_match["startDate"] = datetime(2026, 3, 1, 10, 0)
        test_match["referee1"] = {"userId": "r1"}
        test_match["referee2"] = None
        await mongodb["matches"].insert_one(test_match)

        response = await client.get(
            "/reftool/day-strip?start_date=2026-03-01&days=7",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)
        assert len(data["data"]) == 1  # Only 1 day has matches
        assert data["data"][0]["date"] == "2026-03-01"

    @pytest.mark.asyncio
    async def test_get_day_strip_totals_correct(self, client: AsyncClient, mongodb, admin_token):
        """GET /reftool/day-strip correctly reports fullyAssigned/partiallyAssigned/unassigned"""
        target_date = datetime(2026, 4, 1, 10, 0)

        fully = create_test_match()
        fully["startDate"] = target_date
        fully["referee1"] = {"userId": "r1"}
        fully["referee2"] = {"userId": "r2"}

        partial = create_test_match()
        partial["startDate"] = target_date
        partial["referee1"] = {"userId": "r3"}
        partial["referee2"] = None

        unassigned = create_test_match()
        unassigned["startDate"] = target_date
        unassigned["referee1"] = None
        unassigned["referee2"] = None

        await mongodb["matches"].insert_many([fully, partial, unassigned])

        response = await client.get(
            "/reftool/day-strip?start_date=2026-04-01&days=1",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 1
        day = data[0]
        assert day["date"] == "2026-04-01"
        assert day["totalMatches"] == 3
        assert day["fullyAssigned"] == 1
        assert day["partiallyAssigned"] == 1
        assert day["unassigned"] == 1

    @pytest.mark.asyncio
    async def test_get_day_strip_invalid_date_returns_400(self, client: AsyncClient, mongodb, admin_token):
        """GET /reftool/day-strip with invalid date returns HTTP 400"""
        response = await client.get(
            "/reftool/day-strip?start_date=invalid-date",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_get_day_strip_days_exceeds_max_returns_400(self, client: AsyncClient, mongodb, admin_token):
        """GET /reftool/day-strip with days > 30 returns HTTP 400"""
        response = await client.get(
            "/reftool/day-strip?start_date=2026-03-01&days=31",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_get_day_strip_unauthorized_returns_403(self, client: AsyncClient, mongodb):
        """GET /reftool/day-strip without correct role returns 403"""
        auth = AuthHandler()
        user = {
            "_id": str(ObjectId()),
            "email": "club@test.com",
            "firstName": "Club",
            "lastName": "Admin",
            "roles": ["CLUB_ADMIN"],
        }
        token = auth.encode_token(user)

        response = await client.get(
            "/reftool/day-strip?start_date=2026-03-01",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_get_day_strip_empty_results_valid(self, client: AsyncClient, mongodb, admin_token):
        """GET /reftool/day-strip with no matches returns empty list"""
        response = await client.get(
            "/reftool/day-strip?start_date=2020-01-01&days=3",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 0

    @pytest.mark.asyncio
    async def test_get_day_strip_ref_admin_role_allowed(self, client: AsyncClient, mongodb):
        """GET /reftool/day-strip with REF_ADMIN role is allowed"""
        auth = AuthHandler()
        user = {
            "_id": str(ObjectId()),
            "email": "refadmin@test.com",
            "firstName": "Ref",
            "lastName": "Admin",
            "roles": ["REF_ADMIN"],
        }
        token = auth.encode_token(user)

        response = await client.get(
            "/reftool/day-strip?start_date=2020-01-01&days=3",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
