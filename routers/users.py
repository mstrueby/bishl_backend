# filename routers/users.py
from typing import List
from fastapi import APIRouter, Request, Body, status, HTTPException, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
import os
import httpx
from models.assignments import AssignmentDB
from models.users import UserBase, LoginBase, CurrentUser, UserUpdate
from models.matches import MatchDB
from authentication import AuthHandler, TokenPayload
from datetime import date

router = APIRouter()
auth = AuthHandler()
BASE_URL = os.environ.get("BE_API_URL")


@router.post("/register",
             response_description="Register a new user",
             response_model=CurrentUser)
async def register(
    request: Request, newUser: UserBase = Body(...)) -> JSONResponse:
  mongodb = request.app.state.mongodb
  # Hash the password before inserting into the database
  newUser.password = auth.get_password_hash(newUser.password)

  # Check for existing user or email
  existing_user = await mongodb["users"].find_one({"email": newUser.email})
  if existing_user:
    raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                        detail=f"Email {newUser.email} is already registered")

  # Insert the new user into the database
  newUser_data = jsonable_encoder(newUser)
  result = await mongodb["users"].insert_one(newUser_data)
  created_user = await request.app.state.mongodb["users"].find_one(
      {"_id": result.inserted_id})

  token = auth.encode_token(created_user)
  response = CurrentUser(**created_user)

  return JSONResponse(status_code=status.HTTP_201_CREATED,
                      content={
                          "token": token,
                          "user": jsonable_encoder(response)
                      })


# login user
@router.post("/login",
             response_description="Login a user",
             response_model=CurrentUser)
async def login(
    request: Request, loginUser: LoginBase = Body(...)) -> JSONResponse:
  mongodb = request.app.state.mongodb
  existing_user = await mongodb["users"].find_one({"email": loginUser.email})
  if (existing_user is None) or (not auth.verify_password(
      loginUser.password, existing_user["password"])):
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Incorrect email and/or password",
                        headers={"WWW-Authenticate": "Bearer"})

  token = auth.encode_token(existing_user)

  response = CurrentUser(**existing_user)

  return JSONResponse(status_code=status.HTTP_200_OK,
                      content={
                          "token": token,
                          "user": jsonable_encoder(response)
                      })


# get current user
@router.get("/me",
            response_description="Get current user",
            response_model=CurrentUser)
async def me(
    request: Request, token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> JSONResponse:
  mongodb = request.app.state.mongodb
  user_id = token_payload.sub
  user = await mongodb["users"].find_one({"_id": user_id})

  if not user:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                        detail="User not found")

  response = CurrentUser(**user)
  return JSONResponse(status_code=status.HTTP_200_OK,
                      content=jsonable_encoder(response))


# update user details
@router.patch("/me",
              response_description="Update a user",
              response_model=CurrentUser)
async def update_user(request: Request,
                      token_payload: TokenPayload = Depends(auth.auth_wrapper),
                      user: UserUpdate = Body(...)):
  mongodb = request.app.state.mongodb
  user_dict = user.dict(exclude_unset=True)
  user_dict.pop("id", None)
  user_id = token_payload.sub

  existing_user = await mongodb["users"].find_one({"_id": user_id})
  if not existing_user:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                        detail="User not found")
  print("existing_user", existing_user)
  user_to_update = {
      k: v
      for k, v in user_dict.items() if v != existing_user.get(k)
  }
  if not user_to_update:
    print("No fields to update")
    return Response(status_code=status.HTTP_304_NOT_MODIFIED)

  try:
    print("update user:", user_to_update)
    update_result = await mongodb["users"].update_one({"_id": user_id},
                                                      {"$set": user_to_update})

    if update_result.modified_count == 1:
      updated_user = await mongodb["users"].find_one({"_id": user_id})
      response = CurrentUser(**updated_user)
      return JSONResponse(status_code=status.HTTP_200_OK,
                          content=jsonable_encoder(response))

    raise HTTPException(status_code=status.HTTP_304_NOT_MODIFIED,
                        detail="User not modified")
  except Exception as e:
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=str(e))


@router.get("/matches",
            response_description="All assigned matches for me as a referee",
            response_model=List[MatchDB])
async def get_assigned_matches(
    request: Request, token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> JSONResponse:
  mongodb = request.app.state.mongodb
  user_id = token_payload.sub
  user = await mongodb["users"].find_one({"_id": user_id})
  if not user:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                        detail="User not found")
  if "REFEREE" not in user["roles"]:
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                        detail="User is not a referee")

  # Fetch matches assigned to me as referee using the GET endpoint
  async with httpx.AsyncClient() as client:
    current_date = date.today().strftime('%Y-%m-%d')
    response = await client.get(
        f"{BASE_URL}/matches/?referee={user_id}&date_from={current_date}")
    print("response", response)
    # Parse matches into a list of MatchDB objects
    matches_list = [MatchDB(**match) for match in response.json()]
    return JSONResponse(status_code=status.HTTP_200_OK, content=matches_list)


@router.get("/assignments",
            response_description="All assignments by me",
            response_model=List[AssignmentDB])
async def get_assignments(
    request: Request, token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> JSONResponse:
  mongodb = request.app.state.mongodb
  user_id = token_payload.sub
  user = await mongodb["users"].find_one({"_id": user_id})
  if not user:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                        detail="User not found")
  if "REFEREE" not in user["roles"]:
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                        detail="User is not a referee")

  # Fetch assignments assigned to me using the GET endpoint
  async with httpx.AsyncClient() as client:
    response = await client.get(f"{BASE_URL}/assignments/?referee={user_id}")
    print("response", response)
    # Parse assignments into a list of AssignmentDB objects
    assignments_list = [
        AssignmentDB(**assignment) for assignment in response.json()
    ]
    return JSONResponse(status_code=status.HTTP_200_OK,
                        content=assignments_list)


@router.get("/referees",
            response_description="Get all referees",
            response_model=List[CurrentUser])
async def get_all_referees(
    request: Request, token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> JSONResponse:
  mongodb = request.app.state.mongodb
  if not any(role in ['ADMIN', 'REFEREE', 'REF_ADMIN']
             for role in token_payload.roles):
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                        detail="Not authorized")

  referees_cursor = mongodb["users"].find({"roles": "REFEREE"})
  referees = await referees_cursor.to_list(length=None)

  response = [CurrentUser(**referee) for referee in referees]
  return JSONResponse(status_code=status.HTTP_200_OK,
                      content=jsonable_encoder(response))
