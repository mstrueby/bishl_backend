from datetime import datetime
from typing import Any

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
from loguru import logger
from pymongo.errors import DuplicateKeyError

from authentication import AuthHandler, TokenPayload
from exceptions import (
    AuthorizationException,
    ResourceNotFoundException,
    ValidationException,
)
from models.documents import DocumentBase, DocumentDB, DocumentUpdate
from models.responses import PaginatedResponse, StandardResponse
from services.pagination import PaginationHelper
from utils import configure_cloudinary

router = APIRouter()
auth = AuthHandler()
configure_cloudinary()


# Helper function to upload file to Cloudinary
def upload_to_cloudinary(title: str, file: UploadFile):
    try:
        result = cloudinary.uploader.upload(
            file.file, public_id=file.filename, resource_type="raw", folder="docs/"
        )
        logger.info(f"Document uploaded to Cloudinary: {result["public_id"]}")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# Helper function to check file format
def validate_file_type(file: UploadFile):
    allowed_types = [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "text/plain",
        "text/csv",
    ]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400, detail="Invalid file type. Only PDF, DOCX and XLSX are allowed."
        )


# Helper function to delete file from Cloudinary
async def delete_from_cloudinary(public_id: str):
    try:
        result = cloudinary.uploader.destroy(public_id, resource_type="raw")
        logger.info(f"Document deleted from Cloudinary: {public_id}")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# Helper function to check for reserved aliases
def check_reserved_aliases(alias: str):
    reserved_aliases = ["categories"]
    if alias.lower() in reserved_aliases:
        raise HTTPException(
            status_code=400,
            detail="Alias/Title is reserved as API endpoint. Please choose another.",
        )


# get all catgories
@router.get("/categories", response_description="Get list of all categories")
async def get_categories(request: Request) -> list[str]:
    mongodb = request.app.state.mongodb
    categories: list[str] = await mongodb["documents"].distinct("category")
    categories.sort()
    return categories


# get documents of a category
@router.get(
    "/categories/{category}",
    response_model=PaginatedResponse[DocumentDB],
    response_description="Get documents for a category",
)
async def get_documents_by_category(
    request: Request,
    category: str,
    published: bool | None = None,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(100, ge=1, le=100, description="Items per page"),
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    query: dict[str, Any] = {"category": {"$regex": rf"^{category}$", "$options": "i"}}
    if published is not None:
        query["published"] = published

    items, total_count = await PaginationHelper.paginate_query(
        collection=mongodb["documents"],
        query=query,
        page=page,
        page_size=page_size,
        sort=[("title", 1)],
    )

    paginated_result = PaginationHelper.create_response(
        items=[DocumentDB(**document) for document in items],
        page=page,
        page_size=page_size,
        total_count=total_count,
        message=f"Retrieved {len(items)} documents for category {category}",
    )

    return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(paginated_result))


