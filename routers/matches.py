import os
from datetime import datetime, timedelta

import httpx
import isodate
from bson import ObjectId
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response

from authentication import AuthHandler, TokenPayload
from exceptions import (
    AuthorizationException,
    DatabaseOperationException,
    ResourceNotFoundException,
    ValidationException,
)
from logging_config import logger
from models.matches import (
    MatchBase,
    MatchDB,
    MatchListBase,
    MatchStats,
    MatchTeamUpdate,
    MatchUpdate,
)
from models.responses import PaginatedResponse, StandardResponse
from services.pagination import PaginationHelper
from services.stats_service import StatsService
from utils import (
    fetch_ref_points,
    flatten_dict,
    get_sys_ref_tool_token,
    my_jsonable_encoder,
    parse_time_from_seconds,
    parse_time_to_seconds,
    populate_event_player_fields,
)

router = APIRouter()
auth_handler = AuthHandler()
stats_service = None  # Will be initialized with MongoDB instance
BASE_URL = os.environ.get("BE_API_URL")
DEBUG_LEVEL = int(os.environ.get("DEBUG_LEVEL", 0))


# Prepare to convert matchSeconds to seconds for accurate comparison
def convert_times_to_seconds(data):
    for score in data.get("home", {}).get("scores", []) or []:
        score["matchSeconds"] = parse_time_to_seconds(score["matchTime"])
    for score in data.get("away", {}).get("scores", []) or []:
        score["matchSeconds"] = parse_time_to_seconds(score["matchTime"])
    for penalty in data.get("home", {}).get("penalties", []) or []:
        penalty["matchSecondsStart"] = parse_time_to_seconds(penalty["matchTimeStart"])
        if penalty.get("matchTimeEnd") is not None:
            penalty["matchSecondsEnd"] = parse_time_to_seconds(penalty["matchTimeEnd"])
    for penalty in data.get("away", {}).get("penalties", []) or []:
        penalty["matchSecondsStart"] = parse_time_to_seconds(penalty["matchTimeStart"])
        if penalty.get("matchTimeEnd") is not None:
            penalty["matchSecondsEnd"] = parse_time_to_seconds(penalty["matchTimeEnd"])
    return data


def convert_seconds_to_times(data):
    for score in data.get("home", {}).get("scores") or []:
        if score is not None:
            score["matchTime"] = parse_time_from_seconds(score["matchSeconds"])
    for score in data.get("away", {}).get("scores") or []:
        if score is not None:
            score["matchTime"] = parse_time_from_seconds(score["matchSeconds"])
    # parse penalties.matchSeconds[Start|End] to a string format
    for penalty in data.get("home", {}).get("penalties") or []:
        if penalty is not None:
            penalty["matchTimeStart"] = parse_time_from_seconds(penalty["matchSecondsStart"])
            if penalty.get("matchSecondsEnd") is not None:
                penalty["matchTimeEnd"] = parse_time_from_seconds(penalty["matchSecondsEnd"])
    for penalty in data.get("away", {}).get("penalties") or []:
        if penalty is not None:
            penalty["matchTimeStart"] = parse_time_to_seconds(penalty["matchSecondsStart"])
            if penalty.get("matchSecondsEnd") is not None:
                penalty["matchTimeEnd"] = parse_time_from_seconds(penalty["matchSecondsEnd"])
    if DEBUG_LEVEL > 100:
        print("data", data)
    return data


async def get_match_object(mongodb, match_id: str) -> MatchDB:
    match = await mongodb["matches"].find_one({"_id": match_id})
    if not match:
        raise ResourceNotFoundException(resource_type="Match", resource_id=match_id)

    # Populate EventPlayer display fields for scores and penalties
    for team_key in ["home", "away"]:
        team = match.get(team_key, {})

        # Populate roster player fields
        roster = team.get("roster", [])
        for roster_entry in roster:
            if roster_entry.get("player"):
                await populate_event_player_fields(mongodb, roster_entry["player"])

        # Populate score player fields
        scores = team.get("scores", [])
        for score in scores:
            if score.get("goalPlayer"):
                await populate_event_player_fields(mongodb, score["goalPlayer"])
            if score.get("assistPlayer"):
                await populate_event_player_fields(mongodb, score["assistPlayer"])

        # Populate penalty player fields
        penalties = team.get("penalties", [])
        for penalty in penalties:
            if penalty.get("penaltyPlayer"):
                await populate_event_player_fields(mongodb, penalty["penaltyPlayer"])

    # parse scores.matchSeconds to a string format
    match = convert_seconds_to_times(match)
    return MatchDB(**match)


