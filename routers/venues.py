from datetime import datetime

import cloudinary
import cloudinary.uploader
from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from pydantic import HttpUrl
from pymongo.errors import DuplicateKeyError

from authentication import AuthHandler, TokenPayload
from exceptions import AuthorizationException, ResourceNotFoundException
from models.venues import VenueBase, VenueDB, VenueUpdate

router = APIRouter()
auth = AuthHandler()


async def handle_image_upload(image: UploadFile, public_id: str):
    if image:
        result = cloudinary.uploader.upload(
            image.file,
            folder="venues",
            public_id=public_id,
            overwrite=True,
            resource_type="image",
            format="jpg",
            transformation=[
                {
                    "width": 1080,
                    # 'aspect_ratio': '16:9',
                    # 'crop': 'fill',
                    # 'gravity': 'auto',
                    "effect": "sharpen:100",
                }
            ],
        )
        print(f"Venue Image uploaded: {result['url']}")
        return result["url"]


async def delete_from_cloudinary(image_url: str):
    if image_url:
        try:
            public_id = image_url.rsplit("/", 1)[-1].split(".")[0]
            result = cloudinary.uploader.destroy(f"venues/{public_id}")
            print("Venue Image deleted from Cloudinary:", f"venues/{public_id}")
            print("Result:", result)
            return result
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e


# list all venues
@router.get("", response_description="List all venues", response_model=list[VenueDB])
async def list_venues(
    request: Request,
    active: bool | None = None,
    page: int = 1,
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    # RESULTS_PER_PAGE = int(os.environ['RESULTS_PER_PAGE'])
    RESULTS_PER_PAGE = 100
    skip = (page - 1) * RESULTS_PER_PAGE
    query = {}
    if active is not None:
        query["active"] = active
    full_query = (
        await mongodb["venues"]
        .find(query)
        .sort("name", 1)
        .skip(skip)
        .limit(RESULTS_PER_PAGE)
        .to_list(length=None)
    )
    venues = [VenueDB(**raw_venue) for raw_venue in full_query]
    return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(venues))


# get venue by Alias
@router.get("/{alias}", response_description="Get a single venue", response_model=VenueDB)
async def get_venue(alias: str, request: Request) -> JSONResponse:
    mongodb = request.app.state.mongodb
    if (venue := await mongodb["venues"].find_one({"alias": alias})) is not None:
        return JSONResponse(
            status_code=status.HTTP_200_OK, content=jsonable_encoder(VenueDB(**venue))
        )
    raise ResourceNotFoundException(
        resource_type="Venue", resource_id=alias, details={"query_field": "alias"}
    )


