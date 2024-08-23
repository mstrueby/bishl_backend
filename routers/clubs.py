import os
from typing import List, Optional
from fastapi import (
  APIRouter,
  Request,
  status,
  HTTPException,
  Depends,
  Form,
  File,
  UploadFile,
)
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from models.clubs import ClubBase, ClubDB, ClubUpdate
from authentication import AuthHandler, TokenPayload
from pymongo.errors import DuplicateKeyError
from utils import configure_cloudinary
import cloudinary
import cloudinary.uploader

router = APIRouter()
auth = AuthHandler()
configure_cloudinary()


async def handle_logo_upload(logo: UploadFile, public_id: str) -> str:
  if logo:
    return cloudinary.uploader.upload(
      logo.file,
      folder="logos",
      public_id=f"{public_id}",
      overwrite=True,
      crop="scale",
      height=200,
    )['url']
  return None


# list all clubs
@router.get("/", response_description="List all clubs")
async def list_clubs(
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


# get club by Alias
@router.get("/{alias}", response_description="Get a single club")
async def get_club(alias: str, request: Request) -> ClubDB:
  if (club := await
      request.app.mongodb["clubs"].find_one({"alias": alias})) is not None:
    return ClubDB(**club)
  raise HTTPException(status_code=404,
                      detail=f"Club with alias {alias} not found")


# create new club
@router.post("/", response_model=ClubDB, response_description="Add new club")
async def create_club(
    request: Request,
    name: str = Form(...),
    alias: str = Form(...),
    addressName: str = Form(None),
    street: str = Form(None),
    zipCode: str = Form(None),
    city: str = Form(None),
    country: str = Form(...),
    email: str = Form(None),
    yearOfFoundation: int = Form(None),
    description: str = Form(None),
    website: str = Form(None),
    ishdId: int = Form(None),
    active: bool = Form(False),
    logo: UploadFile = File(None),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> ClubDB:
  if token_payload.roles not in [["ADMIN"]]:
    raise HTTPException(status_code=403, detail="Not authorized")

  club = ClubBase(
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
  )
  club_data = jsonable_encoder(club)

  club_data['logo'] = await handle_logo_upload(logo, alias)

  # insert club
  try:
    print("club_data: ", club_data)
    new_club = await request.app.mongodb["clubs"].insert_one(club_data)
    created_club = await request.app.mongodb["clubs"].find_one(
      {"_id": new_club.inserted_id})
    if created_club:
      return JSONResponse(status_code=status.HTTP_201_CREATED,
                          content=jsonable_encoder(ClubDB(**created_club)))
    else:
      raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                          detail="Failed to create club")
  except DuplicateKeyError:
    raise HTTPException(status_code=400,
                        detail=f"Club {club_data['name']} already exists.")
  except Exception as e:
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=str(e))


# Update club
@router.patch("/{id}",
              response_model=ClubDB,
              response_description="Update club")
async def update_club(
    request: Request,
    id: str,
    name: str = Form(...),
    alias: str = Form(...),
    addressName: str = Form(None),
    street: str = Form(None),
    zipCode: str = Form(None),
    city: str = Form(None),
    country: str = Form(...),
    email: str = Form(None),
    yearOfFoundation: int = Form(None),
    description: str = Form(None),
    website: str = Form(None),
    ishdId: int = Form(None),
    active: bool = Form(False),
    logo: UploadFile = File(None),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> ClubDB:
  if token_payload.roles not in [["ADMIN"]]:
    raise HTTPException(status_code=403, detail="Not authorized")

  club_data = ClubUpdate(
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
    active=active
  ).dict(exclude_unset=True)

  # retrieve existing club
  existing_club = await request.app.mongodb["clubs"].find_one({"_id": id})
  if not existing_club:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                        details=f"Club with id {id} not found")

  club_data['logo'] = await handle_logo_upload(logo, existing_club['alias'])

  print("club_data: ", club_data)

  #Exclude unchanged data
  club_to_update = {
    k: v
    for k, v in club_data.items() if v != existing_club.get(k, None)
  }
  print("club_to__update", club_to_update)
  if not club_to_update:
    print("No changes to update")
    return JSONResponse(status_code=status.HTTP_200_OK,
                        content=jsonable_encoder(ClubDB(**existing_club)))
  # update club
  try:
    update_result = await request.app.mongodb["clubs"].update_one(
      {"_id": id}, {"$set": club_to_update})
    if update_result.modified_count == 1:
      updated_club = await request.app.mongodb["clubs"].find_one({"_id": id})
      return JSONResponse(status_code=status.HTTP_200_OK,
                          content=jsonable_encoder(ClubDB(**updated_club)))
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        content="Failed to update club")
  except DuplicateKeyError:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Club {club_data.get('name', '')} already exists.")
  except Exception as e:
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=str(e))


# Delete club
@router.delete("/{alias}", response_description="Delete club")
async def delete_club(
    request: Request,
    alias: str,
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> None:
  if token_payload.roles not in [["ADMIN"]]:
    raise HTTPException(status_code=403, detail="Not authorized")
  result = await request.app.mongodb['clubs'].delete_one({"alias": alias})
  if result.deleted_count == 1:
    return Response(status_code=status.HTTP_204_NO_CONTENT)
  raise HTTPException(status_code=404,
                      detail=f"Club with alias {alias} not found")