async def update_round_and_matchday(client, headers, t_alias, s_alias, r_alias, round_id, md_id):
    if DEBUG_LEVEL > 0:
        print(f"Updating round {r_alias} and matchday {md_id} for {t_alias} / {s_alias}")

    # Update round dates first
    round_response = await client.patch(
        f"{BASE_URL}/tournaments/{t_alias}/seasons/{s_alias}/rounds/{round_id}",
        json={},
        headers=headers,
        timeout=30.0,
    )
    if round_response.status_code not in [200, 304]:
        print(f"WARNING: Failed to update round dates: {round_response.status_code}")
        return

    # After successful round update, update matchday
    matchday_response = await client.patch(
        f"{BASE_URL}/tournaments/{t_alias}/seasons/{s_alias}/rounds/{r_alias}/matchdays/{md_id}",
        json={},
        headers=headers,
        timeout=30.0,
    )
    if matchday_response.status_code not in [200, 304]:
        print(f"WARNING: Failed to update matchday dates: {matchday_response.status_code}")


# get today's matches
@router.get(
    "/today", response_model=list[MatchListBase], response_description="Get today's matches"
)
async def get_todays_matches(
    request: Request,
    tournament: str | None = None,
    season: str | None = None,
    round: str | None = None,
    matchday: str | None = None,
    referee: str | None = None,
    club: str | None = None,
    team: str | None = None,
    assigned: bool | None = None,
) -> JSONResponse:
    mongodb = request.app.state.mongodb

    # Get today's date range
    today = datetime.now().date()
    start_of_day = datetime.combine(today, datetime.min.time())
    end_of_day = datetime.combine(today, datetime.max.time())

    query = {
        "season.alias": season if season else os.environ["CURRENT_SEASON"],
        "startDate": {"$gte": start_of_day, "$lte": end_of_day},
    }

    if tournament:
        query["tournament.alias"] = tournament
    if round:
        query["round.alias"] = round
    if matchday:
        query["matchday.alias"] = matchday
    if referee:
        query["$or"] = [{"referee1.userId": referee}, {"referee2.userId": referee}]
    if club:
        if team:
            query["$or"] = [
                {"$and": [{"home.clubAlias": club}, {"home.teamAlias": team}]},
                {"$and": [{"away.clubAlias": club}, {"away.teamAlias": team}]},
            ]
        else:
            query["$or"] = [{"home.clubAlias": club}, {"away.clubAlias": club}]
    if assigned is not None:
        if not assigned:  # assigned == False
            query["$and"] = [
                {"referee1.userId": {"$exists": False}},
                {"referee2.userId": {"$exists": False}},
            ]
        elif assigned:  # assigned == True
            query["$or"] = [
                {"referee1.userId": {"$exists": True}},
                {"referee2.userId": {"$exists": True}},
            ]

    if DEBUG_LEVEL > 20:
        print("today's matches query: ", query)

    # Project only necessary fields, excluding roster, scores, and penalties
    projection = {
        "home.roster": 0,
        "home.scores": 0,
        "home.penalties": 0,
        "away.roster": 0,
        "away.scores": 0,
        "away.penalties": 0,
    }

    matches = await mongodb["matches"].find(query, projection).sort("startDate", 1).to_list(None)

    # Convert to MatchListBase objects and parse time fields
    results = []
    for match in matches:
        match = convert_seconds_to_times(match)
        results.append(MatchListBase(**match))

    return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(results))