# create new venue
@router.post("", response_description="Add new venue", response_model=VenueDB)
async def create_venue(
    request: Request,
    name: str = Form(...),
    alias: str = Form(...),
    shortName: str = Form(...),
    street: str = Form(...),
    zipCode: str = Form(...),
    city: str = Form(...),
    country: str = Form(...),
    latitude: str = Form(...),
    longitude: str = Form(...),
    image: UploadFile = Form(None),
    description: str | None = Form(None),
    active: bool = Form(False),
    usageApprovalId: str | None = Form(None),
    usageApprovalValidTo: datetime | None = Form(None),
    legacyId: int | None = Form(None),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    if "ADMIN" not in token_payload.roles:
        raise AuthorizationException(
            message="Admin role required to create venues",
            details={"user_roles": token_payload.roles},
        )
    venue = VenueBase(
        name=name,
        alias=alias,
        shortName=shortName,
        street=street,
        zipCode=zipCode,
        city=city,
        country=country,
        latitude=latitude,
        longitude=longitude,
        description=description,
        active=active,
        usageApprovalId=usageApprovalId,
        usageApprovalValidTo=usageApprovalValidTo,
        legacyId=legacyId,
    )
    venue_data = jsonable_encoder(venue)

    # Handle image upload
    if image:
        venue_data["imageUrl"] = await handle_image_upload(image, venue_data["alias"])

    # DB processing
    try:
        new_venue = await mongodb["venues"].insert_one(venue_data)
        created_venue = await mongodb["venues"].find_one({"_id": new_venue.inserted_id})
        if created_venue:
            return JSONResponse(
                status_code=status.HTTP_201_CREATED,
                content=jsonable_encoder(VenueDB(**created_venue)),
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to create venue")
    except DuplicateKeyError as e:
        raise HTTPException(
            status_code=400, detail=f"Venue {venue_data.get('name', 'Unknown')} already exists."
        ) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# Update venue
@router.patch("/{id}", response_description="Update venue", response_model=VenueDB)
async def update_venue(
    request: Request,
    id: str,
    name: str | None = Form(None),
    alias: str | None = Form(None),
    shortName: str | None = Form(None),
    street: str | None = Form(None),
    zipCode: str | None = Form(None),
    city: str | None = Form(None),
    country: str | None = Form(None),
    latitude: str | None = Form(None),
    longitude: str | None = Form(None),
    image: UploadFile | None = Form(None),
    imageUrl: HttpUrl | None = Form(None),
    description: str | None = Form(None),
    active: bool | None = Form(None),
    usageApprovalId: str | None = Form(None),
    usageApprovalValidTo: datetime | None = Form(None),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
):
    mongodb = request.app.state.mongodb
    if "ADMIN" not in token_payload.roles:
        raise HTTPException(status_code=403, detail="Nicht authorisiert")

    existing_venue = await mongodb["venues"].find_one({"_id": id})
    if not existing_venue:
        raise ResourceNotFoundException(resource_type="Venue", resource_id=id)

    try:
        venue_data = VenueUpdate(
            name=name,
            alias=alias,
            shortName=shortName,
            street=street,
            zipCode=zipCode,
            city=city,
            country=country,
            latitude=latitude,
            longitude=longitude,
            description=description,
            active=active,
            usageApprovalId=usageApprovalId,
            usageApprovalValidTo=usageApprovalValidTo,
        ).model_dump(exclude_none=True)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Failed to parse input data"
        ) from e

    venue_data.pop("id", None)

    # Handle image upload
    if image:
        venue_data["imageUrl"] = await handle_image_upload(image, venue_data["alias"])
    elif imageUrl:
        venue_data["imageUrl"] = imageUrl
    elif existing_venue.get("imageUrl"):
        await delete_from_cloudinary(existing_venue["imageUrl"])
        venue_data["imageUrl"] = None
    else:
        venue_data["imageUrl"] = None

    print("venue_data: ", venue_data)

    # Remove None values
    # venue_data = {k: v for k, v in venue_data.items() if v is not None}

    # Exclude unchanged data
    venue_to_update = {k: v for k, v in venue_data.items() if v != existing_venue.get(k)}
    print("venue_to_update: ", venue_to_update)

    if not venue_to_update:
        print("No update needed")
        return Response(status_code=status.HTTP_304_NOT_MODIFIED)
    try:
        update_result = await mongodb["venues"].update_one({"_id": id}, {"$set": venue_to_update})
        if update_result.modified_count == 1:
            if (updated_venue := await mongodb["venues"].find_one({"_id": id})) is not None:
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content=jsonable_encoder(VenueDB(**updated_venue)),
                )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content="Failed to update venue"
        )
    except DuplicateKeyError as e:
        raise HTTPException(
            status_code=400, detail=f"Venue with name {venue_data.get('name', '')} already exists."
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"An unexpected error occurred: {str(e)}"
        ) from e


# Delete venue
@router.delete("/{id}", response_description="Delete venue")
async def delete_venue(
    request: Request,
    id: str,
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> Response:
    mongodb = request.app.state.mongodb
    if "ADMIN" not in token_payload.roles:
        raise HTTPException(status_code=403, detail="Nicht authorisiert")
    existing_venue = await mongodb["venues"].find_one({"_id": id})
    if not existing_venue:
        raise ResourceNotFoundException(resource_type="Venue", resource_id=id)
    result = await mongodb["venues"].delete_one({"_id": id})
    if result.deleted_count == 1:
        await delete_from_cloudinary(existing_venue["imageUrl"])
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail=f"Venue with id {id} not found"
    )