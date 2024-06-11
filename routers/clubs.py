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
from authentication import AuthHandler
from pymongo.errors import DuplicateKeyError
import cloudinary
import cloudinary.uploader

# Cloudinary Image processing
CLOUD_NAME = os.environ["CLDY_CLOUD_NAME"]
API_KEY = os.environ["CLDY_API_KEY"]
API_SECRET = os.environ["CLDY_API_SECRET"]
cloudinary.config(
  cloud_name=CLOUD_NAME,
  api_key=API_KEY,
  api_secret=API_SECRET,
)

router = APIRouter()
auth = AuthHandler()


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
@router.post("/", response_description="Add new club")
async def create_club(
    request: Request,
    name: str = Form(...),
    alias: str = Form(...),
    addressName: Optional[str] = Form(None),
    street: Optional[str] = Form(None),
    zipCode: Optional[str] = Form(None),
    city: Optional[str] = Form(None),
    country: str = Form(...),
    email: Optional[str] = Form(None),
    yearOfFoundation: Optional[int] = Form(None),
    description: Optional[str] = Form(None),
    website: Optional[str] = Form(None),
    ishdId: Optional[int] = Form(None),
    active: Optional[bool] = Form(False),
    logo: Optional[UploadFile] = File(None),
    userId=Depends(auth.auth_wrapper),
) -> ClubDB:
  if logo:
    result = cloudinary.uploader.upload(
      logo.file,
      folder="logos",
      public_id=f"{alias}",
      overwrite=True,
      crop="scale",
      height=200,
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
    yearOfFoundation=yearOfFoundation,
    description=description,
    website=website,
    ishdId=ishdId,
    active=active,
    logo=url,
  )
  club = jsonable_encoder(club)
  print("add club: ", club)

  # DB processing
  try:
    new_club = await request.app.mongodb["clubs"].insert_one(club)
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
                        detail=f"Club {club['name']} already exists.")
  except Exception as e:
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=str(e))


# Update club
@router.patch("/{id}", response_description="Update club")
async def update_club(
    request: Request,
    id: str,
    name: str = Form(None),
    alias: str = Form(None),
    addressName: Optional[str] = Form(None),
    street: Optional[str] = Form(None),
    zipCode: Optional[str] = Form(None),
    city: Optional[str] = Form(None),
    country: str = Form(None),
    email: Optional[str] = Form(None),
    yearOfFoundation: Optional[int] = Form(None),
    description: Optional[str] = Form(None),
    website: Optional[str] = Form(None),
    ishdId: Optional[int] = Form(None),
    active: Optional[bool] = Form(False),
    logo: Optional[UploadFile] = File(None),
    userId=Depends(auth.auth_wrapper),
) -> ClubDB:
  print("logo: " + str(logo))

  if logo:
    result = cloudinary.uploader.upload(
      logo.file,
      folder="logos",
      public_id=f"{alias}",
      overwrite=True,
      crop="fit",
      height=200,
    )
    url = result.get("url")
  else:
    url = None

  club = {
    "name": name,
    "alias": alias,
    "addressName": addressName,
    "street": street,
    "zipCode": zipCode,
    "city": city,
    "country": country,
    "email": email,
    "yearOfFoundation": yearOfFoundation,
    "description": description,
    "website": website,
    "ishdId": ishdId,
    "active": active,
    # If url is None, do not include it in club_data
  }
  if url is not None:
    club["logo"] = url

  try:
    club = ClubUpdate(**club)
    club = club.dict(exclude_unset=True)
    club.pop("id", None)
  except:
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="Invalid club data")
      
  print("club: ", club)

  existing_club = await request.app.mongodb["clubs"].find_one({"_id": id})
  if existing_club is None:
    raise HTTPException(status_code=404, detail=f"Club with id {id} not found")
  #del club_to_update["_id"]
  #club_to_update = ClubBase(**club)
  #Exclude unchanged data
  club_to_update = {
    k: v
    for k, v in club.items() if v != existing_club.get(k)
  }
  #club_to_update = club_to_update.dict(exclude_unset=True)


  # If logo was not updated, remove it from the update
  if url is None and 'logo' in club_to_update:
    del club_to_update['logo']

  if not club_to_update:
    print("No update needed")
    return ClubDB(**existing_club)
  try:
    print('club_to_update: ' + str(club_to_update))
    update_result = await request.app.mongodb["clubs"].update_one(
      {"_id": id}, {"$set": club_to_update})
    if update_result.modified_count == 1:
      if (updated_club := await
          request.app.mongodb["clubs"].find_one({"_id": id})) is not None:
        return ClubDB(**updated_club)
    return ClubDB(**existing_club)
  except DuplicateKeyError:
    raise HTTPException(
      status_code=400,
      detail=f"Club {club.get('name', '')} already exists.")
  except Exception as e:
    raise HTTPException(status_code=500,
                        detail=f"An unexpected error occurred: {str(e)}")


# Delete club
@router.delete("/{alias}", response_description="Delete club")
async def delete_club(
    request: Request,
    alias: str,
    userId=Depends(auth.auth_wrapper),
) -> None:
  result = await request.app.mongodb['clubs'].delete_one({"alias": alias})
  if result.deleted_count == 1:
    return Response(status_code=status.HTTP_204_NO_CONTENT)
  raise HTTPException(status_code=404,
                      detail=f"Club with alias {alias} not found")
