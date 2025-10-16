# filename: routers/tournaments.py
from typing import List
from fastapi import APIRouter, Request, Body, status, HTTPException, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from models.tournaments import TournamentBase, TournamentDB, TournamentUpdate
from authentication import AuthHandler, TokenPayload
from pymongo.errors import DuplicateKeyError

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
    if (tournaments :=
        [TournamentDB(**tournament) for tournament in full_query]) is not None:
        return JSONResponse(status_code=status.HTTP_200_OK,
                            content=jsonable_encoder(tournaments))
    raise HTTPException(status_code=404, detail="No tournaments found")


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
    raise HTTPException(
        status_code=404,
        detail=f"Tournament with alias {tournament_alias} not found")


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
        raise HTTPException(status_code=403, detail="Nicht authorisiert")
    # print("tournament: ", tournament)
    tournament_data = jsonable_encoder(tournament)

    # DB processing
    try:
        new_tournament = await mongodb["tournaments"].insert_one(
            tournament_data)
        exclusioin_projection = {"seasons.rounds": 0}
        created_tournament = await mongodb["tournaments"].find_one(
            {"_id": new_tournament.inserted_id}, exclusioin_projection)
        return JSONResponse(status_code=status.HTTP_201_CREATED,
                            content=jsonable_encoder(
                                TournamentDB(**created_tournament)))
    except DuplicateKeyError:
        raise HTTPException(
            status_code=400,
            detail=
            f"Tournament {tournament_data.get('name', 'unknown')} already exists."
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
        raise HTTPException(status_code=403, detail="Nicht authorisiert")
    print("tournament pre exclude: ", tournament)
    tournament_dict = tournament.model_dump(exclude_unset=True)
    tournament_dict.pop("id", None)
    #print("tournament: ", tournament)

    existing_tournament = await mongodb['tournaments'].find_one(
        {"_id": tournament_id})
    if existing_tournament is None:
        raise HTTPException(
            status_code=404,
            detail=f"Tournament with id {tournament_id} not found")
    # Exclude unchanged data
    tournament_to_update = {
        k: v
        for k, v in tournament_dict.items() if v != existing_tournament.get(k)
    }
    if tournament_to_update:
        try:
            print("to update: ", tournament_to_update)
            update_result = await mongodb['tournaments'].update_one(
                {"_id": tournament_id}, {"$set": tournament_to_update})
            if update_result.modified_count == 0:
                raise HTTPException(
                    status_code=404,
                    detail=
                    f"Update: Tournament with id {tournament_id} not found")
        except DuplicateKeyError:
            raise HTTPException(
                status_code=400,
                detail=
                f"Tournament {tournament_dict.get('name', '')} already exists."
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"An unexpected error occurred: {str(e)}")
    else:
        print("No update needed")
        return Response(status_code=status.HTTP_304_NOT_MODIFIED)

    exclusion_projection = {"seasons.rounds": 0}
    updated_tournament = await mongodb['tournaments'].find_one(
        {"_id": tournament_id}, exclusion_projection)
    if updated_tournament is not None:
        tournament_respomse = TournamentDB(**updated_tournament)
        return JSONResponse(status_code=status.HTTP_200_OK,
                            content=jsonable_encoder(tournament_respomse))
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Fetch: Tournament with id {tournament_id} not found")


# delete tournament
@router.delete("/{tournament_alias}", response_description="Delete tournament")
async def delete_tournament(
    request: Request,
    tournament_alias: str,
    token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> Response:
    mongodb = request.app.state.mongodb
    if "ADMIN" not in token_payload.roles:
        raise HTTPException(status_code=403, detail="Nicht authorisiert")
    result = await mongodb['tournaments'].delete_one(
        {"alias": tournament_alias})
    if result.deleted_count == 1:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    raise HTTPException(
        status_code=404,
        detail=f"Tournament with alias {tournament_alias} not found")
