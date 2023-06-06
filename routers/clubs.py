from typing import List
from fastapi import APIRouter, Request, Body, status, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from models import ClubBase, ClubDB, ClubUpdate

router = APIRouter()

# list all clubs
@router.get("/", response_description="List all clubs")
async def list_venues(
    request: Request,
    # active: bool=True,
    page: int=1,
    ) -> List[ClubDB]:

    RESULTS_PER_PAGE = 50
    skip = (page - 1) * RESULTS_PER_PAGE
    # query = {"active":active}
    query = {}
    full_query = request.app.mongodb["clubs"].find(query).sort("name",1).skip(skip).limit(RESULTS_PER_PAGE)
    results = [ClubDB(**raw_club) async for raw_club in full_query]
    return results


# create new club
@router.post("/", response_description="Add new club")
async def create_club(request: Request, club: ClubBase = Body(...)):
    club = jsonable_encoder(club)
    new_club = await request.app.mongodb["clubs"].insert_one(club)
    created_club = await request.app.mongodb["clubs"].find_one(
        {"_id": new_club.inserted_id}
    )

    return JSONResponse(status_code=status.HTTP_201_CREATED, content=created_club)


# get club by ID
@router.get("/{id}", response_description="Get a single club")
async def get_club(id: str, request: Request):
    if (club := await request.app.mongodb["clubs"].find_one({"_id": id})) is not None:
        return ClubDB(**club)
    raise HTTPException(status_code=404, detail=f"Club with {id} not found")


# Update club
@router.patch("/{id}", response_description="Update club")
async def update_club(
    request: Request,
    id: str,
    club: ClubUpdate = Body(...)
    ):
    await request.app.mongodb['clubs'].update_one(
        {"_id": id}, {"$set": club.dict(exclude_unset=True)}
    )
    if (club := await request.app.mongodb['clubs'].find_one({"_id": id})) is not None:
        return ClubDB(**club)
    raise HTTPException(status_code=404, detail=f"Club with {id} not found")


# Delete club
@router.delete("/{id}", response_description="Delete club")
async def delete_club(
    request: Request,
    id: str
    ):
    result = await request.app.mongodb['clubs'].delete_one({"_id": id})
    if result.deleted_count == 1:
        return JSONResponse(status_code=status.HTTP_204_NO_CONTENT, content=None)
    raise HTTPException(status_code=404, detail=f"Club with {id} not found")
