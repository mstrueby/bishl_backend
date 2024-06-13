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
  matchData = my_jsonable_encoder(match)
  print("matchData: ", matchData)
  
  # remove some attibutes from match
  matchHeader = matchData.copy()
  print("matchData 2 : ", matchData)
  
  matchHeader['homeTeam'].pop('roster', None)
  matchHeader['awayTeam'].pop('roster', None)
  matchHeader.pop('scoreEvents', None)
  matchHeader.pop('penaltyEvents', None)
  print("reduced match: ", matchHeader)
  
  # renew matchData, because is some how modified by copy()
  matchData = my_jsonable_encoder(match)
  
  try:
    
    # First: add match to matchday in tournament
    filter = {"alias": match.tournament.alias}
    update = {
      "$push": {
        "seasons.$[s].rounds.$[r].matchdays.$[md].matches": (matchHeader)
      }
    }
    arrayFilters = [
      {
        "s.alias": match.season.alias
      },
      {
        "r.alias": match.round.alias
      },
      {
        "md.alias": match.matchday.alias
      },
    ]
    print("do update")
    print("update tournament: ", update)
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
        f"Matchday with alias {match.matchday.alias} not found in round {match.round.alias} of season {match.season.alias} of tournament {match.tournament.alias}"
      )

    # Second: add match to collection matches
    print("insert into matches") 
    print("matchData: ", matchData)
    
    result = await request.app.mongodb["matches"].insert_one(matchData)
    newMatch = await request.app.mongodb["matches"].find_one(
      {"_id": result.inserted_id})

    # lastly: return complete match document
    if newMatch:
      newMatchModel = MatchDB(**newMatch)
      return JSONResponse(status_code=status.HTTP_201_CREATED,
                          content=jsonable_encoder(newMatchModel))
    else:
      raise HTTPException(status_code=500, detail="Failed to create match")
  

  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))
