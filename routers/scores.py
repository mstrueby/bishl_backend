# filename: routers/scores.py
from fastapi import APIRouter, Body, Depends, Path, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response

from authentication import AuthHandler, TokenPayload
from models.matches import ScoresBase, ScoresDB, ScoresUpdate
from services.score_service import ScoreService

router = APIRouter()
auth = AuthHandler()


# get score sheet of a team
@router.get("/", response_description="Get score sheet", response_model=list[ScoresDB])
async def get_score_sheet(
    request: Request,
    match_id: str = Path(..., description="The ID of the match"),
    team_flag: str = Path(..., description="The team flag (home/away)"),
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    service = ScoreService(mongodb)

    score_entries = await service.get_scores(match_id, team_flag)
    return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(score_entries))


# create one score
@router.post("/", response_description="Create one score", response_model=ScoresDB)
async def create_score(
    request: Request,
    match_id: str = Path(..., description="The id of the match"),
    team_flag: str = Path(..., description="The flag of the team"),
    score: ScoresBase = Body(..., description="The score to be added to the scoresheet"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    service = ScoreService(mongodb)

    new_score = await service.create_score(match_id, team_flag, score)
    return JSONResponse(
        status_code=status.HTTP_201_CREATED, content=jsonable_encoder(new_score)
    )


# get one score
@router.get("/{score_id}", response_description="Get one score", response_model=ScoresDB)
async def get_one_score(
    request: Request,
    match_id: str = Path(..., description="The id of the match"),
    score_id: str = Path(..., description="The id of the score"),
    team_flag: str = Path(..., description="The flag of the team"),
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    service = ScoreService(mongodb)

    score = await service.get_score_by_id(match_id, team_flag, score_id)
    return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(score))


# update one score
@router.patch("/{score_id}", response_description="Patch one score", response_model=ScoresDB)
async def patch_one_score(
    request: Request,
    match_id: str = Path(..., description="The id of the match"),
    score_id: str = Path(..., description="The id of the score"),
    team_flag: str = Path(..., description="The flag of the team"),
    score: ScoresUpdate = Body(..., description="The score to be added to the scoresheet"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> Response:
    mongodb = request.app.state.mongodb
    service = ScoreService(mongodb)

    updated_score = await service.update_score(match_id, team_flag, score_id, score)
    return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(updated_score))


# delete one score
@router.delete("/{score_id}", response_description="Delete one score")
async def delete_one_score(
    request: Request,
    match_id: str = Path(..., description="The id of the match"),
    score_id: str = Path(..., description="The id of the score"),
    team_flag: str = Path(..., description="The flag of the team"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> Response:
    mongodb = request.app.state.mongodb
    service = ScoreService(mongodb)

    await service.delete_score(match_id, team_flag, score_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)