import os
from typing import List
from fastapi import APIRouter, Request, Body, status, HTTPException, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
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


# get venue by Alias
@router.get("/{alias}", response_description="Get a single venue")
async def get_venue(alias: str, request: Request) -> VenueDB:
  if (venue := await
      request.app.mongodb["venues"].find_one({"alias": alias})) is not None:
    return VenueDB(**venue)
  raise HTTPException(status_code=404,
                      detail=f"Venue with alias {alias} not found")


# create new venue
@router.post("/", response_description="Add new venue")
async def create_venue(
    request: Request,
    venue: VenueBase = Body(...),
    userId=Depends(auth.auth_wrapper),
) -> VenueDB:
  venue = jsonable_encoder(venue)

  # DB processing
  try:
    new_venue = await request.app.mongodb["venues"].insert_one(venue)
    created_venue = await request.app.mongodb["venues"].find_one(
      {"_id": new_venue.inserted_id})
    if created_venue:
      return JSONResponse(status_code=status.HTTP_201_CREATED,
                          content=jsonable_encoder(VenueDB(**created_venue)))
    else:
      raise HTTPException(status_code=500, detail="Failed to create venue")
  except DuplicateKeyError:
    raise HTTPException(status_code=400,
                        detail=f"Venue {venue['name']} already exists.")
  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))


# Update venue
@router.patch("/{id}", response_description="Update venue")
async def update_venue(
    request: Request,
    id: str,
    venue: VenueUpdate = Body(...),
    userId=Depends(auth.auth_wrapper),
) -> VenueDB:
  venue = venue.dict(exclude_unset=True)
  venue.pop("id", None)
  
  print("venue: ", venue)
  existing_venue = await request.app.mongodb['venues'].find_one({"_id": id})
  if existing_venue is None:
    raise HTTPException(status_code=404,
                        detail=f"Venue with id {id} not found")
  # Exclude unchanged data
  venue_to_update = {
    k: v
    for k, v in venue.items() if v != existing_venue.get(k)
  }

  if not venue_to_update:
    print("No update needed")
    return VenueDB(
      **existing_venue)  # No update needed as no values have changed
  try:
    print('venue_to_update: ' + str(venue_to_update))
    update_result = await request.app.mongodb['venues'].update_one(
      {"_id": id}, {"$set": venue_to_update})
    if update_result.modified_count == 1:
      if (updated_venue := await
          request.app.mongodb['venues'].find_one({"_id": id})) is not None:
        return VenueDB(**updated_venue)
    return VenueDB(**existing_venue)
  except DuplicateKeyError:
    raise HTTPException(
      status_code=400,
      detail=f"Venue with name {venue.get('name', '')} already exists.")
  except Exception as e:
    raise HTTPException(status_code=500,
                        detail=f"An unexpected error occurred: {str(e)}")


# Delete venue
@router.delete("/{alias}", response_description="Delete venue")
async def delete_venue(
    request: Request,
    alias: str,
    userId=Depends(auth.auth_wrapper),
) -> None:
  result = await request.app.mongodb['venues'].delete_one({"alias": alias})
  if result.deleted_count == 1:
    return Response(status_code=status.HTTP_204_NO_CONTENT)
  raise HTTPException(status_code=404,
                      detail=f"Venue with alias {alias} not found")
