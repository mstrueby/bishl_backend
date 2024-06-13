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
@router.get("/{match_id}", response_description="Get one match by id")
async def get_match(request: Request, match_id: str) -> MatchDB:
  if (match := await
      request.app.mongodb["matches"].find_one({"_id": match_id})) is not None:
    return MatchDB(**match)
  raise HTTPException(status_code=404, detail=f"Match with id {match_id} not found")


# create new match
@router.post("/", response_description="Add new match")
async def create_match(
  request: Request,
  match: MatchBase = Body(...),
  user_id=Depends(auth.auth_wrapper),
) -> MatchDB:
  match_data = my_jsonable_encoder(match)
  print("match_data: ", match_data)
  
  # remove some attibutes from match
  match_header = match_data.copy()
  print("match_data 2 : ", match_data)
  
  match_header['homeTeam'].pop('roster', None)
  match_header['awayTeam'].pop('roster', None)
  match_header.pop('scoreEvents', None)
  match_header.pop('penaltyEvents', None)
  print("reduced match: ", match_header)
  
  # renew match_data, because is some how modified by copy()
  match_data = my_jsonable_encoder(match)
  
  try:
    
    # First: add match to matchday in tournament
    filter = {"alias": match.tournament.alias}
    update = {
      "$push": {
        "seasons.$[s].rounds.$[r].matchdays.$[md].matches": (match_header)
      }
    }
    array_filters = [
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
    print("arryFilters: ", array_filters)
    result = await request.app.mongodb["tournaments"].update_one(
      filter=filter,
      update=update,
      array_filters=array_filters,
      upsert=False)
    if result.modified_count == 0:
      raise HTTPException(
        status_code=404,
        detail=
        f"Matchday with alias {match.matchday.alias} not found in round {match.round.alias} of season {match.season.alias} of tournament {match.tournament.alias}"
      )

    # Second: add match to collection matches
    print("insert into matches") 
    print("match_data: ", match_data)
    
    result = await request.app.mongodb["matches"].insert_one(match_data)
    new_match = await request.app.mongodb["matches"].find_one(
      {"_id": result.inserted_id})

    # lastly: return complete match document
    if new_match:
      new_match_model = MatchDB(**new_match)
      return JSONResponse(status_code=status.HTTP_201_CREATED,
                          content=jsonable_encoder(new_match_model))
    else:
      raise HTTPException(status_code=500, detail="Failed to create match")
  

  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))

# update match
@router.patch("/{match_id}", response_description="Update match")
async def update_match(
  request: Request,
  match_id: str,
  match: MatchUpdate = Body(...),
  user_id=Depends(auth.auth_wrapper)
) -> MatchDB:
  print("match: ", match)
  match_data = match.dict(exclude_unset=True)
  match_data.pop("id", None)
  print("match_data: ", match_data)

  existing_match = await request.app.mongodb["matches"].find_one({"_id": match_id})
  if existing_match is None:
    raise HTTPException(status_code=404, detail=f"Match with id {match_id} not found")

  # exclude unchanged data
  match_to_update = {
    k: v
    for k, v in match_data.items() if v != existing_match.get(k)
  }

  if match_to_update:
    try:
      print("match to update: ", match_to_update)
      update_result = await request.app.mongodb["matches"].update_one(
        {"_id": match_id}, {"$set": match_data})
      print("update result: ", update_result.modified_count)
      if update_result.modified_count == 0:
        raise HTTPException(
          status_code=404,
          detail=f"Match with id {match_id} not found")

      else:
        # update match header data in tournament/matchday/matches
        print("second update")
        match_header = match_data.copy()
        if 'homeTeam' in match_header and 'roster' in match_header['homeTeam']:
            match_header['homeTeam'].pop('roster')
        if 'awayTeam' in match_header and 'roster' in match_header['awayTeam']:
            match_header['awayTeam'].pop('roster')
        if 'scoreEvents' in match_header:
            match_header.pop('scoreEvents')
        if 'penaltyEvents' in match_header:
            match_header.pop('penaltyEvents')
        print("reduced match: ", match_header)
        print("existing match: ", existing_match)
        
      if match_header is not None:
        filter = {"alias": existing_match['tournament']['alias']}
        print("filter: ", filter)
        update = {
            "$push": {
                "seasons.$[s].rounds.$[r].matchdays.$[md].matches": (match_header)
            }
        }
        array_filters = [
            {"s.alias": existing_match['season']['alias']},
            {"r.alias": existing_match['round']['alias']},
            {"md.alias": existing_match['matchday']['alias']},
        ]
        print("do update")
        print("update tournament: ", update)
        print("arryFilters: ", array_filters)
        result = await request.app.mongodb["tournaments"].update_one(
            filter=filter,
            update=update,
            array_filters=array_filters,
            upsert=False
        )
        if result.modified_count == 0:
            raise HTTPException(
                status_code=404,
                detail=
                f"Matchday with alias {existing_match['matchday']['alias']} not found in round {existing_match['round']['alias']} of season {existing_match['season']['alias']} of tournament {existing_match['tournament']['alias']}"
            )

    except Exception as e:
      raise HTTPException(status_code=500, detail=str(e))
  else:
    print("No changes to update")

  # return updated match
  updated_match = await request.app.mongodb["matches"].find_one({"_id": match_id})
  if updated_match is not None:
    match_response = MatchDB(**updated_match)
    return JSONResponse(status_code=status.HTTP_200_OK,content=jsonable_encoder(match_response))
  else:
    raise HTTPException(status_code=500, detail=f"Fetch: Match with id {match_id} not found")
