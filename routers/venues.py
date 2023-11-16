import os
from typing import List
from fastapi import APIRouter, Request, Body, status, HTTPException, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from models.venues import VenueBase, VenueDB, VenueUpdate
from authentication import AuthHandler
from pymongo.errors import DuplicateKeyError

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


# get venue by Alias
@router.get("/{alias}", response_description="Get a single venue")
async def get_venue(alias: str, request: Request):
  if (venue := await
      request.app.mongodb["venues"].find_one({"alias": alias})) is not None:
    return VenueDB(**venue)
  raise HTTPException(status_code=404,
                      detail=f"Venue with alias {alias} not found")


# Update venue
@router.patch("/{id}", response_description="Update venue")
async def update_venue(
    request: Request,
    id: str,
    venue: VenueUpdate = Body(...),
    userId=Depends(auth.auth_wrapper),
):
  venue = venue.dict(exclude_unset=True)
  existing_venue = await request.app.mongodb['venues'].find_one({"_id": id})
  if existing_venue is None:
    raise HTTPException(status_code=404,
                        detail=f"Venue with id {id} not found")
  # Exclude unchanged data
  venue_to_update = {k: v for k, v in venue.items() if v != existing_venue.get(k)}

  if not venue_to_update:
    return VenueDB(**existing_venue)  # No update needed as no values have changed
  try:
    update_result = await request.app.mongodb['venues'].update_one(
      {"_id": id}, {"$set": venue_to_update})
    if update_result.modified_count == 1:
      if (updated_venue := await
          request.app.mongodb['venues'].find_one({"_id": id})) is not None:
        return VenueDB(**updated_venue)
    return VenueDB(**existing_venue)  # No update occurred if no attributes had different values
  except DuplicateKeyError:
    raise HTTPException(
      status_code=400,
      detail=
      f"Venue with name {venue.get('name', '')} already exists.")


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
