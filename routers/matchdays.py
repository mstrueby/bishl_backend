# filename: routers/matchdays.py
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from authentication import AuthHandler, TokenPayload
from exceptions import AuthorizationException, DatabaseOperationException
from logging_config import logger
from models.responses import StandardResponse
from models.matchday_responses import MatchdayResponse, MatchdayLinks
from models.tournaments import MatchdayBase, MatchdayDB, MatchdayUpdate
from utils import DEBUG_LEVEL, my_jsonable_encoder

router = APIRouter()
auth = AuthHandler()


# get all matchdays of a round
@router.get(
    "",
    response_description="List all matchdays for a round",
    response_model=StandardResponse[list[MatchdayResponse]],
)
async def get_matchdays_for_round(
    request: Request,
    tournament_alias: str = Path(
        ..., description="The alias of the tournament to list the matchdays for"
    ),
    season_alias: str = Path(..., description="The alias of the season to get"),
    round_alias: str = Path(..., description="The alias of the round to get"),
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    exclusion_projection: dict[str, Any] = {}
    if (
        tournament := await mongodb["tournaments"].find_one(
            {"alias": tournament_alias}, exclusion_projection
        )
    ) is not None:
        for season in tournament.get("seasons", []):
            if season.get("alias") == season_alias:
                for round_data in season.get("rounds", []):
                    if round_data.get("alias") == round_alias:
                        matchdays = []
                        for matchday in round_data.get("matchdays", []):
                            matchday_response = MatchdayResponse(
                                _id=matchday["_id"],
                                name=matchday["name"],
                                alias=matchday["alias"],
                                type=matchday["type"],
                                startDate=matchday.get("startDate"),
                                endDate=matchday.get("endDate"),
                                createStandings=matchday.get("createStandings", False),
                                createStats=matchday.get("createStats", False),
                                matchSettings=matchday.get("matchSettings"),
                                published=matchday.get("published", False),
                                standings=matchday.get("standings"),
                                owner=matchday.get("owner"),
                                links=MatchdayLinks(
                                    self=f"/tournaments/{tournament_alias}/seasons/{season_alias}/rounds/{round_alias}/matchdays/{matchday['alias']}",
                                    matches=f"/matches?tournament={tournament_alias}&season={season_alias}&round={round_alias}&matchday={matchday['alias']}",
                                    round=f"/tournaments/{tournament_alias}/seasons/{season_alias}/rounds/{round_alias}"
                                )
                            )
                            matchdays.append(matchday_response)
                        return JSONResponse(
                            status_code=status.HTTP_200_OK,
                            content=jsonable_encoder(
                                StandardResponse(
                                    success=True,
                                    data=matchdays,
                                    message=f"Retrieved {len(matchdays)} matchdays",
                                )
                            ),
                        )
                raise HTTPException(
                    status_code=404,
                    detail=f"Round with name {round_alias} not found in season {season_alias} of tournament {tournament_alias}",
                )
        raise HTTPException(
            status_code=404,
            detail=f"Season {season_alias} not found in tournament {tournament_alias}",
        )
    raise HTTPException(
        status_code=404, detail=f"Tournament with alias {tournament_alias} not found"
    )


# get one matchday of a round
@router.get(
    "/{matchday_alias}",
    response_description="Get one matchday of a round",
    response_model=StandardResponse[MatchdayResponse],
)
async def get_matchday(
    request: Request,
    tournament_alias: str = Path(
        ..., description="The ALIAS of the tournament to list the matchdays for"
    ),
    season_alias: str = Path(..., description="The alias of the season to get"),
    round_alias: str = Path(..., description="The alias of the round to get"),
    matchday_alias: str = Path(..., description="The alias of the matchday to get"),
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    exclusion_projection: dict[str, Any] = {}
    if (
        tournament := await mongodb["tournaments"].find_one(
            {"alias": tournament_alias}, exclusion_projection
        )
    ) is not None:
        for season in tournament.get("seasons", []):
            if season.get("alias") == season_alias:
                for round_data in season.get("rounds", []):
                    if round_data.get("alias") == round_alias:
                        for matchday in round_data.get("matchdays", []):
                            if matchday.get("alias") == matchday_alias:
                                matchday_response = MatchdayResponse(
                                    _id=matchday["_id"],
                                    name=matchday["name"],
                                    alias=matchday["alias"],
                                    type=matchday["type"],
                                    startDate=matchday.get("startDate"),
                                    endDate=matchday.get("endDate"),
                                    createStandings=matchday.get("createStandings", False),
                                    createStats=matchday.get("createStats", False),
                                    matchSettings=matchday.get("matchSettings"),
                                    published=matchday.get("published", False),
                                    standings=matchday.get("standings"),
                                    owner=matchday.get("owner"),
                                    links=MatchdayLinks(
                                        self=f"/tournaments/{tournament_alias}/seasons/{season_alias}/rounds/{round_alias}/matchdays/{matchday_alias}",
                                        matches=f"/matches?tournament={tournament_alias}&season={season_alias}&round={round_alias}&matchday={matchday_alias}",
                                        round=f"/tournaments/{tournament_alias}/seasons/{season_alias}/rounds/{round_alias}"
                                    )
                                )
                                return JSONResponse(
                                    status_code=status.HTTP_200_OK,
                                    content=jsonable_encoder(
                                        StandardResponse(
                                            success=True,
                                            data=matchday_response,
                                            message="Matchday retrieved successfully",
                                        )
                                    ),
                                )
    raise HTTPException(
        status_code=404,
        detail=f"Matchday {matchday_alias} not found in round {round_alias} of season {season_alias} of tournament {tournament_alias}",
    )


# add new matchday to a round
@router.post(
    "",
    response_description="Add a new matchday to a round",
    response_model=StandardResponse[MatchdayDB],
)
async def add_matchday(
    request: Request,
    tournament_alias: str = Path(
        ..., description="The alias of the tournament to add the matchday to"
    ),
    season_alias: str = Path(..., description="The alias of the season to add"),
    round_alias: str = Path(..., description="The alias of the round to add"),
    matchday: MatchdayBase = Body(..., description="The matchday to add"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    if "ADMIN" not in token_payload.roles:
        raise AuthorizationException(
            message="Admin role required to add matchdays",
            details={"user_role": token_payload.roles},
        )
    # print("add matchday")
    # check if tournament exists
    if (tournament := await mongodb["tournaments"].find_one({"alias": tournament_alias})) is None:
        raise HTTPException(status_code=404, detail=f"Tournament {tournament_alias} not found")
    # check if season exists
    if (season := next(s for s in tournament["seasons"] if s.get("alias") == season_alias)) is None:
        raise HTTPException(status_code=404, detail=f"Season {season_alias} not found")
    # check if round exists
    if (round := next(r for r in season["rounds"] if r.get("alias") == round_alias)) is None:

        raise HTTPException(status_code=404, detail=f"Round {round_alias} not found")
    # check if matchday already exiists
    if any(md.get("alias") == matchday.alias for md in round.get("matchdays", [])):
        raise HTTPException(
            status_code=404,
            detail=f"Matchday {matchday.alias} already exists in round {round_alias} in seasion {season_alias} of tournament {tournament_alias}",
        )

    # add matchday to round
    try:
        matchday_data = my_jsonable_encoder(matchday)
        filter = {"alias": tournament_alias}
        new_values = {"$push": {"seasons.$[s].rounds.$[r].matchdays": matchday_data}}
        array_filters = [{"s.alias": season_alias}, {"r.alias": round_alias}]
        result = await mongodb["tournaments"].update_one(
            filter=filter, update=new_values, array_filters=array_filters, upsert=False
        )
        # get inserted matchday
        if result.modified_count == 1:
            updated_tournament = await mongodb["tournaments"].find_one(
                {
                    "alias": tournament_alias,
                    "seasons.alias": season_alias,
                    "seasons.rounds.alias": round_alias,
                }
            )
            # updated_tournament contains only one season of the tournament
            if updated_tournament and "seasons" in updated_tournament:
                season_data = next(
                    (s for s in updated_tournament["seasons"] if s.get("alias") == season_alias),
                    None,
                )
                if season_data and "rounds" in season_data:
                    round_data = next(
                        (r for r in season_data["rounds"] if r.get("alias") == round_alias), None
                    )
                    if round_data and "matchdays" in round_data:
                        inserted_matchday = next(
                            (
                                md
                                for md in round_data["matchdays"]
                                if md.get("alias") == matchday.alias
                            ),
                            None,
                        )
                        if inserted_matchday:
                            logger.info(
                                f"Matchday added: {matchday.alias} in {tournament_alias}/{season_alias}/{round_alias}"
                            )
                            return JSONResponse(
                                status_code=status.HTTP_201_CREATED,
                                content=jsonable_encoder(
                                    StandardResponse(
                                        success=True,
                                        data=MatchdayDB(**inserted_matchday),
                                        message="Matchday created successfully",
                                    )
                                ),
                            )
        raise DatabaseOperationException(
            operation="insert",
            collection="tournaments.matchdays",
            details={
                "matchday_alias": matchday.alias,
                "round": round_alias,
                "season": season_alias,
                "tournament": tournament_alias,
                "modified_count": result.modified_count,
            },
        )
    except Exception as e:
        logger.error(f"Error adding matchday {matchday.alias}: {str(e)}")
        raise DatabaseOperationException(
            operation="insert",
            collection="tournaments.matchdays",
            details={"error": str(e), "matchday_alias": matchday.alias},
        ) from e


# update matchday of a round
@router.patch(
    "/{matchday_id}",
    response_description="Update a matchday of a round",
    response_model=StandardResponse[MatchdayDB],
)
async def update_matchday(
    request: Request,
    matchday_id: str = Path(..., description="The ID of the matchday to update"),
    tournament_alias: str = Path(
        ..., description="The alias of the tournament to update the matchday of"
    ),
    season_alias: str = Path(..., description="The alias of the season to update"),
    round_alias: str = Path(..., description="The alias of the round to update"),
    matchday: MatchdayUpdate = Body(..., description="The matchday to update"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
):
    mongodb = request.app.state.mongodb
    if "ADMIN" not in token_payload.roles:
        raise AuthorizationException(
            message="Admin role required to update matchdays",
            details={"user_role": token_payload.roles},
        )
    if DEBUG_LEVEL > 10:
        print("update matchday: ", matchday)
    matchday_dict = matchday.model_dump(exclude_unset=True)
    if DEBUG_LEVEL > 100:
        print("excluded unset: ", matchday_dict)
    # check if tournament exists
    tournament = await mongodb["tournaments"].find_one({"alias": tournament_alias})
    if tournament is None:
        raise HTTPException(status_code=404, detail=f"Tournament {tournament_alias} not found")
    # check if season exists
    season_index = next(
        (i for i, s in enumerate(tournament["seasons"]) if s["alias"] == season_alias), None
    )
    if season_index is None:
        raise HTTPException(
            status_code=404,
            detail=f"Season {season_alias} not found in tournament {tournament_alias}",
        )
    if DEBUG_LEVEL > 20:
        print("season_index: ", season_index)
    # check if round exists
    round_index = next(
        (
            i
            for i, r in enumerate(tournament["seasons"][season_index]["rounds"])
            if r.get("alias") == round_alias
        ),
        None,
    )
    if DEBUG_LEVEL > 20:
        print("round_index: ", round_index)
    if round_index is None:
        raise HTTPException(
            status_code=404,
            detail=f"Round {round_alias} not found in season {season_alias} of tournament {tournament_alias}",
        )
    # check if matchday exists
    round = tournament["seasons"][season_index]["rounds"][round_index]
    matchday_index = next(
        (i for i, md in enumerate(round["matchdays"]) if md["_id"] == matchday_id), None
    )
    if DEBUG_LEVEL > 20:
        print("matchday_index: ", matchday_index)
    if matchday_index is None:
        raise HTTPException(
            status_code=404,
            detail=f"Matchday {matchday_id} not found in round {round_alias} of season {season_alias} of tournament {tournament_alias}",
        )

    # get matches for this matchday to determine start/end dates
    # print(tournament_alias, season_alias, round_alias, tournament["seasons"][season_index]["rounds"][round_index]['matchdays'][matchday_index]['alias'])
    matches = (
        await mongodb["matches"]
        .find(
            {
                "tournament.alias": tournament_alias,
                "season.alias": season_alias,
                "round.alias": round_alias,
                "matchday.alias": tournament["seasons"][season_index]["rounds"][round_index][
                    "matchdays"
                ][matchday_index]["alias"],
            }
        )
        .sort("startDate", 1)
        .to_list(length=None)
    )
    if matches:
        matchday_dict["startDate"] = min(match["startDate"] for match in matches)
        matchday_dict["endDate"] = max(match["startDate"] for match in matches)

    # update matchday
    # prepare
    update_data: dict[str, dict[str, Any]] = {"$set": {}}
    for field in matchday_dict:
        if field != "_id" and matchday_dict[field] != tournament["seasons"][season_index]["rounds"][
            round_index
        ]["matchdays"][matchday_index].get(field):
            update_data["$set"][
                f"seasons.{season_index}.rounds.{round_index}.matchdays.{matchday_index}.{field}"
            ] = matchday_dict[field]
    if DEBUG_LEVEL > 10:
        print("update_data: ", update_data)

    # update matchday
    if update_data.get("$set"):
        if DEBUG_LEVEL > 10:
            print("to update", update_data)
        try:
            result = await mongodb["tournaments"].update_one(
                {
                    "alias": tournament_alias,
                    "seasons.alias": season_alias,
                    "seasons.rounds.alias": round_alias,
                    "seasons.rounds.matchdays._id": matchday_id,
                },
                update_data,
            )
            if result.modified_count == 0:
                raise DatabaseOperationException(
                    operation="update",
                    collection="tournaments.matchdays",
                    details={
                        "matchday_id": matchday_id,
                        "round": round_alias,
                        "season": season_alias,
                        "tournament": tournament_alias,
                        "modified_count": 0,
                    },
                )
            logger.info(
                f"Matchday updated: {matchday_id} in {tournament_alias}/{season_alias}/{round_alias}"
            )
        except Exception as e:
            logger.error(f"Error updating matchday {matchday_id}: {str(e)}")
            raise DatabaseOperationException(
                operation="update",
                collection="tournaments.matchdays",
                details={"error": str(e), "matchday_id": matchday_id},
            ) from e
    else:
        if DEBUG_LEVEL > 10:
            print("no update needed")
        # Return current matchday state
        current_matchday = tournament["seasons"][season_index]["rounds"][round_index]["matchdays"][
            matchday_index
        ]
        logger.info(
            "No changes to update for matchday",
            extra={"matchday_id": matchday_id, "round": round_alias, "season": season_alias},
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=jsonable_encoder(
                StandardResponse(
                    success=True, data=MatchdayDB(**current_matchday), message="No changes detected"
                )
            ),
        )

    # Fetch the updated matchday
    updated_tournament = await mongodb["tournaments"].find_one(
        {
            "alias": tournament_alias,
            "seasons.alias": season_alias,
        },
        {"_id": 0, "seasons.$": 1},
    )
    if updated_tournament and "seasons" in updated_tournament:
        season = updated_tournament["seasons"][0]
        round = next((r for r in season.get("rounds", []) if r.get("alias") == round_alias), None)
        if round and "matchdays" in round:
            matchdays = round.get("matchdays", [])
            updated_matchday = next(
                (md for md in matchdays if str(md.get("_id")) == matchday_id), None
            )
            if updated_matchday:
                # Recalculate standings if createStandings was updated
                if matchday_dict.get("createStandings") is not None:
                    from services.stats_service import StatsService
                    stats_service = StatsService(mongodb)
                    await stats_service.aggregate_matchday_standings(
                        tournament_alias, season_alias, round_alias, updated_matchday["alias"]
                    )
                    logger.info(
                        f"Recalculated standings for matchday {updated_matchday['alias']}"
                    )
                
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content=jsonable_encoder(
                        StandardResponse(
                            success=True,
                            data=MatchdayDB(**updated_matchday),
                            message="Matchday updated successfully",
                        )
                    ),
                )
            else:
                raise HTTPException(
                    status_code=404,
                    detail=f"Fetch: Matchday {matchday_id} not found in round {round_alias} of season {season_alias} of tournament {tournament_alias}",
                )


# delete matchday of a round
@router.delete("/{matchday_id}", response_description="Delete a matchday of a round")
async def delete_matchday(
    request: Request,
    tournament_alias: str = Path(
        ..., description="The alias of the tournament to delete the matchday of"
    ),
    season_alias: str = Path(..., description="The alias of the season to delete"),
    round_alias: str = Path(..., description="The alias of the round to delete"),
    matchday_id: str = Path(..., description="The ID of the matchday to delete"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> Response:
    mongodb = request.app.state.mongodb
    if "ADMIN" not in token_payload.roles:
        raise AuthorizationException(
            message="Admin role required to delete matchdays",
            details={"user_role": token_payload.roles},
        )
    result = await mongodb["tournaments"].update_one(
        {
            "alias": tournament_alias,
            "seasons.alias": season_alias,
            "seasons.rounds.alias": round_alias,
            "seasons.rounds.matchdays._id": matchday_id,
        },
        {"$pull": {"seasons.$[s].rounds.$[r].matchdays": {"_id": matchday_id}}},
        array_filters=[{"s.alias": season_alias}, {"r.alias": round_alias}],
    )
    if result.modified_count == 1:
        logger.info(
            f"Matchday deleted: {matchday_id} in {tournament_alias}/{season_alias}/{round_alias}"
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    else:
        logger.warning(
            f"Attempted to delete non-existent matchday: {matchday_id} in {tournament_alias}/{season_alias}/{round_alias}"
        )
        raise DatabaseOperationException(
            operation="delete",
            collection="tournaments.matchdays",
            details={
                "matchday_id": matchday_id,
                "round": round_alias,
                "season": season_alias,
                "tournament": tournament_alias,
                "modified_count": 0,
            },
        )