# get upcoming matches (next day with matches)
@router.get(
    "/upcoming",
    response_model=list[MatchListBase],
    response_description="Get upcoming matches for next day where matches exist",
)
async def get_upcoming_matches(
    request: Request,
    tournament: str | None = None,
    season: str | None = None,
    round: str | None = None,
    matchday: str | None = None,
    referee: str | None = None,
    club: str | None = None,
    team: str | None = None,
    assigned: bool | None = None,
) -> JSONResponse:
    mongodb = request.app.state.mongodb

    # Get current time and start searching from tomorrow
    today = datetime.now()
    tomorrow_start = datetime.combine(today.date() + timedelta(days=1), datetime.min.time())

    # Build base query to find minimum start date
    base_query = {
        "season.alias": season if season else os.environ["CURRENT_SEASON"],
        "startDate": {"$gte": tomorrow_start},
    }

    if tournament:
        base_query["tournament.alias"] = tournament
    if round:
        base_query["round.alias"] = round
    if matchday:
        base_query["matchday.alias"] = matchday
    if referee:
        base_query["$or"] = [{"referee1.userId": referee}, {"referee2.userId": referee}]
    if club:
        if team:
            base_query["$or"] = [
                {"$and": [{"home.clubAlias": club}, {"home.teamAlias": team}]},
                {"$and": [{"away.clubAlias": club}, {"away.teamAlias": team}]},
            ]
        else:
            base_query["$or"] = [{"home.clubAlias": club}, {"away.clubAlias": club}]
    if assigned is not None:
        if not assigned:  # assigned == False
            base_query["$and"] = [
                {"referee1.userId": {"$exists": False}},
                {"referee2.userId": {"$exists": False}},
            ]
        elif assigned:  # assigned == True
            base_query["$or"] = [
                {"referee1.userId": {"$exists": True}},
                {"referee2.userId": {"$exists": True}},
            ]

    if DEBUG_LEVEL > 20:
        print("upcoming matches base query: ", base_query)

    # Find the minimum start date for upcoming matches
    min_date_result = (
        await mongodb["matches"].find(base_query).sort("startDate", 1).limit(1).to_list(1)
    )

    if not min_date_result:
        # No upcoming matches found
        return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder([]))

    min_start_date = min_date_result[0]["startDate"]
    match_date = min_start_date.date()

    # Create date range for the found date
    start_of_day = datetime.combine(match_date, datetime.min.time())
    end_of_day = datetime.combine(match_date, datetime.max.time())

    # Build final query for matches on the found date
    final_query = base_query.copy()
    final_query["startDate"] = {"$gte": start_of_day, "$lte": end_of_day}

    if DEBUG_LEVEL > 20:
        print(f"upcoming matches final query for {match_date}: ", final_query)

    # Project only necessary fields, excluding roster, scores, and penalties
    projection = {
        "home.roster": 0,
        "home.scores": 0,
        "home.penalties": 0,
        "away.roster": 0,
        "away.scores": 0,
        "away.penalties": 0,
    }

    matches = (
        await mongodb["matches"].find(final_query, projection).sort("startDate", 1).to_list(None)
    )

    # Convert to MatchListBase objects and parse time fields
    results = []
    for match in matches:
        match = convert_seconds_to_times(match)
        results.append(MatchListBase(**match))

    return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(results))


# get this week's matches (tomorrow until Sunday)
@router.get(
    "/rest-of-week",
    response_description="Get matches for rest of current week (tomorrow until Sunday)",
)
async def get_rest_of_week_matches(
    request: Request,
    tournament: str | None = None,
    season: str | None = None,
    round: str | None = None,
    matchday: str | None = None,
    referee: str | None = None,
    club: str | None = None,
    team: str | None = None,
    assigned: bool | None = None,
) -> JSONResponse:
    mongodb = request.app.state.mongodb

    # Get current date and calculate tomorrow and end of week (Sunday)
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)

    # Calculate days until Sunday (0=Monday, 6=Sunday)
    days_until_sunday = 6 - today.weekday()
    if days_until_sunday <= 0:  # If today is Sunday, get next Sunday
        days_until_sunday = 7

    end_of_week = today + timedelta(days=days_until_sunday)

    # Build base query
    base_query = {"season.alias": season if season else os.environ["CURRENT_SEASON"]}

    if tournament:
        base_query["tournament.alias"] = tournament
    if round:
        base_query["round.alias"] = round
    if matchday:
        base_query["matchday.alias"] = matchday
    if referee:
        base_query["$or"] = [{"referee1.userId": referee}, {"referee2.userId": referee}]
    if club:
        if team:
            base_query["$or"] = [
                {"$and": [{"home.clubAlias": club}, {"home.teamAlias": team}]},
                {"$and": [{"away.clubAlias": club}, {"away.teamAlias": team}]},
            ]
        else:
            base_query["$or"] = [{"home.clubAlias": club}, {"away.clubAlias": club}]
    if assigned is not None:
        if not assigned:  # assigned == False
            base_query["$and"] = [
                {"referee1.userId": {"$exists": False}},
                {"referee2.userId": {"$exists": False}},
            ]
        elif assigned:  # assigned == True
            base_query["$or"] = [
                {"referee1.userId": {"$exists": True}},
                {"referee2.userId": {"$exists": True}},
            ]

    if DEBUG_LEVEL > 20:
        print("this week matches base query: ", base_query)

    # Initialize result structure
    week_matches = []

    # Loop through each day from tomorrow until Sunday
    current_date = tomorrow
    while current_date <= end_of_week:
        start_of_day = datetime.combine(current_date, datetime.min.time())
        end_of_day = datetime.combine(current_date, datetime.max.time())

        # Build query for this specific day
        day_query = base_query.copy()
        day_query["startDate"] = {"$gte": start_of_day, "$lte": end_of_day}

        if DEBUG_LEVEL > 20:
            print(f"this week matches query for {current_date}: ", day_query)

        # Project only necessary fields, excluding roster, scores, and penalties
        projection = {
            "home.roster": 0,
            "home.scores": 0,
            "home.penalties": 0,
            "away.roster": 0,
            "away.scores": 0,
            "away.penalties": 0,
        }

        matches = (
            await mongodb["matches"].find(day_query, projection).sort("startDate", 1).to_list(None)
        )

        # Convert to MatchListBase objects and parse time fields
        day_matches = []
        for match in matches:
            match = convert_seconds_to_times(match)
            day_matches.append(MatchListBase(**match))

        # Add day data to result
        week_matches.append(
            {
                "date": current_date.isoformat(),
                "dayName": current_date.strftime("%A"),
                "matches": day_matches,
            }
        )

        # Move to next day
        current_date += timedelta(days=1)

    return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(week_matches))


