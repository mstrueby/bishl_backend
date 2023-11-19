import os
from typing import List
from fastapi import APIRouter, Request, Body, status, HTTPException, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from models.clubs import ClubBase, ClubDB, ClubUpdate
from authentication import AuthHandler
from pymongo.errors import DuplicateKeyError

router = APIRouter()
auth = AuthHandler()


# list all clubs
@router.get("/", response_description="List all clubs")
async def list_venues(
  request: Request,
  # active: bool=True,
  page: int = 1,
) -> List[ClubDB]:
  RESULTS_PER_PAGE = int(os.environ['RESULTS_PER_PAGE'])
  skip = (page - 1) * RESULTS_PER_PAGE
  # query = {"active":active}
  query = {}
  full_query = request.app.mongodb["clubs"].find(query).sort(
    "name", 1).skip(skip).limit(RESULTS_PER_PAGE)
  results = [ClubDB(**raw_club) async for raw_club in full_query]
  return results


# create new club
@router.post("/", response_description="Add new club")
async def create_club(
    request: Request,
    club: ClubBase = Body(...),
    userId=Depends(auth.auth_wrapper),
):
  club = jsonable_encoder(club)

  try:
    new_club = await request.app.mongodb["clubs"].insert_one(club)
    created_club = await request.app.mongodb["clubs"].find_one(
      {"_id": new_club.inserted_id})
    return JSONResponse(status_code=status.HTTP_201_CREATED,
                        content=created_club)
  except DuplicateKeyError:
    raise HTTPException(status_code=400,
                        detail=f"Club {club['name']} already exists.")


# get club by Alias
@router.get("/{alias}", response_description="Get a single club")
async def get_club(alias: str, request: Request):
  if (club := await
      request.app.mongodb["clubs"].find_one({"alias": alias})) is not None:
    return ClubDB(**club)
  raise HTTPException(status_code=404,
                      detail=f"Club with alias {alias} not found")


# Update club
@router.patch("/{id}", response_description="Update club")
async def update_club(
    request: Request,
    id: str,
    club: ClubUpdate = Body(...),
    userId=Depends(auth.auth_wrapper),
):
  club = club.dict(exclude_unset=True)
  exisitng_club = await request.app.mongodb["clubs"].find_one({"_id": id})
  if exisitng_club is None:
    raise HTTPException(status_code=404, detail=f"Club with id {id} not found")
  #Exclude unchanged data
  club_to_update = {k: v for k, v in club.items() if v != exisitng_club.get(k)}
  if not club_to_update:
    return ClubDB(**exisitng_club)
  try:

    update_result = await request.app.mongodb["clubs"].update_one(
      {"_id": id}, {"$set": club_to_update})
    if update_result.modified_count == 1:
      if (updatd_club := await
          request.app.mongodb["clubs"].find_one({"_id": id})) is not None:

        return ClubDB(**updatd_club)
    return ClubDB(**exisitng_club)
  except DuplicateKeyError:
    raise HTTPException(
      status_code=400,
      detail=f"Club with name {club.get('name', '')} already exists.")


# Delete club
@router.delete("/{alias}", response_description="Delete club")
async def delete_club(
    request: Request,
    alias: str,
    userId=Depends(auth.auth_wrapper),
):
  result = await request.app.mongodb['clubs'].delete_one({"alias": alias})
  if result.deleted_count == 1:
    return JSONResponse(status_code=status.HTTP_204_NO_CONTENT, content=None)
  raise HTTPException(status_code=404,
                      detail=f"Club with alias {alias} not found")
