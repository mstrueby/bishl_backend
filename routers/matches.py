# filename: routers/matches.py
from fastapi import APIRouter, Request, Body, status, HTTPException, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from models.matches import MatchBase, MatchDB, MatchUpdate
from authentication import AuthHandler
from utils import my_jsonable_encoder, parse_time_to_seconds, parse_time_from_seconds

router = APIRouter()
auth = AuthHandler()


async def get_match_object(mongodb, match_id: str) -> MatchDB:
  match = await mongodb["matches"].find_one({"_id": match_id})
  if not match:
    raise HTTPException(status_code=404,
                        detail=f"Match with id {match_id} not found")

  # parse scores.matchSeconds to a string format
  for score in match.get("home", {}).get("scores", []):
    score["matchSeconds"] = parse_time_from_seconds(score["matchSeconds"])
  for score in match.get("away", {}).get("scores", []):
    score["matchSeconds"] = parse_time_from_seconds(score["matchSeconds"])
  # parse penalties.matchSeconds[Start|End] to a string format
  for penalty in match.get("home", {}).get("penalties", []):
    penalty["matchSecondsStart"] = parse_time_from_seconds(
      penalty["matchSecondsStart"])
    if penalty.get('matchSecondsEnd') is not None:
      penalty["matchSecondsEnd"] = parse_time_from_seconds(
        penalty["matchSecondsEnd"])
  for penalty in match.get("away", {}).get("penalties", []):
    penalty["matchSecondsStart"] = parse_time_from_seconds(
      penalty["matchSecondsStart"])
    if penalty.get('matchSecondsEnd') is not None:
      penalty["matchSecondsEnd"] = parse_time_from_seconds(
        penalty["matchSecondsEnd"])

  return MatchDB(**match)


# get all matches --> will be not implemented


# get one match by id
@router.get("/{match_id}", response_description="Get one match by id")
async def get_match(request: Request, match_id: str) -> MatchDB:
  match = await get_match_object(request.app.mongodb, match_id)
  return JSONResponse(status_code=status.HTTP_200_OK,
                      content=jsonable_encoder(match))


# create new match
@router.post("/", response_description="Add new match")
async def create_match(
    request: Request,
    match: MatchBase = Body(...),
    user_id=Depends(auth.auth_wrapper),
) -> MatchDB:
  match_data = my_jsonable_encoder(match)

  # remove some attibutes from match
  match_header = match_data.copy()

  match_header['home'].pop('roster', None)
  match_header['home'].pop('scores', None)
  match_header['home'].pop('penalties', None)
  match_header['away'].pop('roster', None)
  match_header['away'].pop('scores', None)
  match_header['away'].pop('penalties', None)
  match_header.pop('tournament', None)
  match_header.pop('season', None)
  match_header.pop('round', None)
  match_header.pop('matchday', None)
  print("reduced match: ", match_header)

  # renew match_data, because is some how modified by copy()
  match_data = my_jsonable_encoder(match)
  for score in match_data.get("home", {}).get("scores", []):
    score["matchSeconds"] = parse_time_to_seconds(score["matchSeconds"])
  for score in match_data.get("away", {}).get("scores", []):
    score["matchSeconds"] = parse_time_to_seconds(score["matchSeconds"])
  # parse penalties.matchSeconds[Start|End] to a string format
  for penalty in match_data.get("home", {}).get("penalties", []):
    penalty["matchSecondsStart"] = parse_time_to_seconds(
      penalty["matchSecondsStart"])
    if penalty.get('matchSecondsEnd') is not None:
      penalty["matchSecondsEnd"] = parse_time_to_seconds(
        penalty["matchSecondsEnd"])
  for penalty in match_data.get("away", {}).get("penalties", []):
    penalty["matchSecondsStart"] = parse_time_to_seconds(
      penalty["matchSecondsStart"])
    if penalty.get('matchSecondsEnd') is not None:
      penalty["matchSecondsEnd"] = parse_time_to_seconds(
        penalty["matchSecondsEnd"])

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
    print("do update, match_header: ", match_header)
    print("update tournament: ", update)
    print("arryFilters: ", array_filters)
    result = await request.app.mongodb["tournaments"].update_one(
      filter=filter, update=update, array_filters=array_filters, upsert=False)
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

    # lastly: return complete match document
    new_match = await get_match_object(request.app.mongodb, result.inserted_id)
    return JSONResponse(status_code=status.HTTP_201_CREATED,
                        content=jsonable_encoder(new_match))

  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))


