import os
from typing import List
from fastapi import APIRouter, Request, Body, status, HTTPException, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from models.venues import VenueBase, VenueDB, VenueUpdate
from authentication import AuthHandler, TokenPayload
from pymongo.errors import DuplicateKeyError

router = APIRouter()
auth = AuthHandler()


# list all venues
@router.get("/",
            response_description="List all venues",
            response_model=List[VenueDB])
async def list_venues(
    request: Request,
    # active: bool=True,
    page: int = 1,
) -> JSONResponse:
  mongodb = request.app.state.mongodb
  RESULTS_PER_PAGE = int(os.environ['RESULTS_PER_PAGE'])
  skip = (page - 1) * RESULTS_PER_PAGE
  # query = {"active":active}
  query = {}
  full_query = await mongodb["venues"].find(query).sort(
      "name", 1).skip(skip).limit(RESULTS_PER_PAGE).to_list(length=None)
  venues = [VenueDB(**raw_venue) for raw_venue in full_query]
  return JSONResponse(status_code=status.HTTP_200_OK,
                      content=jsonable_encoder(venues))


# get venue by Alias
@router.get("/{alias}",
            response_description="Get a single venue",
            response_model=VenueDB)
async def get_venue(alias: str, request: Request) -> JSONResponse:
  mongodb = request.app.state.mongodb
  if (venue := await mongodb["venues"].find_one({"alias": alias})) is not None:
    return JSONResponse(status_code=status.HTTP_200_OK,
                        content=jsonable_encoder(VenueDB(**venue)))
  raise HTTPException(status_code=404,
                      detail=f"Venue with alias {alias} not found")


# create new venue
@router.post("/", response_description="Add new venue", response_model=VenueDB)
async def create_venue(
    request: Request,
    venue: VenueBase = Body(...),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> JSONResponse:
  mongodb = request.app.state.mongodb
  if token_payload.roles not in [["ADMIN"]]:
    raise HTTPException(status_code=403, detail="Not authorized")
  venue_data = jsonable_encoder(venue)

  # DB processing
  try:
    new_venue = await mongodb["venues"].insert_one(venue_data)
    created_venue = await mongodb["venues"].find_one(
        {"_id": new_venue.inserted_id})
    if created_venue:
      return JSONResponse(status_code=status.HTTP_201_CREATED,
                          content=jsonable_encoder(VenueDB(**created_venue)))
    else:
      raise HTTPException(status_code=500, detail="Failed to create venue")
  except DuplicateKeyError:
    raise HTTPException(
        status_code=400,
        detail=f"Venue {venue_data.get('name', 'Unknown')} already exists.")
  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))


# Update venue
@router.patch("/{id}",
              response_description="Update venue",
              response_model=VenueDB)
async def update_venue(
    request: Request,
    id: str,
    venue: VenueUpdate = Body(...),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
):
  mongodb = request.app.state.mongodb
  if token_payload.roles not in [["ADMIN"]]:
    raise HTTPException(status_code=403, detail="Not authorized")
  venue_data = venue.dict(exclude_unset=True)
  venue_data.pop("id", None)

  print("venue_data: ", venue_data)
  existing_venue = await mongodb['venues'].find_one({"_id": id})
  if existing_venue is None:
    raise HTTPException(status_code=404,
                        detail=f"Venue with id {id} not found")
  # Exclude unchanged data
  venue_to_update = {
      k: v
      for k, v in venue_data.items() if v != existing_venue.get(k)
  }

  if not venue_to_update:
    print("No update needed")
    return Response(status_code=status.HTTP_304_NOT_MODIFIED)
  try:
    print('venue_to_update: ' + str(venue_to_update))
    update_result = await mongodb['venues'].update_one(
        {"_id": id}, {"$set": venue_to_update})
    if update_result.modified_count == 1:
      if (updated_venue := await mongodb['venues'].find_one({"_id":
                                                             id})) is not None:
        return JSONResponse(status_code=status.HTTP_200_OK,
                            content=jsonable_encoder(VenueDB(**updated_venue)))
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        content="Failed to update venue")
  except DuplicateKeyError:
    raise HTTPException(
        status_code=400,
        detail=f"Venue with name {venue_data.get('name', '')} already exists.")
  except Exception as e:
    raise HTTPException(status_code=500,
                        detail=f"An unexpected error occurred: {str(e)}")


# Delete venue
@router.delete("/{alias}", response_description="Delete venue")
async def delete_venue(
    request: Request,
    alias: str,
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> Response:
  mongodb = request.app.state.mongodb
  if token_payload.roles not in [["ADMIN"]]:
    raise HTTPException(status_code=403, detail="Not authorized")
  result = await mongodb['venues'].delete_one({"alias": alias})
  if result.deleted_count == 1:
    return Response(status_code=status.HTTP_204_NO_CONTENT)
  raise HTTPException(status_code=404,
                      detail=f"Venue with alias {alias} not found")
