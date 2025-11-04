
# filename: routers/penalties.py
from fastapi import APIRouter, Body, Depends, Path, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response

from authentication import AuthHandler, TokenPayload
from models.matches import PenaltiesBase, PenaltiesDB, PenaltiesUpdate
from services.penalty_service import PenaltyService

router = APIRouter()
auth = AuthHandler()


# get penalty sheet of a team
@router.get("/", response_description="Get penalty sheet", response_model=list[PenaltiesDB])
async def get_penalty_sheet(
    request: Request,
    match_id: str = Path(..., description="The ID of the match"),
    team_flag: str = Path(..., description="The team flag (home/away)"),
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    service = PenaltyService(mongodb)
    
    penalty_entries = await service.get_penalties(match_id, team_flag)
    return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(penalty_entries))


# create one penalty
@router.post("/", response_description="Create one penalty", response_model=PenaltiesDB)
async def create_penalty(
    request: Request,
    match_id: str = Path(..., description="The id of the match"),
    team_flag: str = Path(..., description="The flag of the team"),
    penalty: PenaltiesBase = Body(..., description="The penalty to be added to the penaltiesheet"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    service = PenaltyService(mongodb)
    
    new_penalty = await service.create_penalty(match_id, team_flag, penalty)
    return JSONResponse(
        status_code=status.HTTP_201_CREATED, content=jsonable_encoder(new_penalty)
    )


# get one penalty
@router.get("/{penalty_id}", response_description="Get one penalty", response_model=PenaltiesDB)
async def get_one_penalty(
    request: Request,
    match_id: str = Path(..., description="The id of the match"),
    penalty_id: str = Path(..., description="The id of the penalty"),
    team_flag: str = Path(..., description="The flag of the team"),
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    service = PenaltyService(mongodb)
    
    penalty = await service.get_penalty_by_id(match_id, team_flag, penalty_id)
    return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(penalty))


# update one penalty
@router.patch("/{penalty_id}", response_description="Patch one penalty", response_model=PenaltiesDB)
async def patch_one_penalty(
    request: Request,
    match_id: str = Path(..., description="The id of the match"),
    penalty_id: str = Path(..., description="The id of the penalty"),
    team_flag: str = Path(..., description="The flag of the team"),
    penalty: PenaltiesUpdate = Body(
        ..., description="The penalty to be added to the penaltiesheet"
    ),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    service = PenaltyService(mongodb)
    
    updated_penalty = await service.update_penalty(match_id, team_flag, penalty_id, penalty)
    return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(updated_penalty))


# delete one penalty
@router.delete("/{penalty_id}", response_description="Delete one penalty")
async def delete_one_penalty(
    request: Request,
    match_id: str = Path(..., description="The id of the match"),
    penalty_id: str = Path(..., description="The id of the penalty"),
    team_flag: str = Path(..., description="The flag of the team"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> Response:
    mongodb = request.app.state.mongodb
    service = PenaltyService(mongodb)
    
    await service.delete_penalty(match_id, team_flag, penalty_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
