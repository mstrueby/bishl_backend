import cloudinary
import cloudinary.uploader
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from pydantic import EmailStr, HttpUrl
from pymongo.errors import DuplicateKeyError

from authentication import AuthHandler, TokenPayload
from exceptions import AuthorizationException, DatabaseOperationException, ResourceNotFoundException
from logging_config import logger
from models.clubs import ClubBase, ClubDB, ClubUpdate
from models.responses import PaginatedResponse, StandardResponse
from services.pagination import PaginationHelper
from utils import configure_cloudinary

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
        return str(result["secure_url"])
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No logo uploaded.")


# Helper function to delete file from Cloudinary
async def delete_from_cloudinary(logo_url: str):
    if logo_url:
        try:
            public_id = logo_url.rsplit("/", 1)[-1].split(".")[0]
            result = cloudinary.uploader.destroy(f"logos/{public_id}")
            print("Logo deleted from Cloudinary:", f"logos/{public_id}")
            print("Result:", result)
            return result
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e


# list all clubs
@router.get("", response_description="List all clubs", response_model=PaginatedResponse[ClubDB])
async def list_clubs(
    request: Request,
    active: bool | None = None,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(100, ge=1, le=100, description="Items per page"),
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    query = {}
    if active is not None:
        query["active"] = active

    items, total_count = await PaginationHelper.paginate_query(
        collection=mongodb["clubs"], query=query, page=page, page_size=page_size, sort=[("name", 1)]
    )

    paginated_result = PaginationHelper.create_response(
        items=[ClubDB(**club) for club in items],
        page=page,
        page_size=page_size,
        total_count=total_count,
        message=f"Retrieved {len(items)} clubs",
    )

    return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(paginated_result))


# get club by Alias
@router.get("/{alias}", response_description="Get a single club", response_model=StandardResponse[ClubDB])
async def get_club(alias: str, request: Request) -> StandardResponse[ClubDB]:
    mongodb = request.app.state.mongodb
    if (club := await mongodb["clubs"].find_one({"alias": alias})) is not None:
        return StandardResponse(
            success=True,
            data=ClubDB(**club),
            message="Club retrieved successfully"
        )
    raise ResourceNotFoundException(
        resource_type="Club", resource_id=alias, details={"query_field": "alias"}
    )


# get club by ID
@router.get("/id/{id}", response_description="Get a single club by ID", response_model=StandardResponse[ClubDB])
async def get_club_by_id(id: str, request: Request) -> JSONResponse:
    mongodb = request.app.state.mongodb
    if (club := await mongodb["clubs"].find_one({"_id": id})) is not None:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=jsonable_encoder(StandardResponse(
                success=True,
                data=ClubDB(**club),
                message="Club retrieved successfully"
            ))
        )
    raise ResourceNotFoundException(
        resource_type="Club", resource_id=id, details={"query_field": "_id"}
    )


