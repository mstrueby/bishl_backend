from typing import List
from fastapi import APIRouter, Request, Body, status, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from models import TeamBase, TeamDB, TeamUpdate

router = APIRouter()

# list all teams
@router.get("/", response_description="List all teams")
async def list_teams(
    request: Request,
    # active: bool=True,
    page: int=1,
    ) -> List[TeamDB]:

    RESULTS_PER_PAGE = 50
    skip = (page - 1) * RESULTS_PER_PAGE
    # query = {"active":active}
    query = {}
    full_query = request.app.mongodb["teams"].find(query).sort("name",1).skip(skip).limit(RESULTS_PER_PAGE)
    results = [TeamDB(**raw_team) async for raw_team in full_query]
    return results


# create new team
@router.post("/", response_description="Add new team")
async def create_team(request: Request, team: TeamBase = Body(...)):
    team = jsonable_encoder(team)
    new_team = await request.app.mongodb["teams"].insert_one(team)
    created_team = await request.app.mongodb["teams"].find_one(
        {"_id": new_team.inserted_id}
    )

    return JSONResponse(status_code=status.HTTP_201_CREATED, content=created_team)


# get team by ID
@router.get("/{id}", response_description="Get a single team")
async def get_team(id: str, request: Request):
    if (team := await request.app.mongodb["teams"].find_one({"_id": id})) is not None:
        return TeamDB(**team)
    raise HTTPException(status_code=404, detail=f"Club with {id} not found")


# Update team
@router.patch("/{id}", response_description="Update team")
async def update_team(
    request: Request,
    id: str,
    team: TeamUpdate = Body(...)
    ):
    await request.app.mongodb['teams'].update_one(
        {"_id": id}, {"$set": team.dict(exclude_unset=True)}
    )
    if (team := await request.app.mongodb['teams'].find_one({"_id": id})) is not None:
        return TeamDB(**team)
    raise HTTPException(status_code=404, detail=f"Club with {id} not found")


# Delete team
@router.delete("/{id}", response_description="Delete team")
async def delete_team(
    request: Request,
    id: str
    ):
    result = await request.app.mongodb['teams'].delete_one({"_id": id})
    if result.deleted_count == 1:
        return JSONResponse(status_code=status.HTTP_204_NO_CONTENT, content=None)
    raise HTTPException(status_code=404, detail=f"Club with {id} not found")
