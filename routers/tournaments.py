from typing import Any

from fastapi import APIRouter, Body, Depends, Query, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from pymongo.errors import DuplicateKeyError

from authentication import AuthHandler, TokenPayload
from exceptions import AuthorizationException, DatabaseOperationException, ResourceNotFoundException
from logging_config import logger
from models.responses import PaginatedResponse, StandardResponse
from pydantic import BaseModel
from models.tournaments import TournamentBase, TournamentDB, TournamentUpdate
from services.pagination import PaginationHelper

router = APIRouter()
auth = AuthHandler()


class TournamentLinks(BaseModel):
    self: str
    seasons: str


# get all tournaments
@router.get(
    "", response_description="List all tournaments", response_model=PaginatedResponse[TournamentDB]
)
async def get_tournaments(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(100, ge=1, le=100, description="Items per page"),
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    exclusion_projection: dict[str, int] = {"seasons": 0}
    query: dict[str, Any] = {}

    items, total_count = await PaginationHelper.paginate_query(
        collection=mongodb["tournaments"],
        query=query,
        page=page,
        page_size=page_size,
        sort=[("name", 1)],
        projection=exclusion_projection,
    )

    # Add _links to each tournament
    tournaments_with_links = []
    for tournament in items:
        tournament_data = TournamentDB(**tournament).model_dump(by_alias=True)
        tournament_data["_links"] = {
            "self": f"/tournaments/{tournament['alias']}",
            "seasons": f"/tournaments/{tournament['alias']}/seasons"
        }
        tournaments_with_links.append(tournament_data)

    paginated_result = PaginationHelper.create_response(
        items=tournaments_with_links,
        page=page,
        page_size=page_size,
        total_count=total_count,
        message=f"Retrieved {len(items)} tournaments",
    )

    return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(paginated_result))


