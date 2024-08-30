from fastapi import APIRouter, UploadFile, File, HTTPException, Request, Form, Depends, status
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from utils import configure_cloudinary, my_jsonable_encoder
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
def upload_to_cloudinary(title: str, file: UploadFile, category: str = None):
  folder = f"docs/{category}/" if category else "docs/"
  try:
    result = cloudinary.uploader.upload(file.file,
                                        public_id=file.filename,
                                        resource_type='raw',
                                        folder=folder)
    print("Document uploaded to Cloudinary:", result['public_id'])
    return result
  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))


# upload new document
@router.post("/", response_model=DocumentDB,
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
  existing_doc = await request.app.mongodb['documents'].find_one({'title': title})
  if existing_doc:
    raise HTTPException(status_code=400, detail=f"Document '{title}' already exists.")
    
  if file.content_type not in [
      "application/pdf",
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
  ]:
    raise HTTPException(
      status_code=400,
      detail="Invalid file type. Only PDF, DOCX and XLSX are allowed.")

  # upload file
  result = upload_to_cloudinary(title, file, category)

  # data preparation for storing in database
  document = DocumentBase(title=title,
                          alias=alias,
                          url=result['secure_url'],
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

"""
# Update document
@router.patch("/", response_model=DocumentDB, response_description="Replace an existing document")
async def update_document(document_id: str, file: UploadFile = File(...)):
  if file.content_type not in [
      "application/pdf",
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
  ]:
    raise HTTPException(
      status_code=400,
      detail="Invalid file type. Only PDF and XLSX are allowed.")

  # Delete the old document
  cloudinary.uploader.destroy(document_id, resource_type='raw')

  # Upload the new document
  result = upload_to_cloudinary(file, category="")

  return JSONResponse(status_code=200,
                      content={
                        "message": "Document replaced successfully",
                        "document_url": result['secure_url'],
                        "document_id": result['public_id']
                      })


@router.get("/{id}", response_description="Get document by ID")
async def get_document(document_id: str):
  url = cloudinary.CloudinaryImage(document_id).build_url(resource_type="raw")
  return JSONResponse(status_code=200, content={"document_url": url})
"""