# ------ update match
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
  for score in match_data.get("home", {}).get("scores", []):
    score["matchSeconds"] = parse_time_to_seconds(score["matchSeconds"])
  for score in match_data.get("away", {}).get("scores", []):
    score["matchSeconds"] = parse_time_to_seconds(score["matchSeconds"])
  # parse penalties.matchSeconds[Start|End] to a string format
  for penalty in match_data.get("home", {}).get("penalties", []):
    penalty["matchSecondsStart"] = parse_time_to_seconds(
      penalty["matchSecondsStart"])
    if penalty.get('matchSecondsEnd') is not None:
      penalty["matchSecondsEnd"] = parse_time_to_seconds(
        penalty["matchSecondsEnd"])
  for penalty in match_data.get("away", {}).get("penalties", []):
    penalty["matchSecondsStart"] = parse_time_to_seconds(
      penalty["matchSecondsStart"])
    if penalty.get('matchSecondsEnd') is not None:
      penalty["matchSecondsEnd"] = parse_time_to_seconds(
        penalty["matchSecondsEnd"])

  print("match_data: ", match_data)

  existing_match = await request.app.mongodb["matches"].find_one(
    {"_id": match_id})
  if existing_match is None:
    raise HTTPException(status_code=404,
                        detail=f"Match with id {match_id} not found")

  # exclude unchanged data
  match_to_update = {
    k: v
    for k, v in match_data.items() if v != existing_match.get(k)
  }

  if match_to_update:
    try:
      # update match in matches
      print("match to update: ", match_to_update)
      update_result = await request.app.mongodb["matches"].update_one(
        {"_id": match_id}, {"$set": match_data})
      print("update result: ", update_result.modified_count)
      if update_result.modified_count == 0:
        raise HTTPException(status_code=404,
                            detail=f"Match with id {match_id} not found")

      else:
        # update match header data in tournament/matchday/matches
        print("second update")
        match_header = existing_match.copy()
        match_header.update(match_to_update)
        if 'home' in match_header and 'roster' in match_header['home']:
          match_header['home'].pop('roster')
        if 'home' in match_header and 'scores' in match_header['home']:
          match_header['home'].pop('scores')
        if 'home' in match_header and 'penalties' in match_header['home']:
          match_header['home'].pop('penalties')
        if 'away' in match_header and 'roster' in match_header['away']:
          match_header['away'].pop('roster')
        if 'away' in match_header and 'scores' in match_header['away']:
          match_header['away'].pop('scores')
        if 'away' in match_header and 'penalties' in match_header['away']:
          match_header['away'].pop('penalties')
        if 'tournament' in match_header:
          match_header.pop('tournament')
        if 'season' in match_header:
          match_header.pop('season')
        if 'round' in match_header:
          match_header.pop('round')
        if 'matchday' in match_header:
          match_header.pop('matchday')
        print("match_header: ", match_header)
        print("existing match: ", existing_match)

      if match_header is not None:
        filter = {"alias": existing_match['tournament']['alias']}
        print("filter: ", filter)
        update = {
          "$set": {
            "seasons.$[s].rounds.$[r].matchdays.$[md].matches.$[m]":
            match_header
          }
        }
        array_filters = [{
          "s.alias": existing_match['season']['alias']
        }, {
          "r.alias": existing_match['round']['alias']
        }, {
          "md.alias": existing_match['matchday']['alias']
        }, {
          "m._id": existing_match['_id']
        }]
        print("do update")
        print("update tournament: ", update)
        print("arrayFilters: ", array_filters)
        result = await request.app.mongodb["tournaments"].update_one(
          filter=filter,
          update=update,
          array_filters=array_filters,
          upsert=False)
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
  updated_match = await get_match_object(request.app.mongodb, match_id)
  return JSONResponse(status_code=status.HTTP_200_OK,
                      content=jsonable_encoder(updated_match))


# delete match
@router.delete("/{match_id}", response_description="Delete match")
async def delete_match(
  request: Request, match_id: str,
  user_id: str = Depends(auth.auth_wrapper)) -> None:
  # Find the match
  match = await request.app.mongodb["matches"].find_one({"_id": match_id})
  if match is None:
    raise HTTPException(status_code=404,
                        detail=f"Match with id {match_id} not found")

  try:
    # delete in mathces
    result = await request.app.mongodb["matches"].delete_one({"_id": match_id})

    # delete match in tournaments collection
    filter = {"alias": match['tournament']['alias']}
    update = {
      "$pull": {
        "seasons.$[s].rounds.$[r].matchdays.$[md].matches": {
          "_id": match_id
        }
      }
    }
    array_filters = [
      {
        "s.alias": match['season']['alias']
      },
      {
        "r.alias": match['round']['alias']
      },
      {
        "md.alias": match['matchday']['alias']
      },
    ]
    print("filter: ", filter)
    print("update: ", update)
    print("array_filters: ", array_filters)

    # Perform the update
    result = await request.app.mongodb["tournaments"].update_one(
      filter=filter, update=update, array_filters=array_filters, upsert=False)

    if result.modified_count == 0:
      raise HTTPException(
        status_code=404,
        detail=
        f"Matchday with alias {match['matchday']['alias']} not found in round {match['round']['alias']} of season {match['season']['alias']} of tournament {match['tournament']['alias']}"
      )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))
