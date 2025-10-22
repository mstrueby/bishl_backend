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
from pydantic import EmailStr, HttpUrl
from utils import configure_cloudinary
from exceptions import (
    ResourceNotFoundException,
    DatabaseOperationException,
    AuthorizationException
)
from logging_config import logger
import cloudinary
import cloudinary.uploader

router = APIRouter()
auth = AuthHandler()
configure_cloudinary()


# upload file
async def handle_logo_upload(logo: UploadFile, alias: str) -> str:
  if logo:
    result = cloudinary.uploader.upload(
        logo.file,
        folder="logos/",
        public_id=alias,
        overwrite=True,
        crop="scale",
        height=200,
    )
    print(f"Logo uploaded to Cloudinary: {result['public_id']}")
    return result["secure_url"]
  raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                      detail="No logo uploaded.")


# Helper function to delete file from Cloudinary
async def delete_from_cloudinary(logo_url: str):
  if logo_url:
    try:
      public_id = logo_url.rsplit('/', 1)[-1].split('.')[0]
      result = cloudinary.uploader.destroy(f"logos/{public_id}")
      print("Logo deleted from Cloudinary:", f"logos/{public_id}")
      print("Result:", result)
      return result
    except Exception as e:
      raise HTTPException(status_code=500, detail=str(e))


# list all clubs
@router.get("/",
            response_description="List all clubs",
            response_model=List[ClubDB])
async def list_clubs(
    request: Request,
    active: Optional[bool] = None,  # Added active parameter
    page: int = 1,
) -> JSONResponse:
  mongodb = request.app.state.mongodb
  #RESULTS_PER_PAGE = int(os.environ['RESULTS_PER_PAGE'])
  RESULTS_PER_PAGE = 100
  skip = (page - 1) * RESULTS_PER_PAGE
  query = {}
  if active is not None:  # Filter by active if provided
    query["active"] = active
  full_query = await mongodb["clubs"].find(query).sort(
      "name", 1).skip(skip).limit(RESULTS_PER_PAGE).to_list(length=None)
  clubs = [ClubDB(**raw_club) for raw_club in full_query]
  return JSONResponse(status_code=status.HTTP_200_OK,
                      content=jsonable_encoder(clubs))


# get club by Alias
@router.get("/{alias}",
            response_description="Get a single club",
            response_model=ClubDB)
async def get_club(alias: str, request: Request) -> JSONResponse:
  mongodb = request.app.state.mongodb
  if (club := await mongodb["clubs"].find_one({"alias": alias})) is not None:
    return JSONResponse(status_code=status.HTTP_200_OK,
                        content=jsonable_encoder(ClubDB(**club)))
  raise ResourceNotFoundException(
    resource_type="Club",
    resource_id=alias,
    details={"query_field": "alias"}
  )

# get club by ID
@router.get("/id/{id}",
            response_description="Get a single club by ID",
            response_model=ClubDB)
async def get_club_by_id(id: str, request: Request) -> JSONResponse:
    mongodb = request.app.state.mongodb
    if (club := await mongodb["clubs"].find_one({"_id": id})) is not None:
        return JSONResponse(status_code=status.HTTP_200_OK,
                          content=jsonable_encoder(ClubDB(**club)))
    raise ResourceNotFoundException(
      resource_type="Club",
      resource_id=id,
      details={"query_field": "_id"}
    )

