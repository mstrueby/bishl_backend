# filename: routers/matches.py
from typing import List
from fastapi import APIRouter, Request, Body, status, HTTPException, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from models.matches import MatchBase, MatchDB, MatchUpdate
from authentication import AuthHandler
from pymongo.errors import DuplicateKeyError
from utils import my_jsonable_encoder

router = APIRouter()
auth = AuthHandler()

# get all matches --> will be not implemented

# get one match by id
@router.get("/{id}", response_description="Get one match by id")
async def get_match(
  request: Request,
  id: str
) -> MatchDB:
  if (match := await request.app.mongodb["matches"].find_one({"_id": id})) is not None:
    return MatchDB(**match)
  raise HTTPException(
    status_code=404,
    detail=f"Match with id {id} not found")

# create new match
@router.post("/", response_description="Add new match")
async def create_match(
  request: Request,
  match: MatchBase = Body(...),
  #userId=Depends(auth.auth_wrapper),
) -> MatchDB:
  match = my_jsonable_encoder(match)
  print(match)
  try:
    new_match = await request.app.mongodb["matches"].insert_one(match)
    created_match = await request.app.mongodb["matches"].find_one({"_id": new_match.inserted_id})
    if created_match:
      return JSONResponse(status_code=status.HTTP_201_CREATED,
                          content=jsonable_encoder(MatchDB(**created_match)))
    else:
      raise HTTPException(status_code=500, detail="Failed to create match")
  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))