# get one document by alias
@router.get(
    "/{alias}",
    response_model=StandardResponse[DocumentDB],
    response_description="Get document by alias",
)
async def get_document(
    request: Request,
    alias: str,
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    query = {"alias": alias}
    document = await mongodb["documents"].find_one(query)
    if not document:
        raise ResourceNotFoundException(
            resource_type="Document", resource_id=alias, details={"query_field": "alias"}
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=jsonable_encoder(
            StandardResponse(
                success=True, data=DocumentDB(**document), message="Document retrieved successfully"
            )
        ),
    )


# get list of all documents
@router.get(
    "",
    response_model=PaginatedResponse[DocumentDB],
    response_description="Get list of all documents",
)
async def get_documents(
    request: Request,
    published: bool | None = None,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(100, ge=1, le=100, description="Items per page"),
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    query: dict[str, Any] = {"published": published} if published is not None else {}

    items, total_count = await PaginationHelper.paginate_query(
        collection=mongodb["documents"],
        query=query,
        page=page,
        page_size=page_size,
        sort=[("title", 1)],
    )

    paginated_result = PaginationHelper.create_response(
        items=[DocumentDB(**document) for document in items],
        page=page,
        page_size=page_size,
        total_count=total_count,
        message=f"Retrieved {len(items)} documents",
    )

    return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(paginated_result))


# create/upload new document
@router.post(
    "", response_model=StandardResponse[DocumentDB], response_description="Upload a new document"
)
async def upload_document(
    request: Request,
    title: str = Form(...),
    alias: str = Form(...),
    file: UploadFile = File(...),
    category: str = Form(None),
    published: bool = Form(False),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    if not any(role in token_payload.roles for role in ["ADMIN", "DOC_ADMIN"]):
        raise AuthorizationException(
            message="Admin or Doc Admin role required", details={"user_roles": token_payload.roles}
        )

    # Check if document already exists in db
    existing_doc = await mongodb["documents"].find_one({"title": title})
    if existing_doc:
        raise ValidationException(
            field="title",
            message=f"Document '{title}' already exists",
            details={"existing_id": existing_doc.get("_id")},
        )

    check_reserved_aliases(alias)
    validate_file_type(file)

    # upload file
    result = upload_to_cloudinary(title, file)

    # data preparation for storing in database
    document = DocumentBase(
        title=title,
        alias=alias,
        url=result["secure_url"],
        publicId=result["public_id"],
        fileName=file.filename if file.filename is not None else "default_filename",
        fileType=file.content_type if file.content_type is not None else "",
        fileSizeByte=file.size if file.size is not None else 0,
        published=published,
    )
    if category:
        document.category = category
    else:
        document.category = None

    document_data = jsonable_encoder(document)

    document_data["createDate"] = datetime.now().replace(microsecond=0)
    document_data["createUser"] = {
        "userId": token_payload.sub,
        "firstName": token_payload.firstName,
        "lastName": token_payload.lastName,
    }
    document_data["updateUser"] = document_data["createUser"]
    document_data["updateDate"] = document_data["createDate"]

    try:
        logger.debug(f"document_data: {document_data}")
        new_doc = await mongodb["documents"].insert_one(document_data)
        created_doc = await mongodb["documents"].find_one({"_id": new_doc.inserted_id})
        if created_doc:
            return JSONResponse(
                status_code=status.HTTP_201_CREATED,
                content=jsonable_encoder(
                    StandardResponse(
                        success=True,
                        data=DocumentDB(**created_doc),
                        message=f"Document '{created_doc['title']}' created successfully",
                    )
                ),
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create document",
            )
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Document {document_data['title']} already exists.",
        ) from None
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e


# Update document
@router.patch(
    "/{id}",
    response_model=StandardResponse[DocumentDB],
    response_description="Update an existing document",
)
async def update_document(
    request: Request,
    id: str,
    title: str | None = Form(None),
    alias: str | None = Form(None),
    category: str | None = Form(None),
    file: UploadFile = File(None),
    published: bool | None = Form(None),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
):
    mongodb = request.app.state.mongodb
    if not any(role in token_payload.roles for role in ["ADMIN", "DOC_ADMIN"]):
        raise HTTPException(status_code=403, detail="Not authorized")

    existing_doc = await mongodb["documents"].find_one({"_id": id})
    if not existing_doc:
        raise HTTPException(status_code=404, detail=f"Document with id {id} not found.")

    doc_data = DocumentUpdate(
        title=title,
        alias=alias,
        category=category,
        published=published,
    ).model_dump(exclude_none=True)
    doc_data.pop("id", None)
    logger.debug(f"doc_data: {doc_data}")

    if file:
        if title is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Title is required."
            )
        # result = upload_to_cloudinary(title, file)
        validate_file_type(file)
        await delete_from_cloudinary(existing_doc["publicId"])
        result = upload_to_cloudinary(title, file)
        doc_data["url"] = result["secure_url"]
        doc_data["publicId"] = result["public_id"]
        doc_data["fileName"] = file.filename
        doc_data["fileType"] = file.content_type
        doc_data["fileSizeByte"] = file.size

    doc_data["updateDate"] = datetime.now().replace(microsecond=0)
    doc_data["updateUser"] = {
        "userId": token_payload.sub,
        "firstName": token_payload.firstName,
        "lastName": token_payload.lastName,
    }

    # Exclude unchanged data
    doc_to_update = {k: v for k, v in doc_data.items() if v != existing_doc.get(k, None)}
    logger.debug(f"doc_to_update: {doc_to_update}")
    if not doc_to_update or ("updateDate" in doc_to_update and len(doc_to_update) == 1):
        logger.debug("No changes to update")
        # Return 200 with existing data
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=jsonable_encoder(
                StandardResponse(
                    success=True, data=DocumentDB(**existing_doc), message="No changes detected"
                )
            ),
        )

    # update doc
    try:
        update_result = await mongodb["documents"].update_one(
            {"_id": id}, {"$set": doc_to_update}, upsert=False
        )
        if update_result.modified_count == 1:
            updated_doc = await mongodb["documents"].find_one({"_id": id})
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=jsonable_encoder(
                    StandardResponse(
                        success=True,
                        data=DocumentDB(**updated_doc),
                        message=f"Document '{updated_doc['title']}' updated successfully",
                    )
                ),
            )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=jsonable_encoder(
                StandardResponse(
                    success=False,
                    data=DocumentDB(**existing_doc),
                    message="Failed to update document",
                )
            ),
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e


# delete document
@router.delete("/{id}", response_description="Delete an existing document")
async def delete_document(
    request: Request, id: str, token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> Response:
    mongodb = request.app.state.mongodb
    if not any(role in token_payload.roles for role in ["ADMIN", "DOC_ADMIN"]):
        raise HTTPException(status_code=403, detail="Not authorized")
    existing_doc = await mongodb["documents"].find_one({"_id": id})
    if not existing_doc:
        raise HTTPException(status_code=404, detail=f"Document with id {id} not found.")
    result = await mongodb["documents"].delete_one({"_id": id})
    if result.deleted_count == 1:
        await delete_from_cloudinary(existing_doc["publicId"])
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete document"
    )
