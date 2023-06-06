from typing import List
from fastapi import APIRouter, Request, Body, status, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from models import VenueBase, VenueDB, VenueUpdate

router = APIRouter()

# list all venues
@router.get("/", response_description="List all venues")
async def list_venues(
    request: Request,
    # active: bool=True,
    page: int=1,
    ) -> List[VenueDB]:

    RESULTS_PER_PAGE = 50
    skip = (page - 1) * RESULTS_PER_PAGE
    # query = {"active":active}
    query = {}
    full_query = request.app.mongodb["venues"].find(query).sort("name",1).skip(skip).limit(RESULTS_PER_PAGE)
    results = [VenueDB(**raw_venue) async for raw_venue in full_query]
    return results


# create new venue
@router.post("/", response_description="Add new venue")
async def create_venue(request: Request, venue: VenueBase = Body(...)):
    venue = jsonable_encoder(venue)
    new_venue = await request.app.mongodb["venues"].insert_one(venue)
    created_venue = await request.app.mongodb["venues"].find_one(
        {"_id": new_venue.inserted_id}
    )

    return JSONResponse(status_code=status.HTTP_201_CREATED, content=created_venue)


# get venue by ID
@router.get("/{id}", response_description="Get a single venue")
async def get_venue(id: str, request: Request):
    if (venue := await request.app.mongodb["venues"].find_one({"_id": id})) is not None:
        return VenueDB(**venue)
    raise HTTPException(status_code=404, detail=f"Venue with {id} not found")


# Update venue
@router.patch("/{id}", response_description="Update venue")
async def update_venue(
    request: Request,
    id: str,
    venue: VenueUpdate = Body(...)
    ):
    await request.app.mongodb['venues'].update_one(
        {"_id": id}, {"$set": venue.dict(exclude_unset=True)}
    )
    if (venue := await request.app.mongodb['venues'].find_one({"_id": id})) is not None:
        return VenueDB(**venue)
    raise HTTPException(status_code=404, detail=f"Venue with {id} not found")


# Delete venue
@router.delete("/{id}", response_description="Delete venue")
async def delete_venue(
    request: Request,
    id: str
    ):
    result = await request.app.mongodb['venues'].delete_one({"_id": id})
    if result.deleted_count == 1:
        return JSONResponse(status_code=status.HTTP_204_NO_CONTENT, content=None)
    raise HTTPException(status_code=404, detail=f"Venue with {id} not found")
