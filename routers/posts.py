from fastapi import APIRouter, HTTPException, Form, UploadFile, File, Request, Depends, status, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
import json

from pydantic import HttpUrl
from models.posts import PostBase, PostDB, PostUpdate, Revision, User
from models.responses import PaginatedResponse
from typing import List, Optional
from utils import configure_cloudinary, my_jsonable_encoder
from utils.pagination import PaginationHelper
from authentication import AuthHandler, TokenPayload
from datetime import datetime
import cloudinary
import cloudinary.uploader
import os
from exceptions import (
    ResourceNotFoundException,
    ValidationException,
    DatabaseOperationException,
    AuthorizationException
)
from logging_config import logger

router = APIRouter()
auth = AuthHandler()
configure_cloudinary()

DEBUG_LEVEL = int(os.environ['DEBUG_LEVEL'])


async def handle_image_upload(image: UploadFile, public_id: str):
  if image:
    result = cloudinary.uploader.upload(
        image.file,
        folder="posts",
        public_id=public_id,
        overwrite=True,
        resource_type="image",
        format='jpg',
        transformation=[{
            'width': 1080,
            # 'aspect_ratio': '16:9',
            # 'crop': 'fill',
            # 'gravity': 'auto',
            'effect': 'sharpen:100',
        }],
    )
    print(f"Post Image uploaded: {result['url']}")
    return result['url']


# Helper function to delete file from Cloudinary
async def delete_from_cloudinary(image_url: str):
  if image_url:
    try:
      public_id = image_url.rsplit('/', 1)[-1].split('.')[0]
      result = cloudinary.uploader.destroy(f"posts/{public_id}")
      print("Post Image deleted from Cloudinary:", f"posts/{public_id}")
      print("Result:", result)
      return result
    except Exception as e:
      raise HTTPException(status_code=500, detail=str(e))


# list all posts
@router.get("/",
            response_description="List all posts",
            response_model=PaginatedResponse[PostDB])
async def get_posts(
    request: Request,
    featured: Optional[bool] = None,
    published: Optional[bool] = None,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(25, ge=1, le=100, description="Items per page")
) -> JSONResponse:
  mongodb = request.app.state.mongodb
  query = {"deleted": False}
  if featured is not None:
    query["featured"] = featured
  if published is not None:
    query["published"] = published
  
  items, total_count = await PaginationHelper.paginate_query(
      collection=mongodb["posts"],
      query=query,
      page=page,
      page_size=page_size,
      sort=[("updateDate", -1)]
  )
  
  paginated_result = PaginationHelper.create_response(
      items=[PostDB(**post) for post in items],
      page=page,
      page_size=page_size,
      total_count=total_count,
      message=f"Retrieved {len(items)} posts"
  )
  
  return JSONResponse(status_code=status.HTTP_200_OK,
                      content=jsonable_encoder(paginated_result))

# get post by alias
@router.get("/{alias}",
            response_description="Get post by alias",
            response_model=PostDB)
async def get_post(request: Request, alias: str) -> JSONResponse:
  mongodb = request.app.state.mongodb
  query = {"alias": alias}
  post = await mongodb["posts"].find_one(query)
  if not post:
    raise ResourceNotFoundException(
        resource_type="Post",
        resource_id=alias,
        details={"query_field": "alias"}
    )
  return JSONResponse(status_code=status.HTTP_200_OK,
                      content=jsonable_encoder(PostDB(**post)))


