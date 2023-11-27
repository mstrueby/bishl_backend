import os
from typing import List, Optional
from fastapi import (
  APIRouter,
  Request,
  Body,
  status,
  HTTPException,
  Depends,
  Form,
  File,
  UploadFile,
)
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from models.clubs import ClubBase, ClubDB, ClubUpdate
from authentication import AuthHandler
from pymongo.errors import DuplicateKeyError
import cloudinary
import cloudinary.uploader

CLOUD_NAME = os.getenv("CLDY_CLOUD_NAME")
API_KEY = os.getenv("CLDY_API_KEY")
API_SECRET = os.getenv("CLDY_API_SECRET")
cloudinary.config(
  cloud_name=CLOUD_NAME,
  api_key=API_KEY,
  api_secret=API_SECRET,
)

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
  #club: ClubBase = Body(...),
  name: str = Form("name"),
  alias: str = Form("alias"),
  addressName: Optional[str] = Form(None),
  street: Optional[str] = Form(None),
  zipCode: Optional[str] = Form(None),
  city: Optional[str] = Form(None),
  country: str = Form("country"),
  email: Optional[str] = Form(None),
  yearOfFoundation: Optional[int] = Form(None),
  description: Optional[str] = Form(None),
  website: Optional[str] = Form(None),
  ishdId: Optional[int] = Form(None),
  active: Optional[bool] = Form(False),
  logo: Optional[UploadFile] = File(None),
  
  userId=Depends(auth.auth_wrapper),
):
  if logo:
    result = cloudinary.uploader.upload(
      logo.file,
      folder="logos",
      public_id=f"{alias}",
      overwrite=True,
      crop="scale",
      height=300,
    )
    url = result.get("url")
  else:
    url = None

  club = ClubDB(
    name=name,
    alias=alias,
    addressName=addressName,
    street=street,
    zipCode=zipCode,
    city=city,
    country=country,
    email=email,
    # if yearOfFoundation is empty, set it to None
    yearOfFoundation = yearOfFoundation,
    description=description,
    website=website,
    ishdId=ishdId,
    active=active,
    logo=url,
  )
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
  #club: ClubBase = Body(...),
  name: str = Form("name"),
  alias: str = Form("alias"),
  addressName: str = Form("addressName"),
  street: str = Form("street"),
  zipCode: str = Form("zipCode"),
  city: str = Form("city"),
  country: str = Form("country"),
  email: str = Form("email"),
  yearOfFoundation: int = Form("yearOfFoundation"),
  description: str = Form("description"),
  website: str = Form("website"),
  ishdId: int = Form("ishdId"),
  active: bool = Form("active"),
  logo: UploadFile = File(...),

  userId=Depends(auth.auth_wrapper),
):
  result = cloudinary.uploader.upload(
    logo.file,
    folder="logos",
    public_id=f"{alias}",
    overwrite=True,
    crop="scale",
    height=300,
  )
  url = result.get("url")
  
  club = ClubDB(
    name=name,
    alias=alias,
    addressName=addressName,
    street=street,
    zipCode=zipCode,
    city=city,
    country=country,
    email=email,
    yearOfFoundation=yearOfFoundation,
    description=description,
    website=website,
    ishdId=ishdId,
    active=active,
    logo=url,
  )
  club = jsonable_encoder(club)
  
  exisitng_club = await request.app.mongodb["clubs"].find_one({"_id": id})
  if exisitng_club is None:
    raise HTTPException(status_code=404, detail=f"Club with id {id} not found")
  #Exclude unchanged data
  club_to_update = {k: v for k, v in club.items() if v != exisitng_club.get(k) and k != '_id'}
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