# get one tournament by Alias
@router.get(
    "/{tournament_alias}",
    response_description="Get a single tournament",
    response_model=TournamentDB,
)
async def get_tournament(
    request: Request,
    tournament_alias: str,
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    exclusion_projection = {"seasons": 0}
    if (
        tournament := await mongodb["tournaments"].find_one(
            {"alias": tournament_alias}, exclusion_projection
        )
    ) is not None:
        tournament_data = TournamentDB(**tournament).model_dump(by_alias=True)
        tournament_data["_links"] = {
            "self": f"/tournaments/{tournament_alias}",
            "seasons": f"/tournaments/{tournament_alias}/seasons"
        }
        response = StandardResponse(
            success=True,
            data=tournament_data,
            message=f"Retrieved tournament: {tournament_alias}"
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK, content=jsonable_encoder(response)
        )
    raise ResourceNotFoundException(
        resource_type="Tournament", resource_id=tournament_alias, details={"query_field": "alias"}
    )


# create new tournament
@router.post("", response_description="Add new tournament", response_model=TournamentDB)
async def create_tournament(
    request: Request,
    tournament: TournamentBase = Body(...),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    if "ADMIN" not in token_payload.roles:
        raise AuthorizationException(
            message="Admin role required to create tournaments",
            details={"user_role": token_payload.roles},
        )
    tournament_data = jsonable_encoder(tournament)

    # DB processing
    try:
        logger.info(f"Creating new tournament: {tournament_data.get('name', 'unknown')}")
        new_tournament = await mongodb["tournaments"].insert_one(tournament_data)
        exclusion_projection = {"seasons": 0}
        created_tournament = await mongodb["tournaments"].find_one(
            {"_id": new_tournament.inserted_id}, exclusion_projection
        )
        logger.info(f"Tournament created successfully: {tournament_data.get('name', 'unknown')}")
        
        tournament_response = TournamentDB(**created_tournament).model_dump(by_alias=True)
        tournament_response["_links"] = {
            "self": f"/tournaments/{created_tournament['alias']}",
            "seasons": f"/tournaments/{created_tournament['alias']}/seasons"
        }
        
        response = StandardResponse(
            success=True,
            data=tournament_response,
            message=f"Tournament created: {created_tournament.get('name', 'unknown')}"
        )
        
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=jsonable_encoder(response),
        )
    except DuplicateKeyError as e:
        raise DatabaseOperationException(
            operation="insert",
            collection="tournaments",
            details={
                "tournament_name": tournament_data.get("name", "unknown"),
                "reason": "Duplicate key",
            },
        ) from e


# update tournament
@router.patch(
    "/{tournament_id}", response_description="Update tournament", response_model=TournamentDB
)
async def update_tournament(
    request: Request,
    tournament_id: str,
    tournament: TournamentUpdate = Body(...),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
):
    mongodb = request.app.state.mongodb
    if "ADMIN" not in token_payload.roles:
        raise AuthorizationException(
            message="Admin role required to update tournaments",
            details={"user_role": token_payload.roles},
        )
    tournament_dict = tournament.model_dump(exclude_unset=True)
    tournament_dict.pop("id", None)

    existing_tournament = await mongodb["tournaments"].find_one({"_id": tournament_id})
    if existing_tournament is None:
        raise ResourceNotFoundException(resource_type="Tournament", resource_id=tournament_id)
    # Exclude unchanged data
    tournament_to_update = {
        k: v for k, v in tournament_dict.items() if v != existing_tournament.get(k)
    }
    if tournament_to_update:
        try:
            logger.info(f"Updating tournament: {existing_tournament.get('name', tournament_id)}")
            update_result = await mongodb["tournaments"].update_one(
                {"_id": tournament_id}, {"$set": tournament_to_update}
            )
            if update_result.modified_count == 0:
                logger.info(
                    "No changes to update for tournament",
                    extra={"tournament_alias": tournament_id},
                )
                tournament_unchanged = TournamentDB(**existing_tournament).model_dump(by_alias=True)
                return StandardResponse(
                    success=True,
                    data=tournament_unchanged,
                    message="Tournament data unchanged (already up to date)",
                )
        except DuplicateKeyError as e:
            raise DatabaseOperationException(
                operation="update",
                collection="tournaments",
                details={"tournament_id": tournament_id, "reason": "Duplicate key"},
            ) from e
        except Exception as e:
            logger.error(f"Unexpected error updating tournament {tournament_id}: {str(e)}")
            raise DatabaseOperationException(
                operation="update",
                collection="tournaments",
                details={"tournament_id": tournament_id, "error": str(e)},
            ) from e
    else:
        logger.info(f"No changes to update for tournament {tournament_id}")
        tournament_unchanged = TournamentDB(**existing_tournament).model_dump(by_alias=True)
        return StandardResponse(
            success=True,
            data=tournament_unchanged,
            message="Tournament data unchanged (already up to date)",
        )

    exclusion_projection = {"seasons": 0}
    updated_tournament = await mongodb["tournaments"].find_one(
        {"_id": tournament_id}, exclusion_projection
    )
    if updated_tournament is not None:
        logger.info(
            f"Tournament updated successfully: {updated_tournament.get('name', tournament_id)}"
        )
        tournament_response = TournamentDB(**updated_tournament).model_dump(by_alias=True)
        tournament_response["_links"] = {
            "self": f"/tournaments/{updated_tournament['alias']}",
            "seasons": f"/tournaments/{updated_tournament['alias']}/seasons"
        }
        response = StandardResponse(
            success=True,
            data=tournament_response,
            message=f"Tournament updated: {updated_tournament.get('name', tournament_id)}"
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK, content=jsonable_encoder(response)
        )
    else:
        raise ResourceNotFoundException(
            resource_type="Tournament",
            resource_id=tournament_id,
            details={"context": "After update"},
        )


# delete tournament
@router.delete("/{id}", response_description="Delete tournament")
async def delete_tournament(
    request: Request,
    id: str,
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> Response:
    mongodb = request.app.state.mongodb
    if "ADMIN" not in token_payload.roles:
        raise AuthorizationException(
            message="Admin role required to delete tournaments",
            details={"user_role": token_payload.roles},
        )

    logger.info(f"Deleting tournament with id: {id}")
    result = await mongodb["tournaments"].delete_one({"_id": id})
    if result.deleted_count == 1:
        logger.info(f"Tournament deleted successfully: {id}")
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    raise ResourceNotFoundException(resource_type="Tournament", resource_id=id)
