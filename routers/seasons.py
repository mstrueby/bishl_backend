# filename: routers/seasons.py

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response

from authentication import AuthHandler, TokenPayload
from exceptions import ResourceNotFoundException
from models.tournaments import SeasonBase, SeasonDB, SeasonUpdate
from models.responses import StandardResponse


router = APIRouter()
auth = AuthHandler()


# get all seasons of a tournament
@router.get(
    "/", response_description="List all seasons for a tournament", response_model=list[SeasonDB]
)
async def get_seasons_for_tournament(
    request: Request,
    tournament_alias: str = Path(
        ..., description="The alias of the tournament to list the seasons for"
    ),
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    exclusion_projection = {"seasons.rounds.matchdays": 0}
    if (
        tournament := await mongodb["tournaments"].find_one(
            {"alias": tournament_alias}, exclusion_projection
        )
    ) is not None:
        seasons = [SeasonDB(**season) for season in (tournament.get("seasons") or [])]
        return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(seasons))
    raise ResourceNotFoundException(resource_type="Tournament", resource_id=tournament_alias)


# get one season of a tournament
@router.get("/{season_alias}", response_description="Get a single season", response_model=SeasonDB)
async def get_season(
    request: Request,
    tournament_alias: str = Path(
        ..., description="The alias of the tournament to list the seasons for"
    ),
    season_alias: str = Path(..., description="The alias of the season to get"),
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    exclusion_projection = {"seasons.rounds.matchdays": 0}
    if (
        tournament := await mongodb["tournaments"].find_one(
            {"alias": tournament_alias}, exclusion_projection
        )
    ) is not None:
        for season in tournament.get("seasons", []):
            if season.get("alias") == season_alias:
                season_response = SeasonDB(**season)
                return JSONResponse(
                    status_code=status.HTTP_200_OK, content=jsonable_encoder(season_response)
                )
        raise ResourceNotFoundException(
            resource_type="Season",
            resource_id=season_alias,
            details={"tournament_alias": tournament_alias},
        )
    raise ResourceNotFoundException(resource_type="Tournament", resource_id=tournament_alias)


# add new season to tournament
@router.post("/", response_description="Add new season to tournament", response_model=SeasonDB)
async def create_season(
    request: Request,
    tournament_alias: str = Path(..., description="The alias of the tournament to add a season to"),
    season: SeasonBase = Body(..., description="Season data"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    if "ADMIN" not in token_payload.roles:
        raise HTTPException(status_code=403, detail="Nicht authorisiert")
    # Check if the tournament exists
    if (tournament := await mongodb["tournaments"].find_one({"alias": tournament_alias})) is None:
        raise ResourceNotFoundException(resource_type="Tournament", resource_id=tournament_alias)
    # Check for existing season with the same alias as the one to add
    if any(s.get("alias") == season.alias for s in tournament.get("seasons", [])):
        raise HTTPException(
            status_code=409,
            detail=f"Season {season.alias} already exists in tournament {tournament_alias}",
        )

    # Here you'd append the new season data to the tournament's seasons array
    try:
        season_data = jsonable_encoder(season)
        result = await mongodb["tournaments"].update_one(
            {"alias": tournament_alias}, {"$push": {"seasons": season_data}}
        )
        if result.modified_count == 1:
            # get inserted season
            updated_tournament = await mongodb["tournaments"].find_one(
                {"alias": tournament_alias, "seasons.alias": season.alias},
                {"_id": 0, "seasons.$": 1},
            )
            # updated_tournament has only one season
            if updated_tournament and "seasons" in updated_tournament:
                season = updated_tournament["seasons"][0]
                season_response = SeasonDB(**season_data)
                return JSONResponse(
                    status_code=status.HTTP_201_CREATED, content=jsonable_encoder(season_response)
                )
            else:
                raise ResourceNotFoundException(
                    resource_type="Season",
                    resource_id=season.alias,
                    details={"tournament_alias": tournament_alias},
                )
        else:
            # This case should ideally not be reached if the tournament exists and modified_count is 0
            # but it's a safeguard.
            raise ResourceNotFoundException(
                resource_type="Tournament", resource_id=tournament_alias
            )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# update season in tournament
@router.patch(
    "/{season_id}", response_description="Update a season in tournament", response_model=SeasonDB
)
async def update_season(
    request: Request,
    season_id: str,
    tournament_alias: str = Path(
        ..., description="The ALIAS of the tournament to update the season in"
    ),
    season: SeasonUpdate = Body(..., description="Season data to update"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
):
    mongodb = request.app.state.mongodb
    if "ADMIN" not in token_payload.roles:
        raise HTTPException(status_code=403, detail="Nicht authorisiert")
    # exclude unset
    season_dict = season.model_dump(exclude_unset=True)
    # Find the tournament by alias
    tournament = await mongodb["tournaments"].find_one({"alias": tournament_alias})
    if not tournament:
        raise ResourceNotFoundException(resource_type="Tournament", resource_id=tournament_alias)

    # Find the index of the season to update
    season_index = next(
        (index for (index, d) in enumerate(tournament["seasons"]) if d["_id"] == season_id), None
    )
    if season_index is None:
        raise ResourceNotFoundException(
            resource_type="Season",
            resource_id=season_id,
            details={"tournament_alias": tournament_alias},
        )

    # Prepare the update by excluding unchanged data
    update_data: dict[str, dict[str, Any]] = {"$set": {}}
    has_changes = False
    for field, value in season_dict.items():
        if field != "_id" and value != tournament["seasons"][season_index].get(field):
            update_data["$set"][f"seasons.{season_index}.{field}"] = value
            has_changes = True

    # Proceed with the update only if there are changes
    if has_changes:
        # Update season in tournament
        try:
            result = await mongodb["tournaments"].update_one(
                {"_id": tournament["_id"], f"seasons.{season_index}._id": season_id}, update_data
            )
            if result.modified_count == 0:
                # This case implies no fields were actually changed, or a race condition.
                # Re-check season existence to be sure.
                updated_tournament_check = await mongodb["tournaments"].find_one(
                    {"alias": tournament_alias}, {"seasons.$": ""}
                )
                if not any(
                    s["_id"] == season_id for s in updated_tournament_check.get("seasons", [])
                ):
                    raise ResourceNotFoundException(
                        resource_type="Season",
                        resource_id=season_id,
                        details={"tournament_alias": tournament_alias},
                    )
                else:
                    # If season exists but no changes were applied because data was the same
                    return StandardResponse(
                        status_code=status.HTTP_304_NOT_MODIFIED,
                        message="No changes detected, season not modified."
                    ).response()

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    else:
        # No changes detected in the payload compared to the existing season data
        return StandardResponse(
            status_code=status.HTTP_304_NOT_MODIFIED,
            message="No changes detected, season not modified."
        ).response()

    # Fetch the current season data after update
    tournament = await mongodb["tournaments"].find_one(
        {"alias": tournament_alias}, {"_id": 0, "seasons": {"$elemMatch": {"_id": season_id}}}
    )
    if tournament and "seasons" in tournament and tournament["seasons"]:
        updated_season = tournament["seasons"][0]
        if "rounds" in updated_season and updated_season["rounds"] is not None:
            for round in updated_season["rounds"]:
                if "matchdays" in round:
                    del round["matchdays"]
        season_response = SeasonDB(**updated_season)
        return JSONResponse(
            status_code=status.HTTP_200_OK, content=jsonable_encoder(season_response)
        )
    else:
        # This case means the season was not found after the update, which is unexpected if modified_count was > 0
        raise ResourceNotFoundException(
            resource_type="Season",
            resource_id=season_id,
            details={"tournament_alias": tournament_alias},
        )


# delete season from tournament
@router.delete("/{season_id}", response_description="Delete a single season from a tournament")
async def delete_season(
    request: Request,
    tournament_alias: str = Path(
        ..., description="The alias of the tournament to delete the season from"
    ),
    season_id: str = Path(..., description="The ID of the season to delete"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> Response:
    mongodb = request.app.state.mongodb
    if "ADMIN" not in token_payload.roles:
        raise HTTPException(status_code=403, detail="Nicht authorisiert")
    delete_result = await mongodb["tournaments"].update_one(
        {"alias": tournament_alias}, {"$pull": {"seasons": {"_id": season_id}}}
    )
    if delete_result.modified_count == 1:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    # If modified_count is 0, it means the tournament was found but the season wasn't there to be pulled.
    # We should check if the tournament exists first to provide a more specific error.
    tournament = await mongodb["tournaments"].find_one({"alias": tournament_alias})
    if not tournament:
        raise ResourceNotFoundException(resource_type="Tournament", resource_id=tournament_alias)
    else:
        raise ResourceNotFoundException(
            resource_type="Season",
            resource_id=season_id,
            details={"tournament_alias": tournament_alias},
        )