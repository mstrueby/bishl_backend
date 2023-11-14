import os
from typing import List
from fastapi import APIRouter, Request, Body, status, HTTPException, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from models.venues import VenueBase, VenueDB, VenueUpdate
from authentication import AuthHandler
from pymongo.errors import DuplicateKeyError  # Added import here

router = APIRouter()
auth = AuthHandler()


# list all venues
@router.get("/", response_description="List all venues")
async def list_venues(
  request: Request,
  # active: bool=True,
  page: int = 1,
) -> List[VenueDB]:

  RESULTS_PER_PAGE = int(os.environ['RESULTS_PER_PAGE'])
  skip = (page - 1) * RESULTS_PER_PAGE
  # query = {"active":active}
  query = {}
  full_query = request.app.mongodb["venues"].find(query).sort(
    "name", 1).skip(skip).limit(RESULTS_PER_PAGE)
  results = [VenueDB(**raw_venue) async for raw_venue in full_query]
  return results


# create new venue
@router.post("/", response_description="Add new venue")
async def create_venue(
    request: Request,
    venue: VenueBase = Body(...),
    userId=Depends(auth.auth_wrapper),
):
  venue = jsonable_encoder(venue)

  try:
    new_venue = await request.app.mongodb["venues"].insert_one(venue)
    created_venue = await request.app.mongodb["venues"].find_one(
      {"_id": new_venue.inserted_id})
    return JSONResponse(status_code=status.HTTP_201_CREATED,
                        content=created_venue)
  except DuplicateKeyError:
    raise HTTPException(status_code=400,
                        detail=f"Venue {venue['name']} already exists.")


# get venue by ID
@router.get("/{alias}", response_description="Get a single venue")
async def get_venue(alias: str, request: Request):
  if (venue := await
      request.app.mongodb["venues"].find_one({"alias": alias})) is not None:
    return VenueDB(**venue)
  raise HTTPException(status_code=404,
                      detail=f"Venue with alias {alias} not found")


# Update venue
@router.patch("/{alias}", response_description="Update venue")
async def update_venue(
    request: Request,
    alias: str,
    venue: VenueUpdate = Body(...),
    userId=Depends(auth.auth_wrapper),
):
  try:
    update_result = await request.app.mongodb['venues'].update_one(
      {"alias": alias}, {"$set": venue.dict(exclude_unset=True)})

    if update_result.modified_count == 1:
      if (updated_venue := await request.app.mongodb['venues'].find_one({"alias": alias})) is not None:
        return VenueDB(**updated_venue)

    if (existing_venue := await request.app.mongodb['venues'].find_one({"alias": alias})) is not None:
      return existing_venue

    raise HTTPException(status_code=404, detail=f"Venue with alias {alias} not found")
  
  except DuplicateKeyError:
    raise HTTPException(status_code=400, detail=f"Update failed: another venue with name {venue.name} already exists.")
    

# Delete venue
@router.delete("/{alias}", response_description="Delete venue")
async def delete_venue(
    request: Request,
    alias: str,
    userId=Depends(auth.auth_wrapper),
):
  result = await request.app.mongodb['venues'].delete_one({"alias": alias})
  if result.deleted_count == 1:
    return JSONResponse(status_code=status.HTTP_204_NO_CONTENT, content=None)
  raise HTTPException(status_code=404,
                      detail=f"Venue with alias {alias} not found")