# get matches
@router.get("", response_model=PaginatedResponse[MatchDB])
async def get_matches(
    request: Request,
    tournament: str | None = None,
    season: str | None = None,
    round: str | None = None,
    matchday: str | None = None,
    status_key: str | None = None,
    referee: str | None = None,
    club: str | None = None,
    team: str | None = None,
    assigned: bool | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    token_payload: TokenPayload = Depends(auth_handler.auth_wrapper),
) -> JSONResponse:
    query = {"season.alias": season if season else os.environ["CURRENT_SEASON"]}
    if tournament:
        query["tournament.alias"] = tournament
    if round:
        query["round.alias"] = round
    if matchday:
        query["matchday.alias"] = matchday
    if status_key:
        query["matchStatus.key"] = status_key
    if referee:
        query["$or"] = [{"referee1.userId": referee}, {"referee2.userId": referee}]
    if club:
        if team:
            query["$or"] = [
                {"$and": [{"home.clubAlias": club}, {"home.teamAlias": team}]},
                {"$and": [{"away.clubAlias": club}, {"away.teamAlias": team}]},
            ]
        else:
            query["$or"] = [{"home.clubAlias": club}, {"away.clubAlias": club}]
    if assigned is not None:
        if not assigned:  # assigned == False
            query["$and"] = [
                {"referee1.userId": {"$exists": False}},
                {"referee2.userId": {"$exists": False}},
            ]
        elif assigned:  # assigned == True
            query["$or"] = [
                {"referee1.userId": {"$exists": True}},
                {"referee2.userId": {"$exists": True}},
            ]

    if date_from or date_to:
        date_query = {}
        try:
            if date_from:
                parsed_date_from = isodate.parse_date(date_from)
                date_query["$gte"] = datetime.combine(parsed_date_from, datetime.min.time())
            if date_to:
                parsed_date_to = isodate.parse_date(date_to)
                date_query["$lte"] = datetime.combine(parsed_date_to, datetime.max.time())
            query["startDate"] = date_query
        except Exception as e:
            raise ValidationException(
                field="date_from/date_to",
                message=str(e),
                details={"date_from": date_from, "date_to": date_to},
            ) from e
    if DEBUG_LEVEL > 20:
        print("query: ", query)

    # Use pagination helper
    items, total_count = await PaginationHelper.paginate_query(
        collection=request.app.state.mongodb["matches"],
        query=query,
        page=page,
        page_size=page_size,
        sort=[("startDate", 1)],
    )

    # Convert to MatchListBase objects and parse time fields
    results = []
    for match in items:
        match = convert_seconds_to_times(match)
        results.append(MatchListBase(**match))

    return PaginationHelper.create_response(
        items=results,
        page=page,
        page_size=page_size,
        total_count=total_count,
        message=f"Retrieved {len(results)} matches",
    )


# get one match by id
@router.get("/{match_id}", response_model=StandardResponse[MatchDB])
async def get_match(
    match_id: str,
    request: Request,
    token_payload: TokenPayload = Depends(auth_handler.auth_wrapper),
):
    mongodb = request.app.state.mongodb
    match = await get_match_object(mongodb, match_id)
    # get_match_object already raises ResourceNotFoundException if not found
    return StandardResponse(success=True, data=match, message="Match retrieved successfully")


