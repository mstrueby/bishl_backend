from fastapi import APIRouter, HTTPException, UploadFile, File, Request, Body, Depends, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from models.posts import PostBase, PostDB, PostUpdate
from typing import List
from utils import configure_cloudinary
from pymongo import MongoClient
from bson import ObjectId
from authentication import AuthHandler, TokenPayload
from datetime import datetime
import cloudinary
import cloudinary.uploader

router = APIRouter()
auth = AuthHandler()

configure_cloudinary()


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
  post: PostBase = Body(...),
  token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> PostDB:
  if token_payload.roles not in [["ADMIN"]]:
    raise HTTPException(status_code=403, detail="Not authorized")
  # data preparation
  post_data = jsonable_encoder(post)

  if post_data['create_date'] is None:
    post_data['create_date'] = datetime.utcnow().replace(microsecond=0)
  else:
    post_data['create_date'] = datetime.strptime(post_data['create_date'],
                                                 '%Y-%m-%dT%H:%M:%S')
  if post_data['update_date'] is not None:
    post_data['update_date'] = datetime.strptime(post_data['update_date'],
                                                 '%Y-%m-%dT%H:%M:%S')
  # get create user
  create_user = await request.app.mongodb["users"].find_one({
    "_id":
    post_data['create_user_id']
    if post_data['create_user_id'] is not None else token_payload.sub
  })
  if not create_user:
    create_user = await request.app.mongodb["users"].find_one(
      {"_id": token_payload.sub})
  post_data['create_user'] = {}
  post_data['create_user']['user_id'] = create_user["_id"]
  post_data['create_user']['firstname'] = create_user["firstname"]
  post_data['create_user']['lastname'] = create_user["lastname"]
  del post_data['create_user_id']

  # get update user
  post_data['update_user'] = None
  if post_data['update_user_id'] is not None:
    update_user = await request.app.mongodb["users"].find_one(
      {"_id": post_data['update_user_id']})
    if update_user:
      post_data['update_user'] = {}
      post_data['update_user']['user_id'] = update_user["_id"]
      post_data['update_user']['firstname'] = update_user["firstname"]
      post_data['update_user']['lastname'] = update_user["lastname"]
  del post_data['update_user_id']

  # get author
  if post_data['author'] is None:
    post_data['author'] = {}
    post_data['author']['firstname'] = token_payload.firstname
    post_data['author']['lastname'] = token_payload.lastname
  
  # check if alias already exists, add number to alias
  alias = post_data['alias']
  alias_suffix = 2
  while await request.app.mongodb['posts'].find_one({'alias': alias}):
    alias = post_data['alias'] + '-' + str(alias_suffix)
    alias_suffix += 1
  post_data['alias'] = alias
  # insert post
  try:
    new_post = await request.app.mongodb["posts"].insert_one(post_data)
    created_post = await request.app.mongodb["posts"].find_one(
      {"_id": new_post.inserted_id})
    if created_post:
      return JSONResponse(status_code=status.HTTP_201_CREATED,
                          content=jsonable_encoder(PostDB(**created_post)))
    else:
      raise HTTPException(status_code=500, detail="Failed to create post")
  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))


# update Post
@router.patch("/{id}",
              response_model=PostDB,
              response_description="Update post")
async def update_post(
  request: Request,
  id: str,
  post: PostUpdate = Body(...),
  token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> PostDB:
  if token_payload.roles not in [["ADMIN"]]:
    raise HTTPException(status_code=403, detail="Not authorized")
  post_data = post.dict(exclude_unset=True)
  post_data.pop("id", None)
  print("post: ", post)
  
  existing_post = await request.app.mongodb["posts"].find_one({"_id": id})
  if not existing_post:
    raise HTTPException(status_code=404, detail=f"Post with id {id} not found")

  # date data preparation
  if 'update_date' not in post_data:
    post_data['update_date'] = datetime.utcnow().replace(microsecond=0)
    
  # get create user
  if 'create_user_id' in post_data:
    create_user = await request.app.mongodb["users"].find_one({
      "_id":
      post_data['create_user_id']
      if post_data['create_user_id'] is not None else token_payload.sub
    })
    if not create_user:
      create_user = await request.app.mongodb["users"].find_one(
        {"_id": token_payload.sub})
    post_data['create_user'] = {}
    post_data['create_user']['user_id'] = create_user["_id"]
    post_data['create_user']['firstname'] = create_user["firstname"]
    post_data['create_user']['lastname'] = create_user["lastname"]
    del post_data['create_user_id']

  # get update user
  post_data['update_user'] = None
  if post_data['update_user_id'] is not None:
    update_user = await request.app.mongodb["users"].find_one(
      {"_id": post_data['update_user_id']})
    if update_user:
      post_data['update_user'] = {}
      post_data['update_user']['user_id'] = update_user["_id"]
      post_data['update_user']['firstname'] = update_user["firstname"]
      post_data['update_user']['lastname'] = update_user["lastname"]
  del post_data['update_user_id']
  
  #exclude unchanged data
  post_to_update = {
    k: v
    for k, v in post_data.items() if v != existing_post.get(k, None)
  }  
  if not post_to_update:
    print("no update needed")
    return PostDB(**existing_post)
  try:
    print("post_to_update: ", post_to_update)
    update_result = await request.app.mongodb["posts"].update_one(
      {"_id": id}, {"$set": post_to_update})
    if update_result.modified_count == 1:
      if (updated_post := await
          request.app.mongodb["posts"].find_one({"_id": id})) is not None:
        return PostDB(**updated_post)
    return PostDB(**existing_post)
  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))


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


"""
@router.post("/{article_id}/upload_image", response_model=ArticleResponse)
async def upload_article_image(article_id: str, file: UploadFile = File(...)):
  # Save the file temporarily
  file_path = f"temp/{file.filename}"
  with open(file_path, "wb") as buffer:
    buffer.write(file.file.read())

  # Upload the image to Cloudinary
  image_url = upload_image_to_cloudinary(file_path)

  # Update the article with the image URL
  result = articles_collection.update_one({"_id": ObjectId(article_id)},
                                          {"$set": {
                                            "image_url": image_url
                                          }})
  if result.matched_count == 0:
    raise HTTPException(status_code=404, detail="Article not found")

  updated_article = articles_collection.find_one({"_id": ObjectId(article_id)})
  return ArticleResponse(**updated_article)
"""
