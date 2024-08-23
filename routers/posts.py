from fastapi import APIRouter, HTTPException, Form, UploadFile, File, Request, Body, Depends, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
import json
from models.posts import PostBase, PostDB, PostUpdate
from typing import List
from utils import configure_cloudinary, my_jsonable_encoder
from pymongo import MongoClient
from bson import ObjectId
from authentication import AuthHandler, TokenPayload
from datetime import datetime
import cloudinary
import cloudinary.uploader

router = APIRouter()
auth = AuthHandler()
configure_cloudinary()


async def handle_image_upload(image: UploadFile, public_id: str) -> str:
  if image:
    return cloudinary.uploader.upload(
      image.file,
      folder="posts",
      public_id=public_id,
      overwrite=True,
      resource_type="image",
      format='jpg',
      transformation=[{
        'width': 1080,
        'aspect_ratio': '16:9',
        'crop': 'fill',
        'gravity': 'auto',
        'effect': 'sharpen:100',
      }],
    )["url"]
  return None


# list all posts
@router.get("/",
            response_description="List all posts",
            response_model=List[PostDB])
async def get_posts(request: Request):
  query = {}
  posts = request.app.mongodb["posts"].find(query).sort("create_date", -1)
  result = [PostDB(**raw_post) async for raw_post in posts]
  return result


# get post by alias
@router.get("/{alias}",
            response_description="Get post by alias",
            response_model=PostDB)
async def get_post(request: Request, alias: str) -> PostDB:
  query = {"alias": alias}
  post = await request.app.mongodb["posts"].find_one(query)
  if not post:
    raise HTTPException(status_code=404, detail="Post not found")
  return PostDB(**post)


# create post
@router.post("/", response_model=PostDB, response_description="Create post")
async def create_post(
  request: Request,
  title: str = Form(...),
  content: str = Form(...),
  alias: str = Form(...),
  author: str = Form(None),
  published: bool = Form(False),
  legacyId: int = Form(None),
  token_payload: TokenPayload = Depends(auth.auth_wrapper),
  image: UploadFile = File(None)
) -> PostDB:
  if token_payload.roles not in [["ADMIN"]]:
    raise HTTPException(status_code=403, detail="Not authorized")

  # Data preparation
  post = PostBase(
    title=title,
    alias=alias,
    content=content,
    author=json.loads(author) if author else None,
  )
  post_data = jsonable_encoder(post)

  post_data['create_date'] = datetime.utcnow().replace(microsecond=0)
  post_data['create_user'] = {
    "user_id": token_payload.sub,
    "firstname": token_payload.firstname,
    "lastname": token_payload.lastname
  }

  # Handle image upload
  post_data['image'] = await handle_image_upload(image, post_data["_id"])

  # set author
  if post_data['author'] is None:
    post_data['author'] = {
      'firstname': post_data['create_user']["firstname"],
      'lastname': post_data['create_user']["lastname"],
    }

  # Handle alias uniqueness
  upd_alias = post_data['alias']
  alias_suffix = 2
  while await request.app.mongodb['posts'].find_one({'alias': upd_alias}):
    upd_alias = post_data['alias'] + '-' + str(alias_suffix)
    alias_suffix += 1
  post_data['alias'] = upd_alias

  # Insert post
  try:
    print("post_data", post_data)
    new_post = await request.app.mongodb["posts"].insert_one(post_data)
    created_post = await request.app.mongodb["posts"].find_one(
      {"_id": new_post.inserted_id})
    if created_post:
      return JSONResponse(status_code=status.HTTP_201_CREATED,
                          content=jsonable_encoder(PostDB(**created_post)))
    else:
      raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                          detail="Failed to create post")
  except Exception as e:
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=str(e))


# update Post
@router.patch("/{id}",
              response_model=PostDB,
              response_description="Update post")
async def update_post(
  request: Request,
  id: str,
  title: str = Form(...),
  alias: str = Form(...),
  content: str = Form(...),
  author: str = Form(None),
  published: bool = Form(False),
  token_payload: TokenPayload = Depends(auth.auth_wrapper),
  image: UploadFile = File(None)
) -> PostDB:
  if token_payload.roles not in [["ADMIN"]]:
    raise HTTPException(status_code=403, detail="Not authorized")

  # Prepare post data
  post_data = PostUpdate(
    title=title,
    alias=alias,
    content=content,
    author=json.loads(author) if author else None,
    published=published,
  ).dict(exclude_unset=True)
  post_data['update_date'] = datetime.utcnow().replace(microsecond=0)
  post_data['update_user'] = {
    "user_id": token_payload.sub,
    "firstname": token_payload.firstname,
    "lastname": token_payload.lastname
  }

  # Retrieve existing post
  existing_post = await request.app.mongodb["posts"].find_one({"_id": id})
  if not existing_post:
    raise HTTPException(status_code=404, detail=f"Post with id {id} not found")

  # Handle image upload
  post_data['image'] = await handle_image_upload(image, id)

  print("post_data", post_data)

  # Exclude unchanged data
  post_to_update = {
    k: v
    for k, v in post_data.items() if v != existing_post.get(k, None)
  }
  print("post_to_update", post_to_update)
  if not post_to_update or ('update_date' in post_to_update
                            and len(post_to_update) == 1):
    print("No changes to update")
    return JSONResponse(status_code=status.HTTP_200_OK,
                        content=jsonable_encoder(PostDB(**existing_post)))
  # Update post
  try:
    update_result = await request.app.mongodb["posts"].update_one(
      {"_id": id}, {"$set": post_to_update})
    if update_result.modified_count == 1:
      updated_post = await request.app.mongodb["posts"].find_one({"_id": id})
      return JSONResponse(status_code=status.HTTP_200_OK,
                          content=jsonable_encoder(PostDB(**updated_post)))
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        content="Failed to update post")
  except Exception as e:
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=str(e))


# delete post
@router.delete("/{alias}", response_description="Delete post")
async def delete_post(
  request: Request,
  alias: str,
  token_payload: TokenPayload = Depends(auth.auth_wrapper)) -> None:
  if token_payload.roles not in [["ADMIN"]]:
    raise HTTPException(status_code=403, detail="Not authorized")
  query = {"alias": alias}
  result = await request.app.mongodb["posts"].delete_one(query)
  if result.deleted_count == 1:
    return Response(status_code=status.HTTP_204_NO_CONTENT)
  raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                      detail=f"Post with alias {alias} not found")
