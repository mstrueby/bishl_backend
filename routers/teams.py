# filename: routers/teams.py
import json
from typing import Any

import cloudinary
import cloudinary.uploader
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Path,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from pydantic import HttpUrl

from authentication import AuthHandler, TokenPayload
from exceptions import (
    DatabaseOperationException,
    ResourceNotFoundException,
)
from models.clubs import TeamBase, TeamDB, TeamPartnerships, TeamUpdate
from models.responses import PaginatedResponse, StandardResponse
from services.pagination import PaginationHelper
from utils import configure_cloudinary

router = APIRouter()
auth = AuthHandler()
configure_cloudinary()


# upload file
async def handle_logo_upload(logo: UploadFile, alias: str) -> str:
    if logo:
        result = cloudinary.uploader.upload(
            logo.file,
            folder="logos/teams",
            public_id=alias,
            overwrite=True,
            crop="scale",
            height=200,
        )
        print(f"Logo uploaded to Cloudinary: {result['public_id']}")
        return str(result["secure_url"])
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No logo uploaded.")


# Helper function to delete file from Cloudinary
async def delete_from_cloudinary(logo_url: str):
    if logo_url:
        try:
            public_id = logo_url.rsplit("/", 1)[-1].split(".")[0]
            result = cloudinary.uploader.destroy(f"logos/teams/{public_id}")
            print("Logo deleted from Cloudinary:", f"logos/teams/{public_id}")
            print("Result:", result)
            return result
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e


