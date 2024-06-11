# filename routers/users.py
from typing import List
from fastapi import APIRouter, Request, Body, status, HTTPException, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from models.users import UserBase, LoginBase, CurrentUser
from authentication import AuthHandler

router = APIRouter()
auth = AuthHandler()


# register user
@router.post("/register", response_description="Register a new user")
async def register(
  request: Request, newUser: UserBase = Body(...)) -> UserBase:

  # hash the password before inserting into the database
  newUser.password = auth.get_password_hash(newUser.password)
  newUser = jsonable_encoder(newUser)

  # check for existing user or email
  existing_user = await request.app.mongodb["users"].find_one(
    {"email": newUser["email"]})
  if existing_user:
    if existing_user.get("email") == newUser["email"]:
      raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Email {newUser['email']} is already registered",
      )

  # insert the new user into the database
  result = await request.app.mongodb["users"].insert_one(newUser)
  created_user = await request.app.mongodb["users"].find_one(
    {"_id": result.inserted_id})

  response = CurrentUser(**created_user).dict()
  response["id"] = result.inserted_id

  return JSONResponse(status_code=status.HTTP_201_CREATED, content=response)


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

  token = auth.encode_token(existing_user["_id"])

  response = CurrentUser(**existing_user).dict()
  response["id"] = existing_user["_id"]

  return JSONResponse(status_code=status.HTTP_200_OK,
                      content={
                        "token": token,
                        "user": response
                      })


# get current user
@router.get("/me", response_description="Get current user")
async def me(request: Request, userId=Depends(auth.auth_wrapper)) -> UserBase:
  user = await request.app.mongodb["users"].find_one({"_id": userId})
  response = CurrentUser(**user).dict()
  response["id"] = userId
  return JSONResponse(status_code=status.HTTP_200_OK, content=response)
