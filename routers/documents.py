from fastapi import APIRouter, UploadFile, File, HTTPException, Request, Form, Depends, status
from fastapi.responses import JSONResponse, Response
from fastapi.encoders import jsonable_encoder
from utils import configure_cloudinary, my_jsonable_encoder
from typing import List
import cloudinary
import cloudinary.uploader
from models.documents import DocumentBase, DocumentDB, DocumentUpdate
from authentication import AuthHandler, TokenPayload
from datetime import datetime
from pymongo.errors import DuplicateKeyError

router = APIRouter()
auth = AuthHandler()
configure_cloudinary()


# Helper function to upload file to Cloudinary
def upload_to_cloudinary(title: str, file: UploadFile):
  try:
    result = cloudinary.uploader.upload(file.file,
                                        public_id=file.filename,
                                        resource_type='raw',
                                        folder="docs/")
    print("Document uploaded to Cloudinary:", result['public_id'])
    return result
  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))


# Helper function to check file format
def validate_file_type(file: UploadFile):
  allowed_types = [
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
  ]
  if file.content_type not in allowed_types:
    raise HTTPException(
      status_code=400,
      detail="Invalid file type. Only PDF, DOCX and XLSX are allowed.")


# Helper function to delete file from Cloudinary
async def delete_from_cloudinary(public_id: str):
  try:
    result = cloudinary.uploader.destroy(public_id, resource_type='raw')
    print("Document deleted from Cloudinary:", public_id)
    return result
  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))

# Helper function to check for reserved aliases
def check_reserved_aliases(alias: str):
  reserved_aliases = ["categories"]
  if alias.lower() in reserved_aliases:
    raise HTTPException(status_code=400,
                        detail="Alias/Title is reserved as API endpoint. Please choose another.")

# get all catgories
@router.get("/categories", response_description="Get list of all categories")
async def get_categories(request: Request, ) -> List[str]:
  categories = await request.app.mongodb["documents"].distinct("category")
  categories.sort()
  return categories


# get documents of a category
@router.get("/categories/{category}",
            response_model=List[DocumentDB],
            response_description="Get documents for a category")
async def get_documents_by_category(
  request: Request,
  category: str,
) -> List[DocumentDB]:
  documents = await request.app.mongodb["documents"].find({
    "category": {"$regex": f"^{category}$", "$options": "i"} 
  }).to_list(1000)
  documents.sort(key=lambda x: x["title"])
  result = [DocumentDB(**document) for document in documents]
  return result


# get one document by alias
@router.get("/{alias}",
            response_model=DocumentDB,
            response_description="Get document by alias")
async def get_document(
  request: Request,
  alias: str,
) -> DocumentDB:
  query = {"alias": alias}
  document = await request.app.mongodb["documents"].find_one(query)
  if not document:
    raise HTTPException(status_code=404, detail="Document not found")
  return DocumentDB(**document)


# get list of all documents
@router.get("/",
            response_model=List[DocumentDB],
            response_description="Get list of all documents")
async def get_documents(request: Request, ) -> List[DocumentDB]:
  documents = await request.app.mongodb["documents"].find().to_list(1000)
  result = [DocumentDB(**document) for document in documents]
  return result


# create/upload new document
@router.post("/",
             response_model=DocumentDB,
             response_description="Upload a new document")
async def upload_document(
  request: Request,
  title: str = Form(...),
  alias: str = Form(...),
  file: UploadFile = File(...),
  category: str = Form(None),
  token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> DocumentDB:

  if token_payload.roles not in [["ADMIN"]]:
    raise HTTPException(status_code=403, detail="Not authorized")

  # Check if document already exists in db
  existing_doc = await request.app.mongodb['documents'].find_one(
    {'title': title})
  if existing_doc:
    raise HTTPException(status_code=400,
                        detail=f"Document '{title}' already exists.")

  check_reserved_aliases(alias)
  validate_file_type(file)

  # upload file
  result = upload_to_cloudinary(title, file)

  # data preparation for storing in database
  document = DocumentBase(
    title=title,
    alias=alias,
    url=result['secure_url'],
    public_id=result['public_id'],
    filename=file.filename,
    file_type=file.content_type,
    file_size_byte=file.size,
  )
  if category:
    document.category = category
  else:
    document.category = None

  document_data = jsonable_encoder(document)

  document_data['create_date'] = datetime.utcnow().replace(microsecond=0)
  document_data['create_user'] = {
    "user_id": token_payload.sub,
    "firstname": token_payload.firstname,
    "lastname": token_payload.lastname
  }
  document_data['update_user'] = None
  document_data['update_date'] = None

  try:
    print("document_data: ", document_data)
    new_doc = await request.app.mongodb["documents"].insert_one(document_data)
    created_doc = await request.app.mongodb["documents"].find_one(
      {"_id": new_doc.inserted_id})
    if created_doc:
      return JSONResponse(status_code=status.HTTP_201_CREATED,
                          content=jsonable_encoder(DocumentDB(**created_doc)))
    else:
      raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                          detail="Failed to create document")
  except DuplicateKeyError:
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST,
      detail=f"Document {document_data['title']} already exists.")
  except Exception as e:
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=str(e))


