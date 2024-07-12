# filename routers/users.py
from typing import List
from fastapi import APIRouter, Request, Body, status, HTTPException, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
import os, httpx, asyncio
from models.users import UserBase, LoginBase, CurrentUser, UserUpdate
from authentication import AuthHandler, TokenPayload

router = APIRouter()
auth = AuthHandler()
BASE_URL = os.environ.get("BE_API_URL")


@router.post("/register", response_description="Register a new user")
async def register(
  request: Request, newUser: UserBase = Body(...)) -> UserBase:
  # Hash the password before inserting into the database
  newUser.password = auth.get_password_hash(newUser.password)
  newUser = jsonable_encoder(newUser)

  # Check for existing user or email
  existing_user = await request.app.mongodb["users"].find_one(
    {"email": newUser["email"]})
  if existing_user:
    raise HTTPException(
      status_code=status.HTTP_409_CONFLICT,
      detail=f"Email {newUser['email']} is already registered")

  # Insert the new user into the database
  result = await request.app.mongodb["users"].insert_one(newUser)
  created_user = await request.app.mongodb["users"].find_one(
    {"_id": result.inserted_id})

  token = auth.encode_token(created_user)
  response = CurrentUser(**created_user).dict()
  response["id"] = result.inserted_id

  return JSONResponse(status_code=status.HTTP_201_CREATED,
                      content={
                        "token": token,
                        "user": response
                      })


# login user
@router.post("/login", response_description="Login a user")
async def login(
  request: Request, loginUser: LoginBase = Body(...)) -> UserBase:

  existing_user = await request.app.mongodb["users"].find_one(
    {"email": loginUser.email})
  if (existing_user is None) or (not auth.verify_password(
      loginUser.password, existing_user["password"])):
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Incorrect email and/or password",
                        headers={"WWW-Authenticate": "Bearer"})

  token = auth.encode_token(existing_user)

  response = CurrentUser(**existing_user).dict()
  response["id"] = existing_user["_id"]
  response["roles"] = existing_user["roles"]

  return JSONResponse(status_code=status.HTTP_200_OK,
                      content={
                        "token": token,
                        "user": response
                      })


# get current user
@router.get("/me", response_description="Get current user")
async def me(
  request: Request, token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> UserBase:
  user_id = token_payload.sub
  user = await request.app.mongodb["users"].find_one({"_id": user_id})

  if not user:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                        detail="User not found")

  response = CurrentUser(**user).dict()
  response["id"] = user_id
  return JSONResponse(status_code=status.HTTP_200_OK, content=response)


# update user details
@router.patch("/me", response_description="Update a user")
async def update_user(
  request: Request,
  token_payload: TokenPayload = Depends(auth.auth_wrapper),
  user: UserUpdate = Body(...)
) -> UserBase:

  user = user.dict(exclude_unset=True)
  user.pop("id", None)
  user_id = token_payload.sub

  existing_user = await request.app.mongodb["users"].find_one({"_id": user_id})
  if not existing_user:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                        detail="User not found")
  print("existing_user", existing_user)
  user_to_update = {k: v for k, v in user.items() if v != existing_user.get(k)}
  if not user_to_update:
    print("No fields to update")
    response = CurrentUser(**existing_user).dict()
    response["id"] = user_id
    return JSONResponse(status_code=status.HTTP_304_NOT_MODIFIED,
                        content=response)
  try:
    print("update user:", user_to_update)
    update_result = await request.app.mongodb["users"].update_one(
      {"_id": user_id}, {"$set": user_to_update})

    if update_result.modified_count == 1:
      updated_user = await request.app.mongodb["users"].find_one(
        {"_id": user_id})
      response = CurrentUser(**updated_user).dict()
      response["id"] = user_id
      return JSONResponse(status_code=status.HTTP_200_OK, content=response)

    raise HTTPException(status_code=status.HTTP_304_NOT_MODIFIED,
                        detail="User not modified")
  except Exception as e:
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=str(e))


@router.get("/matches",
            response_description="All assigned matches for me as a referee")
async def get_assigned_matches(
  request: Request, token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> List:
  user_id = token_payload.sub
  user = await request.app.mongodb["users"].find_one({"_id": user_id})
  if not user:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                        detail="User not found")
  if "REFEREE" not in user["roles"]:
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                        detail="User is not a referee")

  # get all matches assigned to me as referee
  assigned_matches = await request.app.mongodb["assignments"].find({
    "referee.user_id":
    user_id,
    "status": {
      "$in": ["ASSIGNED", "ACCEPTED"]
    }
  }).to_list(None)
  if not assigned_matches:
    return JSONResponse(status_code=status.HTTP_200_OK, content=[])

  print("assigned_matches", assigned_matches)
  match_ids = [match['match_id'] for match in assigned_matches]
  print("match_ids", match_ids)
  matches = []
  # Make async HTTP requests to fetch match details
  async with httpx.AsyncClient() as client:
    tasks = [
      client.get(f"{BASE_URL}/matches/{match_id}") for match_id in match_ids
    ]
    responses = await asyncio.gather(*tasks)
    matches = [response.json() for response in responses]
  return JSONResponse(status_code=status.HTTP_200_OK, content=matches)