# list all teams of one club
@router.get(
    "", response_description="List all teams of one club", response_model=PaginatedResponse[TeamDB]
)
async def list_teams_of_one_club(
    request: Request,
    club_alias: str = Path(..., description="Club alias to list teams"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(100, ge=1, le=100, description="Items per page"),
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    if (club := await mongodb["clubs"].find_one({"alias": club_alias})) is not None:
        all_teams = club.get("teams") or []
        total_count = len(all_teams)

        # Calculate pagination manually for in-memory list
        page = max(1, page)  # Ensure page is at least 1
        page_size = max(1, min(page_size, 100))  # Ensure page_size is between 1 and 100
        skip = (page - 1) * page_size
        teams_page = all_teams[skip : skip + page_size]

        # Convert to TeamDB models
        teams = [TeamDB(**team) for team in teams_page]

        # Create paginated response
        paginated_result = PaginationHelper.create_response(
            items=teams,
            page=page,
            page_size=page_size,
            total_count=total_count,
            message=f"Retrieved {len(teams)} teams for club {club_alias}",
        )

        return JSONResponse(
            status_code=status.HTTP_200_OK, content=jsonable_encoder(paginated_result)
        )
    raise ResourceNotFoundException(
        resource_type="Club", resource_id=club_alias, details={"query_field": "alias"}
    )


# get one team of a club
@router.get(
    "/{team_alias}",
    response_description="Get one team of a club",
    response_model=StandardResponse[TeamDB],
)
async def get_team(
    request: Request,
    club_alias: str = Path(..., description="Club alias to get team"),
    team_alias: str = Path(..., description="Team alias to get"),
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    if (club := await mongodb["clubs"].find_one({"alias": club_alias})) is not None:
        for team in club.get("teams", []):
            if team.get("alias") == team_alias:
                # Use club logoUrl if team logoUrl is empty
                if not team.get("logoUrl") and club.get("logoUrl"):
                    team["logoUrl"] = club["logoUrl"]
                team_response = TeamDB(**team)
                standard_response = StandardResponse(
                    success=True,
                    data=team_response,
                    message=f"Team {team_alias} retrieved successfully",
                )
                return JSONResponse(
                    status_code=status.HTTP_200_OK, content=jsonable_encoder(standard_response)
                )
        raise ResourceNotFoundException(
            resource_type="Team", resource_id=team_alias, details={"club_alias": club_alias}
        )
    else:
        raise ResourceNotFoundException(
            resource_type="Club", resource_id=club_alias, details={"query_field": "alias"}
        )


# create new team
@router.post(
    "", response_description="Add new team to a club", response_model=StandardResponse[TeamDB]
)
async def create_team(
    request: Request,
    club_alias: str = Path(..., description="Club alias to create team for"),
    name: str = Form(...),
    alias: str = Form(...),
    shortName: str = Form(...),
    tinyName: str = Form(...),
    fullName: str = Form(...),
    ageGroup: str = Form(...),
    teamNumber: int = Form(...),
    teamPartnership: str = Form(None),
    active: bool = Form(False),
    external: bool = Form(False),
    ishdId: str | None = Form(None),
    legacyId: int | None = Form(None),
    logo: UploadFile = File(None),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    if "ADMIN" not in token_payload.roles:
        raise HTTPException(status_code=403, detail="Nicht authorisiert")

    # check if club exists
    if (club := await mongodb["clubs"].find_one({"alias": club_alias})) is None:
        raise ResourceNotFoundException(
            resource_type="Club", resource_id=club_alias, details={"query_field": "alias"}
        )

    # check if team already exists
    if any(t.get("alias") == alias for t in club.get("teams", [])):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Team with alias {alias} already exists for club {club_alias}",
        )

    try:
        team_partnership_dict = (
            json.loads(teamPartnership.strip())
            if teamPartnership and teamPartnership.strip()
            else None
        )
        if team_partnership_dict:
            if not isinstance(team_partnership_dict, list):
                team_partnership_dict = [team_partnership_dict]
            team_partnership_dict = [
                TeamPartnerships(**partnership) for partnership in team_partnership_dict
            ]
    except json.JSONDecodeError as e:
        raise DatabaseOperationException(
            operation="validate",
            collection="clubs.teams",
            message="Invalid JSON format for teamPartnership",
            details={"error": str(e), "field": "teamPartnership"},
        ) from e
    except Exception as e:
        raise DatabaseOperationException(
            operation="validate",
            collection="clubs.teams",
            message="Invalid teamPartnership format",
            details={"error": str(e), "field": "teamPartnership"},
        ) from e

    # create team object
    team = TeamBase(
        name=name,
        alias=alias,
        shortName=shortName,
        tinyName=tinyName,
        fullName=fullName,
        ageGroup=ageGroup,
        teamNumber=teamNumber,
        teamPartnership=team_partnership_dict or [],
        active=active,
        external=external,
        ishdId=ishdId,
        legacyId=legacyId,
    )

    # add team to club
    try:
        team_data = jsonable_encoder(team)
        if logo:
            team_data["logoUrl"] = await handle_logo_upload(logo, f"{club_alias}--{alias}")

        result = await mongodb["clubs"].update_one(
            {"alias": club_alias}, {"$push": {"teams": team_data}}
        )
        if result.modified_count == 1:
            # get inserted team
            updated_club = await mongodb["clubs"].find_one(
                {"alias": club_alias, "teams.alias": alias}, {"_id": 0, "teams.$": 1}
            )
            if updated_club and "teams" in updated_club:
                inserted_team = updated_club["teams"][0]
                team_response = TeamDB(**inserted_team)
                standard_response = StandardResponse(
                    success=True, data=team_response, message=f"Team {alias} created successfully"
                )
                return JSONResponse(
                    status_code=status.HTTP_201_CREATED, content=jsonable_encoder(standard_response)
                )
            else:
                raise ResourceNotFoundException(
                    resource_type="Team", resource_id=alias, details={"club_alias": club_alias}
                )
        else:
            raise ResourceNotFoundException(
                resource_type="Team", resource_id=alias, details={"club_alias": club_alias}
            )

    except Exception as e:
        raise DatabaseOperationException(
            operation="create",
            collection="clubs.teams",
            message=f"Failed to create team {alias} for club {club_alias}",
            details={"error": str(e)},
        ) from e


# Update team in club
@router.patch(
    "/{team_id}", response_description="Update team", response_model=StandardResponse[TeamDB]
)
async def update_team(
    request: Request,
    team_id: str,
    club_alias: str = Path(..., description="Club alias to update team for"),
    name: str | None = Form(None),
    alias: str | None = Form(None),
    shortName: str | None = Form(None),
    tinyName: str | None = Form(None),
    fullName: str | None = Form(None),
    ageGroup: str | None = Form(None),
    teamNumber: int | None = Form(None),
    teamPartnership: str | None = Form(None),
    active: bool | None = Form(None),
    external: bool | None = Form(None),
    ishdId: str | None = Form(None),
    legacyId: int | None = Form(None),
    logo: UploadFile | None = File(None),
    logoUrl: HttpUrl | None = Form(None),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
):
    mongodb = request.app.state.mongodb
    if "ADMIN" not in token_payload.roles:
        raise HTTPException(status_code=403, detail="Nicht authorisiert")

    # check if club exists
    club = await mongodb["clubs"].find_one({"alias": club_alias})
    if not club:
        raise ResourceNotFoundException(
            resource_type="Club", resource_id=club_alias, details={"query_field": "alias"}
        )

    # Find the index of the team to be updated
    team_index = next(
        (index for (index, d) in enumerate(club["teams"]) if d["_id"] == team_id), None
    )
    if team_index is None:
        raise ResourceNotFoundException(
            resource_type="Team", resource_id=team_id, details={"club_alias": club_alias}
        )

    try:
        team_partnership_dict = (
            json.loads(teamPartnership.strip())
            if teamPartnership and teamPartnership.strip()
            else None
        )
        if team_partnership_dict:
            if not isinstance(team_partnership_dict, list):
                team_partnership_dict = [team_partnership_dict]
            team_partnership_dict = [
                TeamPartnerships(**partnership) for partnership in team_partnership_dict
            ]
    except json.JSONDecodeError as e:
        raise DatabaseOperationException(
            operation="validate",
            collection="clubs.teams",
            message="Invalid JSON format for teamPartnership",
            details={"error": str(e), "field": "teamPartnership"},
        ) from e
    except Exception as e:
        raise DatabaseOperationException(
            operation="validate",
            collection="clubs.teams",
            message="Invalid teamPartnership format",
            details={"error": str(e), "field": "teamPartnership"},
        ) from e

    # Create team update object
    team_data = TeamUpdate(
        name=name,
        alias=alias,
        shortName=shortName,
        tinyName=tinyName,
        fullName=fullName,
        ageGroup=ageGroup,
        teamNumber=teamNumber,
        teamPartnership=team_partnership_dict,
        active=active,
        external=external,
        ishdId=ishdId,
        legacyId=legacyId,
    ).model_dump(exclude_none=True)
    team_data.pop("id", None)

    # handle image upload
    current_team_alias = club["teams"][team_index].get("alias")
    if logo:
        team_data["logoUrl"] = await handle_logo_upload(
            logo, f"{club['alias']}--{current_team_alias}"
        )
    elif logoUrl is not None:  # Explicitly check for None to allow empty string if needed
        team_data["logoUrl"] = str(logoUrl)
    # If logoUrl is provided and it's an empty string or None, we might want to clear the existing logo.
    # If logo is not provided and logoUrl is not provided, we keep the existing logoUrl.
    elif logoUrl is None and "logoUrl" in team_data:  # If logoUrl was explicitly set to None/empty
        # This case is tricky. If logoUrl is None, we might intend to remove the logo.
        # However, the original code only seemed to handle deletion if the club logo was being cleared.
        # For simplicity, if logo and logoUrl are not provided, we don't modify logoUrl unless it's in team_data.
        pass

    print("team_data: ", team_data)
    team_enc = jsonable_encoder(team_data)

    # prepare the update by excluding unchanged data
    update_data: dict[str, dict[str, Any]] = {"$set": {}}
    for field, value in team_enc.items():
        if field != "_id" and value != club["teams"][team_index].get(field):
            update_data["$set"][f"teams.{team_index}.{field}"] = value

    # Update the team in the club
    if update_data["$set"]:
        try:
            result = await mongodb["clubs"].update_one(
                {"_id": club["_id"], "teams._id": team_id},
                update_data,  # Use "teams._id" for matching the specific team
            )
            if result.modified_count == 0:
                # This case should ideally not happen if team_index was found, but as a safeguard.
                raise ResourceNotFoundException(
                    resource_type="Team", resource_id=team_id, details={"club_alias": club_alias}
                )

        except Exception as e:
            raise DatabaseOperationException(
                operation="update",
                collection="clubs.teams",
                message=f"Failed to update team {team_id} in club {club_alias}",
                details={"error": str(e)},
            ) from e

    # Get the team from the club to return (whether updated or not)
    updated_club = await mongodb["clubs"].find_one(
        {"alias": club_alias}, {"_id": 0, "teams": {"$elemMatch": {"_id": team_id}}}
    )
    if updated_club and "teams" in updated_club and updated_club["teams"]:
        team_response = TeamDB(**updated_club["teams"][0])
        message = (
            "No changes detected"
            if not update_data["$set"]
            else f"Team {team_id} updated successfully"
        )
        standard_response = StandardResponse(success=True, data=team_response, message=message)
        return JSONResponse(
            status_code=status.HTTP_200_OK, content=jsonable_encoder(standard_response)
        )
    else:
        # This case indicates an inconsistency if update succeeded but fetch failed.
        raise ResourceNotFoundException(
            resource_type="Team",
            resource_id=team_id,
            details={"club_alias": club_alias, "fetch_error": "Team not found after update"},
        )


# Delete team
@router.delete("/{team_id}", response_description="Delete team")
async def delete_team(
    request: Request,
    club_alias: str = Path(..., description="Club alias to delete team from"),
    team_id: str = Path(..., description="Team ID to delete"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> Response:
    mongodb = request.app.state.mongodb
    if "ADMIN" not in token_payload.roles:
        raise HTTPException(status_code=403, detail="Nicht authorisiert")

    # Check if club exists
    club = await mongodb["clubs"].find_one({"alias": club_alias})
    if not club:
        raise ResourceNotFoundException(
            resource_type="Club", resource_id=club_alias, details={"query_field": "alias"}
        )

    # Check if team exists within the club before attempting pull
    team_exists = any(team["_id"] == team_id for team in club.get("teams", []))
    if not team_exists:
        raise ResourceNotFoundException(
            resource_type="Team", resource_id=team_id, details={"club_alias": club_alias}
        )

    delete_result = await mongodb["clubs"].update_one(
        {"_id": club["_id"]}, {"$pull": {"teams": {"_id": team_id}}}  # Match by club ID for safety
    )

    if delete_result.modified_count == 1:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    else:
        # This case should ideally be caught by the team_exists check above,
        # but serves as a fallback if the team was removed between checks or if _id mismatch.
        raise ResourceNotFoundException(
            resource_type="Team",
            resource_id=team_id,
            details={"club_alias": club_alias, "delete_error": "Team not found or not removed"},
        )
