# filename: routers/teams.py
from typing import List
from fastapi import APIRouter, Request, Body, status, HTTPException, Path, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from models.clubs import TeamBase, TeamDB, TeamUpdate
from authentication import AuthHandler, TokenPayload

router = APIRouter()
auth = AuthHandler()


# list all teams of one club
@router.get("/",
            response_description="List all teams of one club",
            response_model=List[TeamDB])
async def list_teams_of_one_club(
    request: Request,
    club_alias: str = Path(..., description="Club alias to list teams"),
) -> JSONResponse:
  mongodb = request.app.state.mongodb
  if (club := await
      mongodb["clubs"].find_one({"alias":
                                             club_alias})) is not None:
    teams = [TeamDB(**team) for team in (club.get("teams") or [])]
    return JSONResponse(status_code=status.HTTP_200_OK,
                        content=jsonable_encoder(teams))
  raise HTTPException(status_code=404,
                      detail=f"Club with alias {club_alias} not found")


# get one team of a club
@router.get("/{team_alias}",
            response_description="Get one team of a club",
            response_model=TeamDB)
async def get_team(
    request: Request,
    club_alias: str = Path(..., description="Club alias to get team"),
    team_alias: str = Path(..., description="Team alias to get"),
) -> JSONResponse:
  mongodb = request.app.state.mongodb
  if (club := await
      mongodb["clubs"].find_one({"alias":
                                             club_alias})) is not None:
    for team in club.get("teams", []):
      if team.get("alias") == team_alias:
        team_response = TeamDB(**team)
        return JSONResponse(status_code=status.HTTP_200_OK,
                            content=jsonable_encoder(team_response))
    raise HTTPException(
        status_code=404,
        detail=f"Team with alias {team_alias} not found for club {club_alias}")
  else:
    # Raise HTTPException if the club is not found
    raise HTTPException(status_code=404,
                        detail=f"Club with alias {club_alias} not found")


# create new team
@router.post("/",
             response_description="Add new team to a club",
             response_model=TeamDB)
async def create_team(
    request: Request,
    club_alias: str = Path(..., description="Club alias to create team for"),
    team: TeamBase = Body(..., description="Team data"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> JSONResponse:
  mongodb = request.app.state.mongodb
  if token_payload.roles not in [["ADMIN"]]:
    raise HTTPException(status_code=403, detail="Not authorized")
  print("create team")
  # check if club exists
  if (club := await
      mongodb["clubs"].find_one({"alias": club_alias})) is None:
    raise HTTPException(status_code=404,
                        detail=f"Club with alias {club_alias} not found")
  # check if team already exists
  if any(t.get("alias") == team.alias for t in club.get("teams", [])):
    raise HTTPException(
        status_code=409,
        detail=
        f"Team with alias {team.alias} already exists for club {club_alias}")

  # add team to club
  try:
    team_data = jsonable_encoder(team)
    result = await mongodb["clubs"].update_one(
        {"alias": club_alias}, {"$push": {
            "teams": team_data
        }})
    if result.modified_count == 1:
      # get inserted team
      updated_club = await mongodb["clubs"].find_one(
          {
              "alias": club_alias,
              "teams.alias": team.alias
          }, {
              "_id": 0,
              "teams.$": 1
          })
      if updated_club and "teams" in updated_club:
        inserted_team = updated_club["teams"][0]
        team_response = TeamDB(**inserted_team)
        return JSONResponse(status_code=status.HTTP_201_CREATED,
                            content=jsonable_encoder(team_response))
      else:
        raise HTTPException(
            status_code=404,
            detail=
            f"Team with alias {team.alias} not found in club {club_alias}")
    else:
      raise HTTPException(
          status_code=404,
          detail=
          f"Team with alias {team.alias} not or club {club_alias} not found")

  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))


# Update team in club
@router.patch("/{team_id}",
              response_description="Update team",
              response_model=TeamDB)
async def update_team(
    request: Request,
    team_id: str,
    club_alias: str = Path(..., description="Club alias to update team for"),
    team: TeamUpdate = Body(..., description="Team data"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
):
  mongodb = request.app.state.mongodb
  if token_payload.roles not in [["ADMIN"]]:
    raise HTTPException(status_code=403, detail="Not authorized")
  print("input team: ", team)
  team_data = team.dict(exclude_unset=True)
  print("exclude unset: ", team_data)

  # check if club exists
  club = await mongodb["clubs"].find_one({"alias": club_alias})
  if not club:
    raise HTTPException(status_code=404,
                        detail=f"Club with alias {club_alias} not found")

  # Find the index of the team to be updated
  team_index = next(
      (index
       for (index, d) in enumerate(club["teams"]) if d["_id"] == team_id),
      None)
  if team_index is None:
    raise HTTPException(
        status_code=404,
        detail=f"Team with id {team_id} not found in club {club_alias}")

  team_enc = jsonable_encoder(team_data)

  # prepare the update by excluding unchanged data
  update_data = {"$set": {}}
  for field in team_enc:
    if field != "_id" and team_enc[field] != club["teams"][team_index].get(
        field):
      update_data["$set"][f"teams.{team_index}.{field}"] = team_enc[field]
  print("updated data: ", update_data)

  # Update the team in the club
  if update_data["$set"]:
    print("do update")
    try:
      result = await mongodb["clubs"].update_one(
          {
              "_id": club["_id"],
              f"teams.{team_index}._id": team_id
          }, update_data)
      if result.modified_count == 0:
        raise HTTPException(
            status_code=404,
            detail=
            f"Update: Team with id {team_id} not found in club {club_alias}")

    except Exception as e:
      raise HTTPException(status_code=500, detail=str(e))

  else:
    print("do not update")
    return Response(status_code=status.HTTP_304_NOT_MODIFIED)

  # Get the updated team from the club
  club = await mongodb["clubs"].find_one({"alias": club_alias}, {
      "_id": 0,
      "teams": {
          "$elemMatch": {
              "_id": team_id
          }
      }
  })
  if club and "teams" in club:
    updated_team = club["teams"][0]
    team_response = TeamDB(**updated_team)
    return JSONResponse(status_code=status.HTTP_200_OK,
                        content=jsonable_encoder(team_response))
  else:
    raise HTTPException(
        status_code=404,
        detail=f"Fetch: Team with id {team_id} not found in club {club_alias}")


# Delete team
@router.delete("/{team_alias}", response_description="Delete team")
async def delete_team(
    request: Request,
    club_alias: str = Path(..., description="Club alias to delete team from"),
    team_alias: str = Path(..., description="Team alias to delete"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> Response:
  mongodb = request.app.state.mongodb    
  if token_payload.roles not in [["ADMIN"]]:
    raise HTTPException(status_code=403, detail="Not authorized")
  delete_result = await mongodb["clubs"].update_one(
      {"alias": club_alias}, {"$pull": {
          "teams": {
              "alias": team_alias
          }
      }})
  if delete_result.modified_count == 1:
    return Response(status_code=status.HTTP_204_NO_CONTENT)

  raise HTTPException(
      status_code=404,
      detail=f"Team with alias {team_alias} not found in club {club_alias}")
