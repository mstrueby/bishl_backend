from fastapi import APIRouter, UploadFile, File, HTTPException, Request, Form
from fastapi.responses import JSONResponse
from utils import configure_cloudinary
import cloudinary
import cloudinary.uploader

router = APIRouter()
configure_cloudinary()


# Helper function to upload file to Cloudinary
def upload_to_cloudinary(title: str, file: UploadFile, category: str = None):
  print("category: ", category)
  folder = f"docs/{category}/" if category else "docs/"
  print("folder: ", folder)
  try:
    result = cloudinary.uploader.upload(file.file,
                                        public_id=file.filename,
                                        resource_type='raw',
                                        folder=folder)
    return result
  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_description="Upload a new document")
async def upload_document(request: Request,
                          title: str = Form(...),
                          file: UploadFile = File(...),
                          category: str = Form(None)):
  if file.content_type not in [
      "application/pdf",
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
  ]:
    raise HTTPException(
      status_code=400,
      detail="Invalid file type. Only PDF, DOCX and XLSX are allowed.")

  result = upload_to_cloudinary(title, file, category)

  return JSONResponse(status_code=201,
                      content={
                        "message": "Document uploaded successfully",
                        "document_url": result['secure_url'],
                        "document_id": result['public_id']
                      })


@router.post("/replace", response_description="Replace an existing document")
async def replace_document(document_id: str, file: UploadFile = File(...)):
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
