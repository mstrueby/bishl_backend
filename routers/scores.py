# filename: routers/scores.py
from fastapi import APIRouter, Body, Depends, Path, Request, status
from fastapi.responses import Response

from authentication import AuthHandler, TokenPayload
from models.matches import ScoresBase, ScoresDB, ScoresUpdate
from models.responses import StandardResponse
from services.score_service import ScoreService

router = APIRouter()
auth = AuthHandler()


# get score sheet of a team
@router.get("", response_description="Get score sheet", response_model=StandardResponse[list[ScoresDB]])
async def get_score_sheet(
    request: Request,
    match_id: str = Path(..., description="The ID of the match"),
    team_flag: str = Path(..., description="The team flag (home/away)"),
) -> StandardResponse[list[ScoresDB]]:
    mongodb = request.app.state.mongodb
    service = ScoreService(mongodb)

    score_entries = await service.get_scores(match_id, team_flag)
    return StandardResponse(
        success=True,
        data=score_entries,
        message=f"Retrieved {len(score_entries)} score entries for {team_flag} team"
    )


# create one score
@router.post("", response_description="Create one score", response_model=StandardResponse[ScoresDB], status_code=status.HTTP_201_CREATED)
async def create_score(
    request: Request,
    match_id: str = Path(..., description="The id of the match"),
    team_flag: str = Path(..., description="The flag of the team"),
    score: ScoresBase = Body(..., description="The score to be added to the scoresheet"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> StandardResponse[ScoresDB]:
    mongodb = request.app.state.mongodb
    service = ScoreService(mongodb)

    new_score = await service.create_score(match_id, team_flag, score)
    return StandardResponse(
        success=True,
        data=new_score,
        message="Score created successfully"
    )


# get one score
@router.get("/{score_id}", response_description="Get one score", response_model=StandardResponse[ScoresDB])
async def get_one_score(
    request: Request,
    match_id: str = Path(..., description="The id of the match"),
    score_id: str = Path(..., description="The id of the score"),
    team_flag: str = Path(..., description="The flag of the team"),
) -> StandardResponse[ScoresDB]:
    mongodb = request.app.state.mongodb
    service = ScoreService(mongodb)

    score = await service.get_score_by_id(match_id, team_flag, score_id)
    return StandardResponse(
        success=True,
        data=score,
        message="Score retrieved successfully"
    )


# update one score
@router.patch("/{score_id}", response_description="Patch one score", response_model=StandardResponse[ScoresDB])
async def patch_one_score(
    request: Request,
    match_id: str = Path(..., description="The id of the match"),
    score_id: str = Path(..., description="The id of the score"),
    team_flag: str = Path(..., description="The flag of the team"),
    score: ScoresUpdate = Body(..., description="The score to be added to the scoresheet"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> StandardResponse[ScoresDB]:
    mongodb = request.app.state.mongodb
    service = ScoreService(mongodb)

    updated_score = await service.update_score(match_id, team_flag, score_id, score)
    return StandardResponse(
        success=True,
        data=updated_score,
        message="Score updated successfully"
    )


# delete one score
@router.delete("/{score_id}", response_description="Delete one score", status_code=status.HTTP_204_NO_CONTENT)
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
