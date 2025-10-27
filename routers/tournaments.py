from typing import List
from fastapi import APIRouter, Request, Body, status, HTTPException, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from models.tournaments import TournamentBase, TournamentDB, TournamentUpdate
from authentication import AuthHandler, TokenPayload
from services.performance_monitor import monitor_query
from pymongo.errors import DuplicateKeyError
from exceptions import (
    ResourceNotFoundException,
    DatabaseOperationException,
    AuthorizationException
)
from logging_config import logger

router = APIRouter()
auth = AuthHandler()


# get all tournaments
@router.get("/",
            response_description="List all tournaments",
            response_model=List[TournamentDB])
async def get_tournaments(request: Request) -> JSONResponse:
    mongodb = request.app.state.mongodb
    exclusion_projection = {"seasons.rounds": 0}
    query = {}
    full_query = await mongodb["tournaments"].find(
        query, projection=exclusion_projection).sort("name",
                                                     1).to_list(length=None)
    tournaments = [TournamentDB(**tournament) for tournament in full_query]
    return JSONResponse(status_code=status.HTTP_200_OK,
                        content=jsonable_encoder(tournaments))


# get one tournament by Alias
@router.get("/{tournament_alias}",
            response_description="Get a single tournament",
            response_model=TournamentDB)
async def get_tournament(
    request: Request,
    tournament_alias: str,
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    exclusion_projection = {"seasons.rounds": 0}
    if (tournament := await
            mongodb["tournaments"].find_one({"alias": tournament_alias},
                                            exclusion_projection)) is not None:
        return JSONResponse(status_code=status.HTTP_200_OK,
                            content=jsonable_encoder(
                                TournamentDB(**tournament)))
    raise ResourceNotFoundException(
        resource_type="Tournament",
        resource_id=tournament_alias,
        details={"query_field": "alias"}
    )


# create new tournament
@router.post("/",
             response_description="Add new tournament",
             response_model=TournamentDB)
async def create_tournament(
    request: Request,
    tournament: TournamentBase = Body(...),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    if "ADMIN" not in token_payload.roles:
        raise AuthorizationException(
            message="Admin role required to create tournaments",
            details={"user_role": token_payload.roles}
        )
    tournament_data = jsonable_encoder(tournament)

    # DB processing
    try:
        logger.info(f"Creating new tournament: {tournament_data.get('name', 'unknown')}")
        new_tournament = await mongodb["tournaments"].insert_one(
            tournament_data)
        exclusioin_projection = {"seasons.rounds": 0}
        created_tournament = await mongodb["tournaments"].find_one(
            {"_id": new_tournament.inserted_id}, exclusioin_projection)
        logger.info(f"Tournament created successfully: {tournament_data.get('name', 'unknown')}")
        return JSONResponse(status_code=status.HTTP_201_CREATED,
                            content=jsonable_encoder(
                                TournamentDB(**created_tournament)))
    except DuplicateKeyError:
        raise DatabaseOperationException(
            operation="insert",
            collection="tournaments",
            details={"tournament_name": tournament_data.get('name', 'unknown'), "reason": "Duplicate key"}
        )


# update tournament
@router.patch("/{tournament_id}",
              response_description="Update tournament",
              response_model=TournamentDB)
async def update_tournament(request: Request,
                            tournament_id: str,
                            tournament: TournamentUpdate = Body(...),
                            token_payload: TokenPayload = Depends(
                                auth.auth_wrapper)):
    mongodb = request.app.state.mongodb
    if "ADMIN" not in token_payload.roles:
        raise AuthorizationException(
            message="Admin role required to update tournaments",
            details={"user_role": token_payload.roles}
        )
    tournament_dict = tournament.model_dump(exclude_unset=True)
    tournament_dict.pop("id", None)

    existing_tournament = await mongodb['tournaments'].find_one(
        {"_id": tournament_id})
    if existing_tournament is None:
        raise ResourceNotFoundException(
            resource_type="Tournament",
            resource_id=tournament_id
        )
    # Exclude unchanged data
    tournament_to_update = {
        k: v
        for k, v in tournament_dict.items() if v != existing_tournament.get(k)
    }
    if tournament_to_update:
        try:
            logger.info(f"Updating tournament: {existing_tournament.get('name', tournament_id)}")
            update_result = await mongodb['tournaments'].update_one(
                {"_id": tournament_id}, {"$set": tournament_to_update})
            if update_result.modified_count == 0:
                raise DatabaseOperationException(
                    operation="update",
                    collection="tournaments",
                    details={"tournament_id": tournament_id, "modified_count": 0}
                )
        except DuplicateKeyError:
            raise DatabaseOperationException(
                operation="update",
                collection="tournaments",
                details={"tournament_id": tournament_id, "reason": "Duplicate key"}
            )
        except Exception as e:
            logger.error(f"Unexpected error updating tournament {tournament_id}: {str(e)}")
            raise DatabaseOperationException(
                operation="update",
                collection="tournaments",
                details={"tournament_id": tournament_id, "error": str(e)}
            )
    else:
        logger.info(f"No changes to update for tournament {tournament_id}")
        return Response(status_code=status.HTTP_304_NOT_MODIFIED)

    exclusion_projection = {"seasons.rounds": 0}
    updated_tournament = await mongodb['tournaments'].find_one(
        {"_id": tournament_id}, exclusion_projection)
    if updated_tournament is not None:
        logger.info(f"Tournament updated successfully: {updated_tournament.get('name', tournament_id)}")
        tournament_respomse = TournamentDB(**updated_tournament)
        return JSONResponse(status_code=status.HTTP_200_OK,
                            content=jsonable_encoder(tournament_respomse))
    else:
        raise ResourceNotFoundException(
            resource_type="Tournament",
            resource_id=tournament_id,
            details={"context": "After update"}
        )


# delete tournament
@router.delete("/{tournament_alias}", response_description="Delete tournament")
async def delete_tournament(
    request: Request,
    tournament_alias: str,
    token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> Response:
    mongodb = request.app.state.mongodb
    if "ADMIN" not in token_payload.roles:
        raise AuthorizationException(
            message="Admin role required to delete tournaments",
            details={"user_role": token_payload.roles}
        )

    logger.info(f"Deleting tournament with alias: {tournament_alias}")
    result = await mongodb['tournaments'].delete_one(
        {"alias": tournament_alias})
    if result.deleted_count == 1:
        logger.info(f"Tournament deleted successfully: {tournament_alias}")
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    raise ResourceNotFoundException(
        resource_type="Tournament",
        resource_id=tournament_alias,
        details={"query_field": "alias"}
    )