# Update document
@router.patch("/{id}",
              response_model=DocumentDB,
              response_description="Update an existing document")
async def update_document(
  request: Request,
  id: str,
  title: str = Form(...),
  alias: str = Form(...),
  file: UploadFile = File(None),
  category: str = Form(None),
  token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> DocumentDB:
  if token_payload.roles not in [["ADMIN"]]:
    raise HTTPException(status_code=403, detail="Not authorized")

  doc_data = DocumentUpdate(
    title=title,
    alias=alias,
    category=category,
  ).dict(exclude_unset=True)
  print("doc_data: ", doc_data)

  existing_doc = await request.app.mongodb['documents'].find_one({'_id': id})
  if not existing_doc:
    raise HTTPException(status_code=404,
                        detail=f"Document with id {id} not found.")

  if file:
    validate_file_type(file)
    await delete_from_cloudinary(existing_doc['public_id'])
    result = upload_to_cloudinary(title, file)
    doc_data['url'] = result['secure_url']
    doc_data['public_id'] = result['public_id']
    doc_data['filename'] = file.filename
    doc_data['file_type'] = file.content_type
    doc_data['file_size_byte'] = file.size

  doc_data['update_date'] = datetime.utcnow().replace(microsecond=0)
  doc_data['update_user'] = {
    "user_id": token_payload.sub,
    "firstname": token_payload.firstname,
    "lastname": token_payload.lastname
  }

  # Exclude unchanged data
  doc_to_update = {
    k: v
    for k, v in doc_data.items() if v != existing_doc.get(k, None)
  }
  print("doc_to_update: ", doc_to_update)
  if not doc_to_update or ('update_date' in doc_to_update
                           and len(doc_to_update) == 1):
    print("No changes to update")
    return JSONResponse(status_code=status.HTTP_200_OK,
                        content=jsonable_encoder(DocumentDB(**existing_doc)))

  # update doc
  try:
    update_result = await request.app.mongodb['documents'].update_one(
      {'_id': id}, {'$set': doc_to_update}, upsert=False)
    if update_result.modified_count == 1:
      updated_doc = await request.app.mongodb["documents"].find_one(
        {"_id": id})
      return JSONResponse(status_code=status.HTTP_200_OK,
                          content=jsonable_encoder(DocumentDB(**updated_doc)))
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        content="Failed to update document")
  except Exception as e:
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=str(e))

  return JSONResponse(status_code=200,
                      content={
                        "message": "Document replaced successfully",
                        "document_url": result['secure_url'],
                        "document_id": result['public_id']
                      })


# delete document
@router.delete("/{alias}", response_description="Delete an existing document")
async def delete_document(
  request: Request,
  alias: str,
  token_payload: TokenPayload = Depends(auth.auth_wrapper)) -> None:
  if token_payload.roles not in [["ADMIN"]]:
    raise HTTPException(status_code=403, detail="Not authorized")
  existing_doc = await request.app.mongodb['documents'].find_one(
    {'alias': alias})
  if not existing_doc:
    raise HTTPException(status_code=404,
                        detail=f"Document with alias {alias} not found.")
  result = await request.app.mongodb['documents'].delete_one({"alias": alias})
  if result.deleted_count == 1:
    await delete_from_cloudinary(existing_doc['public_id'])
    return Response(status_code=status.HTTP_204_NO_CONTENT)
  raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                      detail="Failed to delete document")