# create new club
@router.post("", response_description="Add new club", response_model=StandardResponse[ClubDB])
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
) -> StandardResponse[ClubDB]:
    mongodb = request.app.state.mongodb
    if "ADMIN" not in token_payload.roles:
        raise AuthorizationException(
            message="Admin role required to create clubs",
            details={"user_role": token_payload.roles},
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
        club_data["logoUrl"] = await handle_logo_upload(logo, alias)

    # insert club
    try:
        logger.info(f"Creating new club: {name} ({alias})")
        new_club = await mongodb["clubs"].insert_one(club_data)
        created_club = await mongodb["clubs"].find_one({"_id": new_club.inserted_id})
        if created_club:
            logger.info(f"Club created successfully: {name}")
            return StandardResponse(
                success=True,
                data=ClubDB(**created_club),
                message=f"Club '{created_club['name']}' created successfully"
            )
        else:
            raise DatabaseOperationException(
                operation="insert",
                collection="clubs",
                details={"club_name": name, "reason": "Insert acknowledged but club not found"},
            )
    except DuplicateKeyError as e:
        raise DatabaseOperationException(
            operation="insert",
            collection="clubs",
            details={"club_name": name, "reason": "Duplicate key - club already exists"},
        ) from e
    except Exception as e:
        logger.error(f"Unexpected error creating club {name}: {str(e)}")
        raise DatabaseOperationException(
            operation="insert", collection="clubs", details={"club_name": name, "error": str(e)}
        ) from e


# Update club
@router.patch("/{id}", response_description="Update club", response_model=StandardResponse[ClubDB])
async def update_club(
    request: Request,
    id: str,
    name: str | None = Form(None),
    alias: str | None = Form(None),
    addressName: str | None = Form(None),
    street: str | None = Form(None),
    zipCode: str | None = Form(None),
    city: str | None = Form(None),
    country: str | None = Form(None),
    email: EmailStr | None = Form(None),
    yearOfFoundation: int | None = Form(None),
    description: str | None = Form(None),
    website: HttpUrl | None = Form(None),
    ishdId: int | None = Form(None),
    active: bool | None = Form(None),
    logo: UploadFile | None = File(None),
    logoUrl: HttpUrl | None = Form(None),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
):
    mongodb = request.app.state.mongodb
    if "ADMIN" not in token_payload.roles:
        raise AuthorizationException(
            message="Admin role required to update clubs",
            details={"user_role": token_payload.roles},
        )

    # retrieve existing club
    existing_club = await mongodb["clubs"].find_one({"_id": id})
    if not existing_club:
        raise ResourceNotFoundException(resource_type="Club", resource_id=id)

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
        active=active,
    ).model_dump(exclude_none=True)
    club_data.pop("id", None)

    # handle image upload
    if logo:
        club_data["logoUrl"] = await handle_logo_upload(logo, existing_club["alias"])
    elif logoUrl:
        club_data["logoUrl"] = logoUrl
    elif existing_club.get("logoUrl"):
        await delete_from_cloudinary(existing_club["logoUrl"])
        club_data["logoUrl"] = None

    # Exclude unchanged data
    club_to_update = {k: v for k, v in club_data.items() if v != existing_club.get(k, None)}
    if not club_to_update:
        logger.info(f"No changes to update for club {id}")
        # Return 200 with existing data instead of 304
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=jsonable_encoder(StandardResponse(
                success=True,
                data=ClubDB(**existing_club),
                message="No changes detected"
            ))
        )

    # update club
    try:
        logger.info(f"Updating club {existing_club.get('name', id)}")
        update_result = await mongodb["clubs"].update_one({"_id": id}, {"$set": club_to_update})
        if update_result.modified_count == 1:
            updated_club = await mongodb["clubs"].find_one({"_id": id})
            logger.info(f"Club updated successfully: {existing_club.get('name', id)}")
            return StandardResponse(
                success=True,
                data=ClubDB(**updated_club),
                message=f"Club '{updated_club['name']}' updated successfully"
            )
        return StandardResponse(
            success=False,
            data=ClubDB(**existing_club),
            message="Failed to update club"
        )
    except DuplicateKeyError as e:
        raise DatabaseOperationException(
            operation="update",
            collection="clubs",
            details={"club_id": id, "reason": "Duplicate key - club name already exists"},
        ) from e
    except Exception as e:
        logger.error(f"Unexpected error updating club {id}: {str(e)}")
        raise DatabaseOperationException(
            operation="update", collection="clubs", details={"club_id": id, "error": str(e)}
        ) from e


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
            details={"user_role": token_payload.roles},
        )
    existing_club = await mongodb["clubs"].find_one({"_id": id})
    if not existing_club:
        raise ResourceNotFoundException(resource_type="Club", resource_id=id)

    logger.info(f"Deleting club: {existing_club.get('name', id)}")
    result = await mongodb["clubs"].delete_one({"_id": id})
    if result.deleted_count == 1:
        if existing_club.get("logoUrl"):
            await delete_from_cloudinary(existing_club["logoUrl"])
        logger.info(f"Club deleted successfully: {existing_club.get('name', id)}")
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    raise DatabaseOperationException(
        operation="delete",
        collection="clubs",
        details={"club_id": id, "deleted_count": result.deleted_count},
    )