# create new match
@router.post("/", response_description="Add new match", response_model=MatchDB)
async def create_match(
    request: Request,
    match: MatchBase = Body(...),
    token_payload: TokenPayload = Depends(auth_handler.auth_wrapper),
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    if "ADMIN" not in token_payload.roles:
        raise AuthorizationException(
            message="Admin role required to create matches",
            details={"user_roles": token_payload.roles, "required_role": "ADMIN"},
        )

    logger.info(
        "Creating match",
        extra={
            "tournament": match.tournament.alias if match.tournament else None,
            "season": match.season.alias if match.season else None,
            "user": token_payload.sub,
        },
    )

    try:
        # get standingsSettings and set points per team
        if (
            match.tournament is not None
            and match.season is not None
            and match.home is not None
            and match.away is not None
            and hasattr(match.tournament, "alias")
            and hasattr(match.season, "alias")
        ):
            if DEBUG_LEVEL > 10:
                print("get standingsSettings")
            # fetch standing settings
            stats_service = StatsService(mongodb)
            standings_settings = await stats_service.get_standings_settings(
                match.tournament.alias, match.season.alias
            )
            if DEBUG_LEVEL > 10:
                print(standings_settings)
            home_score = (
                0
                if match.home is None or not match.home.stats or match.home.stats.goalsFor is None
                else match.home.stats.goalsFor
            )
            away_score = (
                0
                if match.away is None or not match.away.stats or match.away.stats.goalsFor is None
                else match.away.stats.goalsFor
            )

            match_stats = stats_service.calculate_match_stats(
                match.matchStatus.key,
                match.finishType.key,
                standings_settings,
                home_score=home_score,
                away_score=away_score,
            )
            if DEBUG_LEVEL > 20:
                print("stats: ", match_stats)

            # Now safely assign the stats
            match.home.stats = MatchStats(**match_stats["home"])
            match.away.stats = MatchStats(**match_stats["away"])

        t_alias = match.tournament.alias if match.tournament is not None else None
        s_alias = match.season.alias if match.season is not None else None
        r_alias = match.round.alias if match.round is not None else None
        md_alias = match.matchday.alias if match.matchday is not None else None

        if t_alias and s_alias and r_alias and md_alias:
            try:
                ref_points = await fetch_ref_points(
                    t_alias=t_alias, s_alias=s_alias, r_alias=r_alias, md_alias=md_alias
                )
                if DEBUG_LEVEL > 20:
                    print("ref_points: ", ref_points)
                if match.matchStatus.key in ["FINISHED", "FORFEITED"]:
                    if match.referee1 is not None:
                        match.referee1.points = ref_points
                    if match.referee2 is not None:
                        match.referee2.points = ref_points
            except HTTPException as e:
                if e.status_code == 404:
                    raise ResourceNotFoundException(
                        resource_type="Matchday",
                        resource_id=md_alias,
                        details={"tournament": t_alias, "season": s_alias, "round": r_alias},
                    ) from e
                raise e

        if DEBUG_LEVEL > 20:
            print("xxx match", match)
        match_data = my_jsonable_encoder(match)
        match_data = convert_times_to_seconds(match_data)

        # convert startDate to the required datetime format
        if "startDate" in match_data and match_data["startDate"] is not None:
            start_date_str = match_data["startDate"]
            print(start_date_str)
            try:
                start_date_parts = datetime.fromisoformat(str(start_date_str))
                if DEBUG_LEVEL > 100:
                    print(start_date_parts)
                match_data["startDate"] = datetime(
                    start_date_parts.year,
                    start_date_parts.month,
                    start_date_parts.day,
                    start_date_parts.hour,
                    start_date_parts.minute,
                    start_date_parts.second,
                    start_date_parts.microsecond,
                    tzinfo=start_date_parts.tzinfo,
                )
            except ValueError as e:
                raise ValidationException(
                    field="startDate", message=str(e), details={"value": start_date_str}
                ) from e

        if DEBUG_LEVEL > 0:
            print("xxx match_data: ", match_data)

        # add match to collection matches
        try:
            result = await mongodb["matches"].insert_one(match_data)
        except Exception as e:
            raise DatabaseOperationException(
                operation="insert_one", collection="matches", details={"error": str(e)}
            ) from e

        logger.info(
            "Match created successfully",
            extra={"match_id": result.inserted_id, "tournament": t_alias, "season": s_alias},
        )

        # Update rounds and matchdays dates, and calc standings
        if t_alias and s_alias and r_alias and md_alias:
            token = await get_sys_ref_tool_token(
                email=os.environ["SYS_ADMIN_EMAIL"], password=os.environ["SYS_ADMIN_PASSWORD"]
            )
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            tournament = await mongodb["tournaments"].find_one({"alias": t_alias})
            if tournament:
                season = next(
                    (s for s in tournament.get("seasons", []) if s.get("alias") == s_alias), None
                )
                if season:
                    round_data = next(
                        (r for r in season.get("rounds", []) if r.get("alias") == r_alias), None
                    )
                    if round_data and "_id" in round_data:
                        round_id = round_data["_id"]
                        matchday_data = next(
                            (
                                md
                                for md in round_data.get("matchdays", [])
                                if md.get("alias") == md_alias
                            ),
                            None,
                        )
                        if matchday_data and "_id" in matchday_data:
                            md_id = matchday_data["_id"]
                            async with httpx.AsyncClient() as client:
                                await update_round_and_matchday(
                                    client, headers, t_alias, s_alias, r_alias, round_id, md_id
                                )
                        else:
                            print(f"Warning: Matchday {md_alias} not found or has no ID")
                    else:
                        print(f"Warning: Round {r_alias} not found or has no ID")

        if DEBUG_LEVEL > 0:
            print("calc_roster_stats (home) ...")
        stats_service = StatsService(mongodb)
        await stats_service.calculate_roster_stats(result.inserted_id, "home")
        if DEBUG_LEVEL > 0:
            print("calc_roster_stats (away) ...")
        await stats_service.calculate_roster_stats(result.inserted_id, "away")

        # PHASE 1 OPTIMIZATION: Skip player card stats calculation during match creation
        # Player stats will be calculated when match status changes to FINISHED
        if DEBUG_LEVEL > 0:
            print("Match created - player card stats will be calculated when match finishes")

        # return complete match document
        new_match = await get_match_object(mongodb, result.inserted_id)
        return JSONResponse(
            status_code=status.HTTP_201_CREATED, content=jsonable_encoder(new_match)
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# ------ update match
@router.patch("/{match_id}", response_description="Update match", response_model=MatchDB)
async def update_match(
    request: Request,
    match_id: str,
    match: MatchUpdate = Body(...),
    token_payload: TokenPayload = Depends(auth_handler.auth_wrapper),
):
    mongodb = request.app.state.mongodb
    if not any(role in token_payload.roles for role in ["ADMIN", "LEAGUE_ADMIN", "CLUB_ADMIN"]):
        raise AuthorizationException(
            message="Admin, League Admin, or Club Admin role required",
            details={
                "user_roles": token_payload.roles,
                "required_roles": ["ADMIN", "LEAGUE_ADMIN", "CLUB_ADMIN"],
            },
        )

    # Helper function to add _id to new nested documents and clean up ObjectId id fields
    def add_id_to_scores_and_penalties(items):
        for item in items:
            if "_id" not in item:
                item["_id"] = str(ObjectId())
            # Remove ObjectId id field if it exists
            if "id" in item and isinstance(item["id"], ObjectId):
                item.pop("id")

    # Get existing match
    existing_match = await mongodb["matches"].find_one({"_id": match_id})
    if existing_match is None:
        raise ResourceNotFoundException(resource_type="Match", resource_id=match_id)

    # Extract tournament info for potential use
    t_alias = getattr(
        match.tournament, "alias", existing_match.get("tournament", {}).get("alias", None)
    )
    s_alias = getattr(match.season, "alias", existing_match.get("season", {}).get("alias", None))
    r_alias = getattr(match.round, "alias", existing_match.get("round", {}).get("alias", None))
    md_alias = getattr(
        match.matchday, "alias", existing_match.get("matchday", {}).get("alias", None)
    )

    # Get current and new match status/finish type
    current_match_status = existing_match.get("matchStatus", {}).get("key", None)
    new_match_status = getattr(match.matchStatus, "key", current_match_status)
    current_finish_type = existing_match.get("finishType", {}).get("key", None)
    new_finish_type = getattr(match.finishType, "key", current_finish_type)

    if DEBUG_LEVEL > 10:
        print("passed match: ", match)
    # Check if this is a stats-affecting change - only check fields that were explicitly provided
    match_data_provided = match.model_dump(exclude_unset=True)
    stats_affecting_fields = ["matchStatus", "finishType", "home.stats", "away.stats"]
    stats_change_detected = any(
        field in match_data_provided
        or (
            field.count(".") == 1
            and field.split(".")[0] in match_data_provided
            and field.split(".")[1] in match_data_provided.get(field.split(".")[0], {})
        )
        for field in stats_affecting_fields
    )
    if DEBUG_LEVEL > 10:
        print("stats_change_detected: ", stats_change_detected)

    # Only calculate match stats if stats-affecting fields changed
    if stats_change_detected and new_finish_type and t_alias:
        home_stats_data = (
            match.home.stats
            if (match.home and match.home.stats and match.home.stats != {})
            else existing_match.get("home", {}).get("stats", {})
        )
        away_stats_data = (
            match.away.stats
            if (match.away and match.away.stats and match.away.stats != {})
            else existing_match.get("away", {}).get("stats", {})
        )

        home_stats = (
            home_stats_data
            if isinstance(home_stats_data, MatchStats)
            else MatchStats(**(home_stats_data or {}))
        )
        away_stats = (
            away_stats_data
            if isinstance(away_stats_data, MatchStats)
            else MatchStats(**(away_stats_data or {}))
        )

        home_goals = (
            home_stats.goalsFor
            if (home_stats and home_stats.goalsFor is not None)
            else existing_match["home"]["stats"]["goalsFor"]
        )
        away_goals = (
            away_stats.goalsFor
            if (away_stats and away_stats.goalsFor is not None)
            else existing_match["away"]["stats"]["goalsFor"]
        )

        # fetch standing settings
        stats_service = StatsService(mongodb)
        standings_settings = await stats_service.get_standings_settings(t_alias, s_alias)

        match_stats = stats_service.calculate_match_stats(
            new_match_status,
            new_finish_type,
            standings_settings,
            home_score=home_goals,
            away_score=away_goals,
        )
        if getattr(match, "home", None) is None:
            match.home = MatchTeamUpdate()
        if getattr(match, "away", None) is None:
            match.away = MatchTeamUpdate()

        if match.home and match.away and match_stats is not None:
            match.home.stats = MatchStats(**match_stats["home"])
            match.away.stats = MatchStats(**match_stats["away"])
        else:
            raise ValueError("Calculating match statistics returned None")

    match_data = match.model_dump(exclude_unset=True)
    match_data.pop("id", None)

    # Only update referee points if match status changed to FINISHED/FORFEITED
    if new_match_status in ["FINISHED", "FORFEITED"] and current_match_status != new_match_status:
        if t_alias and s_alias and r_alias and md_alias:
            ref_points = await fetch_ref_points(t_alias, s_alias, r_alias, md_alias)
            if existing_match["referee1"] is not None:
                match_data["referee1"]["points"] = ref_points
            if existing_match["referee2"] is not None:
                match_data["referee2"]["points"] = ref_points

    if DEBUG_LEVEL > 10:
        print("match_data: ", match_data)
    match_data = convert_times_to_seconds(match_data)

    if match_data.get("home") and match_data["home"].get("scores"):
        add_id_to_scores_and_penalties(match_data["home"]["scores"])
    if match_data.get("away") and match_data["away"].get("scores"):
        add_id_to_scores_and_penalties(match_data["away"]["scores"])
    if match_data.get("home") and match_data["home"].get("penalties"):
        add_id_to_scores_and_penalties(match_data["home"]["penalties"])
    if match_data.get("away") and match_data["away"].get("penalties"):
        add_id_to_scores_and_penalties(match_data["away"]["penalties"])

    def check_nested_fields(data, existing, path=""):
        for key, value in data.items():
            full_key = f"{path}.{key}" if path else key

            if existing is None or key not in existing:
                match_to_update[full_key] = value
            elif isinstance(value, dict):
                check_nested_fields(value, existing.get(key, {}), full_key)
            else:
                if value != existing.get(key):
                    match_to_update[full_key] = value

    match_to_update = {}
    check_nested_fields(match_data, existing_match)
    if DEBUG_LEVEL > 10:
        print("match_to_update: ", match_to_update)

    if not match_to_update:
        if DEBUG_LEVEL > 0:
            print("PATCH/match: No changes to update")
        return Response(status_code=status.HTTP_304_NOT_MODIFIED)

    # Check if this is a date-affecting change that requires round/matchday updates
    date_affecting_fields = ["startDate"]
    date_change_detected = any(field in match_to_update for field in date_affecting_fields)

    try:
        set_data = {"$set": flatten_dict(match_to_update)}
        update_result = await mongodb["matches"].update_one({"_id": match_id}, set_data)

        if update_result.modified_count == 0:
            raise ResourceNotFoundException(resource_type="Match", resource_id=match_id)

        logger.info(
            "Match updated",
            extra={
                "match_id": match_id,
                "stats_change": stats_change_detected,
                "date_change": date_change_detected,
                "user": token_payload.sub,
            },
        )

        # Only update round/matchday dates if date-affecting fields changed
        if date_change_detected and t_alias and s_alias and r_alias and md_alias:
            token = await get_sys_ref_tool_token(
                email=os.environ["SYS_ADMIN_EMAIL"], password=os.environ["SYS_ADMIN_PASSWORD"]
            )
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            tournament = await mongodb["tournaments"].find_one({"alias": t_alias})
            if tournament:
                season = next(
                    (s for s in tournament.get("seasons", []) if s.get("alias") == s_alias), None
                )
                if season:
                    round_data = next(
                        (r for r in season.get("rounds", []) if r.get("alias") == r_alias), None
                    )
                    if round_data and "_id" in round_data:
                        round_id = round_data["_id"]
                        matchday_data = next(
                            (
                                md
                                for md in round_data.get("matchdays", [])
                                if md.get("alias") == md_alias
                            ),
                            None,
                        )
                        if matchday_data and "_id" in matchday_data:
                            md_id = matchday_data["_id"]
                            async with httpx.AsyncClient() as client:
                                await update_round_and_matchday(
                                    client, headers, t_alias, s_alias, r_alias, round_id, md_id
                                )
                        else:
                            print(f"WARNING: Matchday {md_alias} not found or has no ID")
                    else:
                        print(f"WARNING: Round {r_alias} not found or has no ID")

        # Only recalculate roster stats if scores or penalties changed (not for roster-only changes)
        stats_recalc_fields = ["home.scores", "away.scores", "home.penalties", "away.penalties"]
        stats_recalc_needed = any(field in match_to_update for field in stats_recalc_fields)

        if stats_recalc_needed:
            # Recalculate roster stats since goals/assists/penalties changed
            stats_service = StatsService(mongodb)
            await stats_service.calculate_roster_stats(match_id, "home")
            await stats_service.calculate_roster_stats(match_id, "away")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    updated_match = await get_match_object(mongodb, match_id)

    # PHASE 1 OPTIMIZATION: Skip player card stats calculation during match creation
    # Player stats will be calculated when match status changes to FINISHED
    if (
        stats_change_detected
        and "FINISHED" in {new_match_status, current_match_status}
        and t_alias
        and s_alias
        and r_alias
        and md_alias
    ):
        home_players = [
            player.get("player", {}).get("playerId")
            for player in existing_match.get("home", {}).get("roster", [])
            if player.get("player", {}).get("playerId")
        ]
        away_players = [
            player.get("player", {}).get("playerId")
            for player in existing_match.get("away", {}).get("roster", [])
            if player.get("player", {}).get("playerId")
        ]
        player_ids = home_players + away_players
        if player_ids and DEBUG_LEVEL > 0:
            print(
                f"Stats change detected on finished match - calculating player card stats for {len(player_ids)} players..."
            )
        if player_ids:
            stats_service = StatsService(mongodb)
            await stats_service.calculate_player_card_stats(
                player_ids, t_alias, s_alias, r_alias, md_alias, token_payload
            )

    if DEBUG_LEVEL > 0:
        change_type = "stats-affecting" if stats_change_detected else "minor"
        player_calc_note = (
            " + player stats calculated"
            if (stats_change_detected and "FINISHED" in {new_match_status, current_match_status})
            else ""
        )
        print(
            f"Match updated - {change_type} change detected for match {match_id}{player_calc_note}"
        )

    return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(updated_match))


# delete match
@router.delete("/{match_id}", response_description="Delete match")
async def delete_match(
    request: Request,
    match_id: str,
    token_payload: TokenPayload = Depends(auth_handler.auth_wrapper),
) -> Response:
    mongodb = request.app.state.mongodb
    if "ADMIN" not in token_payload.roles:
        raise AuthorizationException(
            message="Admin role required to delete matches",
            details={"user_roles": token_payload.roles, "required_role": "ADMIN"},
        )

    # check and get match
    match = await mongodb["matches"].find_one({"_id": match_id})
    if match is None:
        raise ResourceNotFoundException(resource_type="Match", resource_id=match_id)

    try:
        tournament = match.get("tournament") or {}
        season = match.get("season") or {}
        round_data = match.get("round") or {}
        matchday = match.get("matchday") or {}

        t_alias = tournament.get("alias", None)
        s_alias = season.get("alias", None)
        r_alias = round_data.get("alias", None)
        md_alias = matchday.get("alias", None)

        home_players = [
            player["player"]["playerId"] for player in match.get("home", {}).get("roster") or []
        ]
        away_players = [
            player["player"]["playerId"] for player in match.get("away", {}).get("roster") or []
        ]
        if DEBUG_LEVEL > 0:
            print("### home_players: ", home_players)
            print("### away_players: ", away_players)

        player_ids = home_players + away_players

        # delete in matches
        result = await mongodb["matches"].delete_one({"_id": match_id})
        if result.deleted_count == 0:
            raise ResourceNotFoundException(resource_type="Match", resource_id=match_id)

        logger.info(
            "Match deleted",
            extra={
                "match_id": match_id,
                "tournament": t_alias,
                "season": s_alias,
                "user": token_payload.sub,
            },
        )

        # Only update standings if we have all required aliases
        if t_alias and s_alias and r_alias:
            stats_service = StatsService(mongodb)
            await stats_service.aggregate_round_standings(t_alias, s_alias, r_alias)

        if t_alias and s_alias and r_alias and md_alias:
            stats_service = StatsService(mongodb)
            await stats_service.aggregate_matchday_standings(t_alias, s_alias, r_alias, md_alias)
        # for each player in player_ids loop through stats list and compare tournament, season and round. if found then remove item from list
        if player_ids and t_alias and s_alias and r_alias:
            for player_id in player_ids:
                if DEBUG_LEVEL > 10:
                    print("player_id: ", player_id)
                player = await mongodb["players"].find({"_id": player_id}).to_list(length=1)
                if DEBUG_LEVEL > 10:
                    print("player: ", player)
                updated_stats = [
                    entry
                    for entry in player[0]["stats"]
                    if entry["tournament"].get("alias") != t_alias
                    and entry["season"].get("alias") != s_alias
                    and entry["round"].get("alias") != r_alias
                ]
                if DEBUG_LEVEL > 10:
                    print("### DEL / updated_stats: ", updated_stats)
                await mongodb["players"].update_one(
                    {"_id": player_id}, {"$set": {"stats": updated_stats}}
                )
            stats_service = StatsService(mongodb)
            await stats_service.calculate_player_card_stats(
                player_ids, t_alias, s_alias, r_alias, md_alias, token_payload
            )

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