# create post
@router.post("/", response_model=PostDB, response_description="Create post")
async def create_post(
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    alias: str = Form(...),
    author: str = Form(None),  # JSON String
    published: bool = Form(False),
    featured: bool = Form(False),
    deleted: bool = Form(False),
    publishDateFrom: Optional[datetime] = Form(None),
    publishDateTo: Optional[datetime] = Form(None),
    legacyId: int = Form(None),
    image: UploadFile = File(None),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> JSONResponse:
  mongodb = request.app.state.mongodb
  if not any(role in token_payload.roles for role in ["ADMIN", "AUTHOR"]):
    raise AuthorizationException(
        message="Admin or Author role required",
        details={"user_roles": token_payload.roles}
    )

  # Data preparation
  post = PostBase(
      title=title,
      alias=alias,
      content=content,
      author=json.loads(author) if author else None,
      published=published,
      featured=featured,
      deleted=deleted,
  )
  post_data = jsonable_encoder(post)

  # user and dates
  post_data['createDate'] = datetime.now().replace(microsecond=0)
  post_data['createUser'] = {
      "userId": token_payload.sub,
      "firstName": token_payload.firstName,
      "lastName": token_payload.lastName
  }
  post_data['updateUser'] = post_data['createUser']
  post_data['updateDate'] = post_data['createDate']
  post_data['publishDateFrom'] = publishDateFrom
  post_data['publishDateTo'] = publishDateTo


  # set author
  if post_data['author'] is None:
    post_data['author'] = {
        'firstName': post_data['createUser']["firstName"],
        'lastName': post_data['createUser']["lastName"],
    }

  # Handle alias uniqueness
  upd_alias = post_data['alias']
  alias_suffix = 2
  while await mongodb['posts'].find_one({'alias': upd_alias}):
    upd_alias = post_data['alias'] + '-' + str(alias_suffix)
    alias_suffix += 1
  post_data['alias'] = upd_alias

  # Handle image upload
  if image:
    post_data['imageUrl'] = await handle_image_upload(image, post_data["alias"])

  #revision
  revision = Revision(updateData=post_data,
                      updateUser=post_data['createUser'],
                      updateDate=post_data['createDate'])
  post_data['revisions'] = [my_jsonable_encoder(revision)]

  # Insert post
  try:
    print("post_data", post_data)
    new_post = await mongodb["posts"].insert_one(post_data)
    created_post = await mongodb["posts"].find_one(
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
              response_model_by_alias=True)
async def update_post(
    request: Request,
    id: str,
    title: Optional[str] = Form(None),
    alias: Optional[str] = Form(None),
    content: Optional[str] = Form(None),
    author: Optional[str] = Form(None),
    published: Optional[bool] = Form(None),
    featured: Optional[bool] = Form(None),
    deleted: Optional[bool] = Form(None),
    publishDateFrom: Optional[datetime] = Form(None),
    publishDateTo: Optional[datetime] = Form(None),
    image: Optional[UploadFile] = File(None),
    imageUrl: Optional[HttpUrl] = Form(None),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> Response:
  # Handle alias uniqueness if alias is being updated
  if alias:
      upd_alias = alias
      alias_suffix = 2
      while await request.app.state.mongodb['posts'].find_one({'alias': upd_alias, '_id': {'$ne': id}}):
          upd_alias = f"{alias}-{alias_suffix}"
          alias_suffix += 1
      alias = upd_alias

  mongodb = request.app.state.mongodb
  if not any(role in token_payload.roles for role in ["ADMIN", "AUTHOR"]):
    raise HTTPException(status_code=403, detail="Nicht authorisiert")

  # Retrieve existing post
  existing_post = await mongodb["posts"].find_one({"_id": id})
  if not existing_post:
    raise HTTPException(status_code=404, detail=f"Post with id {id} not found")

  # Prepare post data
  try:
    post_data = PostUpdate(
        title=title,
        alias=alias,
        content=content,
        author=json.loads(author) if author else None,
        published=published,
        featured=featured,
        deleted=deleted,
    ).model_dump(exclude_none=True)
  except ValueError as e:
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="Failed to parse input data") from e
  post_data.pop('id', None)
  post_data['updateDate'] = datetime.now().replace(microsecond=0)
  post_data['updateUser'] = {
      "userId": token_payload.sub,
      "firstName": token_payload.firstName,
      "lastName": token_payload.lastName
  }

  post_data['publishDateFrom'] = publishDateFrom
  post_data['publishDateTo'] = publishDateTo

  # Handle image upload
  if image:
    post_data['imageUrl'] = await handle_image_upload(image, post_data['alias'])
  elif imageUrl:
    post_data['imageUrl'] = imageUrl
  elif existing_post['imageUrl']:
    await delete_from_cloudinary(existing_post['imageUrl'])
    post_data['imageUrl'] = None
  else:
    post_data['imageUrl'] = None

  print("post_data", post_data)

  # Exclude unchanged data
  post_to_update = {
      k: v
      for k, v in post_data.items() if v != existing_post.get(k, None)
  }
  print("post_to_update", post_to_update)
  if not post_to_update or ('updateDate' in post_to_update
                            and len(post_to_update) == 1):
    print("No changes to update")
    return Response(status_code=status.HTTP_304_NOT_MODIFIED)

  # Create a User instance from dictionary
  update_user_instance = User(userId=post_data['updateUser']["userId"],
                              firstName=post_data['updateUser']["firstName"],
                              lastName=post_data['updateUser']["lastName"])

  revision = Revision(updateData={
      k: v
      for k, v in post_to_update.items()
      if k != 'updateUser' and k != 'updateDate'
  },
                      updateUser=update_user_instance,
                      updateDate=post_data['updateDate'])
  if 'revisions' not in existing_post:
    post_to_update['revisions'] = [my_jsonable_encoder(revision)]
  else:
    post_to_update['revisions'] = existing_post['revisions']
    post_to_update['revisions'].append(my_jsonable_encoder(revision))

  # Update post
  try:
    update_result = await mongodb["posts"].update_one({"_id": id},
                                                      {"$set": post_to_update})
    if update_result.modified_count == 1:
      updated_post = await mongodb["posts"].find_one({"_id": id})
      return JSONResponse(status_code=status.HTTP_200_OK,
                          content=jsonable_encoder(PostDB(**updated_post)))
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        content="Failed to update post")
  except Exception as e:
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=str(e))


# delete post
@router.delete("/{id}", response_description="Delete post")
async def delete_post(
    request: Request,
    id: str,
    token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> Response:
  mongodb = request.app.state.mongodb
  if "ADMIN" not in token_payload.roles:
    raise HTTPException(status_code=403, detail="Nicht authorisiert")
  existing_post = await mongodb["posts"].find_one({"_id": id})
  if not existing_post:
    raise HTTPException(status_code=404,
                        detail=f"Post with id {id} not found")
  result = await mongodb["posts"].delete_one({"_id": id})
  if result.deleted_count == 1:
    await delete_from_cloudinary(existing_post['imageUrl'])
    return Response(status_code=status.HTTP_204_NO_CONTENT)
  raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                      detail=f"Post with id {id} not found")