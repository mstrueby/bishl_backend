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
async def get_match(request: Request, id: str) -> MatchDB:
  if (match := await
      request.app.mongodb["matches"].find_one({"_id": id})) is not None:
    return MatchDB(**match)
  raise HTTPException(status_code=404, detail=f"Match with id {id} not found")


# create new match
@router.post("/", response_description="Add new match")
async def create_match(
  request: Request,
  match: MatchBase = Body(...),
  #userId=Depends(auth.auth_wrapper),
) -> MatchDB:
  print("match: ", match)
  matchData = my_jsonable_encoder(match)
  print("matchData: ", matchData)


  try:
    
    # First: add match to matchday in tournament
    filter = {"alias": match.matchHead.tournament.alias}
    update = {
      "$push": {
        "seasons.$[s].rounds.$[r].matchdays.$[md].matches": my_jsonable_encoder(match.matchHead)
      }
    }
    arrayFilters = [
      {
        "s.alias": match.matchHead.season.alias
      },
      {
        "r.alias": match.matchHead.round.alias
      },
      {
        "md.alias": match.matchHead.matchday.alias
      },
    ]
    print("do update")
    print("update: ", update)
    print("arryFilters: ", arrayFilters)
    result = await request.app.mongodb["tournaments"].update_one(
      filter=filter,
      update=update,
      array_filters=arrayFilters,
      upsert=False)
    if result.modified_count == 0:
      raise HTTPException(
        status_code=404,
        detail=
        f"Matchday with alias {match.matchHead.matchday.alias} not found in round {match.matchHead.round.alias} of season {match.matchHead.season.alias} of tournament {match.matchHead.tournament.alias}"
      )

    # Second: add match to collection matches
    print("insert into matches")
    result = await request.app.mongodb["matches"].insert_one(matchData)
    newMatch = await request.app.mongodb["matches"].find_one(
      {"_id": result.inserted_id})
    if newMatch:
      newMatchModel = MatchDB(**newMatch)
      return JSONResponse(status_code=status.HTTP_201_CREATED,
                          content=jsonable_encoder(newMatchModel))
    else:
      raise HTTPException(status_code=500, detail="Failed to create match")
  

  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))