# create new club
@router.post("/", response_description="Add new club", response_model=ClubDB)
async def create_club(
    request: Request,
    name: str = Form(...),
    alias: str = Form(...),
    addressName: str = Form(None),
    street: str = Form(None),
    zipCode: str = Form(None),
    city: str = Form(None),
    country: str = Form(...),
    email: EmailStr = Form(None),
    yearOfFoundation: int = Form(None),
    description: str = Form(None),
    website: HttpUrl = Form(None),
    ishdId: int = Form(None),
    active: bool = Form(False),
    logo: UploadFile = File(None),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> JSONResponse:
  mongodb = request.app.state.mongodb
  if "ADMIN" not in token_payload.roles:
    raise AuthorizationException(
      message="Admin role required to create clubs",
      details={"user_role": token_payload.roles}
    )

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

  if logo:
    club_data['logoUrl'] = await handle_logo_upload(logo, alias)

  # insert club
  try:
    logger.info(f"Creating new club: {name} ({alias})")
    new_club = await mongodb["clubs"].insert_one(club_data)
    created_club = await mongodb["clubs"].find_one(
        {"_id": new_club.inserted_id})
    if created_club:
      logger.info(f"Club created successfully: {name}")
      return JSONResponse(status_code=status.HTTP_201_CREATED,
                          content=jsonable_encoder(ClubDB(**created_club)))
    else:
      raise DatabaseOperationException(
        operation="insert",
        collection="clubs",
        details={"club_name": name, "reason": "Insert acknowledged but club not found"}
      )
  except DuplicateKeyError:
    raise DatabaseOperationException(
      operation="insert",
      collection="clubs",
      details={"club_name": name, "reason": "Duplicate key - club already exists"}
    )
  except Exception as e:
    logger.error(f"Unexpected error creating club {name}: {str(e)}")
    raise DatabaseOperationException(
      operation="insert",
      collection="clubs",
      details={"club_name": name, "error": str(e)}
    )


# Update club
@router.patch("/{id}",
              response_description="Update club",
              response_model=ClubDB)
async def update_club(
    request: Request,
    id: str,
    name: Optional[str] = Form(None),
    alias: Optional[str] = Form(None),
    addressName: Optional[str] = Form(None),
    street: Optional[str] = Form(None),
    zipCode: Optional[str] = Form(None),
    city: Optional[str] = Form(None),
    country: Optional[str] = Form(None),
    email: Optional[EmailStr] = Form(None),
    yearOfFoundation: Optional[int] = Form(None),
    description: Optional[str] = Form(None),
    website: Optional[HttpUrl] = Form(None),
    ishdId: Optional[int] = Form(None),
    active: Optional[bool] = Form(None),
    logo: Optional[UploadFile] = File(None),
    logoUrl: Optional[HttpUrl] = Form(None),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
):
  mongodb = request.app.state.mongodb
  if "ADMIN" not in token_payload.roles:
    raise AuthorizationException(
      message="Admin role required to update clubs",
      details={"user_role": token_payload.roles}
    )

  # retrieve existing club
  existing_club = await mongodb["clubs"].find_one({"_id": id})
  if not existing_club:
    raise ResourceNotFoundException(
      resource_type="Club",
      resource_id=id
    )

  club_data = ClubUpdate(name=name,
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
                         active=active).model_dump(exclude_none=True)
  club_data.pop('id', None)

  # handle image upload
  if logo:
    club_data['logoUrl'] = await handle_logo_upload(logo,
                                                    existing_club['alias'])
  elif logoUrl:
    club_data['logoUrl'] = logoUrl
  elif existing_club.get('logoUrl'):
    await delete_from_cloudinary(existing_club['logoUrl'])
    club_data['logoUrl'] = None

  #Exclude unchanged data
  club_to_update = {
      k: v
      for k, v in club_data.items() if v != existing_club.get(k, None)
  }
  if not club_to_update:
    logger.info(f"No changes to update for club {id}")
    return Response(status_code=status.HTTP_304_NOT_MODIFIED)

  # update club
  try:
    logger.info(f"Updating club {existing_club.get('name', id)}")
    update_result = await mongodb["clubs"].update_one({"_id": id},
                                                      {"$set": club_to_update})
    if update_result.modified_count == 1:
      updated_club = await mongodb["clubs"].find_one({"_id": id})
      logger.info(f"Club updated successfully: {existing_club.get('name', id)}")
      return JSONResponse(status_code=status.HTTP_200_OK,
                          content=jsonable_encoder(ClubDB(**updated_club)))
    raise DatabaseOperationException(
      operation="update",
      collection="clubs",
      details={"club_id": id, "modified_count": update_result.modified_count}
    )
  except DuplicateKeyError:
    raise DatabaseOperationException(
      operation="update",
      collection="clubs",
      details={"club_id": id, "reason": "Duplicate key - club name already exists"}
    )
  except Exception as e:
    logger.error(f"Unexpected error updating club {id}: {str(e)}")
    raise DatabaseOperationException(
      operation="update",
      collection="clubs",
      details={"club_id": id, "error": str(e)}
    )


# Delete club
@router.delete("/{id}", response_description="Delete club")
async def delete_club(
    request: Request,
    id: str,
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> Response:
  mongodb = request.app.state.mongodb
  if "ADMIN" not in token_payload.roles:
    raise AuthorizationException(
      message="Admin role required to delete clubs",
      details={"user_role": token_payload.roles}
    )
  existing_club = await mongodb["clubs"].find_one({"_id": id})
  if not existing_club:
    raise ResourceNotFoundException(
      resource_type="Club",
      resource_id=id
    )
  
  logger.info(f"Deleting club: {existing_club.get('name', id)}")
  result = await mongodb['clubs'].delete_one({"_id": id})
  if result.deleted_count == 1:
    if existing_club.get('logoUrl'):
      await delete_from_cloudinary(existing_club['logoUrl'])
    logger.info(f"Club deleted successfully: {existing_club.get('name', id)}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
  raise DatabaseOperationException(
    operation="delete",
    collection="clubs",
    details={"club_id": id, "deleted_count": result.deleted_count}
  )
