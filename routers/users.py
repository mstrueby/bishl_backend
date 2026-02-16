# filename routers/users.py
import json
from datetime import date

from fastapi import APIRouter, Body, Depends, Form, HTTPException, Query, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from authentication import AuthHandler, TokenPayload
from config import settings
from exceptions import AuthorizationException, ResourceNotFoundException
from logging_config import logger
from mail_service import send_email
from models.assignments import AssignmentDB
from models.matches import MatchDB
from models.responses import PaginatedResponse, StandardResponse
from models.users import Club, CurrentUser, LoginBase, Role, UserBase, UserUpdate
from services.match_service import MatchService
from services.pagination import PaginationHelper

router = APIRouter()
auth = AuthHandler()
match_service = None  # Will be initialized with MongoDB instance


async def calculate_referee_points(mongodb, user_id):
    """
    Calculate referee points for a user based on matches in current season
    """
    current_season = settings.CURRENT_SEASON
    matches = (
        await mongodb["matches"]
        .find(
            {
                "season.alias": current_season,
                "$or": [
                    {"referee1.userId": user_id, "referee1.points": {"$exists": True}},
                    {"referee2.userId": user_id, "referee2.points": {"$exists": True}},
                ],
            }
        )
        .to_list(length=None)
    )

    total_points = 0
    for match in matches:
        if (
            match.get("referee1")
            and match["referee1"].get("userId") == user_id
            and match["referee1"].get("points")
        ):
            total_points += match["referee1"]["points"]
        if (
            match.get("referee2")
            and match["referee2"].get("userId") == user_id
            and match["referee2"].get("points")
        ):
            total_points += match["referee2"]["points"]

    return total_points


@router.post(
    "/register",
    response_description="Register a new user",
    response_model=StandardResponse[CurrentUser],
)
async def register(
    request: Request,
    newUser: UserBase = Body(...),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> JSONResponse:
    mongodb = request.app.state.mongodb

    # Check if logged-in user has ADMIN role
    if "ADMIN" not in token_payload.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to register a new user"
        )

    # Hash the password before inserting into the database
    newUser.password = auth.get_password_hash(newUser.password)

    # Check for existing user or email
    existing_user = await mongodb["users"].find_one({"email": newUser.email})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Email {newUser.email} is already registered",
        )
    # Insert the new user into the database
    newUser_data = jsonable_encoder(newUser)
    result = await mongodb["users"].insert_one(newUser_data)
    created_user = await request.app.state.mongodb["users"].find_one({"_id": result.inserted_id})

    token = auth.encode_token(created_user)
    response = StandardResponse(
        success=True, data=CurrentUser(**created_user), message="User registered successfully"
    )

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"token": token, **jsonable_encoder(response)},
    )


# login user
@router.post(
    "/login", response_description="Login a user", response_model=StandardResponse[CurrentUser]
)
async def login(request: Request, loginUser: LoginBase = Body(...)) -> JSONResponse:
    mongodb = request.app.state.mongodb
    existing_user = await mongodb["users"].find_one(
        {"email": {"$regex": f"^{loginUser.email}$", "$options": "i"}}
    )
    if (existing_user is None) or (
        not auth.verify_password(loginUser.password, existing_user["password"])
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email and/or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Auto-upgrade password from bcrypt to argon2 if needed
    if auth.needs_rehash(existing_user["password"]):
        new_hash = auth.get_password_hash(loginUser.password)
        await mongodb["users"].update_one(
            {"_id": existing_user["_id"]}, {"$set": {"password": new_hash}}
        )
        logger.info(
            f"Upgraded password hash for user {existing_user['email']} from bcrypt to argon2"
        )

    # Calculate referee points if user is a referee
    if "REFEREE" in existing_user.get("roles", []):
        total_points = await calculate_referee_points(mongodb, existing_user["_id"])

        # Update user's referee points
        if not existing_user.get("referee"):
            existing_user["referee"] = {"points": total_points}
        else:
            existing_user["referee"]["points"] = total_points

    # Generate access and refresh tokens
    access_token = auth.encode_token(existing_user)
    refresh_token = auth.encode_refresh_token(existing_user)

    response = StandardResponse(
        success=True, data=CurrentUser(**existing_user), message="Login successful"
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": 900,  # 15 minutes in seconds
            **jsonable_encoder(response),
        },
    )


# get current user
@router.get(
    "/me", response_description="Get current user", response_model=StandardResponse[CurrentUser]
)
async def me(
    request: Request, token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    user_id = token_payload.sub
    user = await mongodb["users"].find_one({"_id": user_id})

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Calculate referee points if user is a referee
    if "REFEREE" in user.get("roles", []):
        total_points = await calculate_referee_points(mongodb, user_id)

        # Update user's referee points
        if not user.get("referee"):
            user["referee"] = {"points": total_points}
        else:
            user["referee"]["points"] = total_points

    response = StandardResponse(
        success=True, data=CurrentUser(**user), message="User retrieved successfully"
    )
    return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(response))


# update user details
@router.patch(
    "/{user_id}", response_description="Update a user", response_model=StandardResponse[CurrentUser]
)
async def update_user(
    request: Request,
    user_id: str,
    email: str | None = Form(default=None),
    password: str | None = Form(default=None),
    firstName: str | None = Form(default=None),
    lastName: str | None = Form(default=None),
    club: str | None = Form(default=None),
    roles: list[str] | None = Form(default=None),
    referee: str | None = Form(default=None),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> JSONResponse:
    mongodb = request.app.state.mongodb

    # Check if user is trying to update their own profile or is an admin
    is_admin = any(role in ["ADMIN", "REF_ADMIN"] for role in token_payload.roles)
    is_self_update = user_id == token_payload.sub

    if not (is_admin or is_self_update):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this user"
        )

    existing_user_data = await mongodb["users"].find_one({"_id": user_id})
    existing_user_obj = CurrentUser(**existing_user_data) if existing_user_data else None
    existing_user = jsonable_encoder(existing_user_obj) if existing_user_obj else None
    if not existing_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Only allow role updates for admin users
    if roles and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can update roles"
        )

    try:
        user_data = UserUpdate(
            email=email,
            password=auth.get_password_hash(password) if password else None,
            firstName=firstName,
            lastName=lastName,
            club=Club(**json.loads(club)) if club else None,
            roles=[Role(role) for role in roles] if roles else None,
            referee=json.loads(referee) if referee else None,
        ).model_dump(
            exclude_none=True,
        )
        # user_data = UserUpdate(**user_update_fields).model_dump(exclude_none=True)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to parse input data: {e}",
        ) from e
    user_data.pop("id", None)
    logger.debug(f"user_data: {user_data}")

    user_to_update = {k: v for k, v in user_data.items() if v != existing_user.get(k, None)}
    if not user_to_update:
        logger.debug("No fields to update")
        response = StandardResponse(
            success=True, data=CurrentUser(**existing_user), message="No changes detected"
        )
        return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(response))
    try:
        logger.debug(f"update user: {user_to_update}")
        update_result = await mongodb["users"].update_one(
            {"_id": user_id}, {"$set": user_to_update}
        )

        if update_result.modified_count == 1:
            updated_user = await mongodb["users"].find_one({"_id": user_id})
            response = StandardResponse(
                success=True, data=CurrentUser(**updated_user), message="User updated successfully"
            )
            return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(response))

        # If not modified but no error, return current user
        response = StandardResponse(
            success=True, data=CurrentUser(**existing_user), message="No changes applied"
        )
        return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(response))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e


@router.get(
    "/matches",
    response_description="All assigned matches for me as a referee",
    response_model=StandardResponse[list[MatchDB]],
)
async def get_assigned_matches(
    request: Request, token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    global match_service
    if match_service is None:
        match_service = MatchService(mongodb)

    user_id = token_payload.sub
    user = await mongodb["users"].find_one({"_id": user_id})
    if not user:
        raise ResourceNotFoundException(resource_type="User", resource_id=user_id)
    if "REFEREE" not in user["roles"]:
        raise AuthorizationException(
            message="User is not a referee",
            details={"user_id": user_id, "user_roles": user.get("roles", [])},
        )

    # Fetch matches assigned to me as referee using MatchService
    from datetime import datetime

    current_date = datetime.combine(date.today(), datetime.min.time())
    matches = await match_service.get_matches_for_referee(user_id, current_date)

    # Parse matches into a list of MatchDB objects
    matches_list = [MatchDB(**match) for match in matches]
    response = StandardResponse(
        success=True, data=matches_list, message=f"Retrieved {len(matches_list)} assigned matches"
    )
    return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(response))


@router.get(
    "/assignments",
    response_description="All assignments by me",
    response_model=StandardResponse[list[AssignmentDB]],
)
async def get_assignments(
    request: Request, token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    global match_service
    if match_service is None:
        match_service = MatchService(mongodb)

    user_id = token_payload.sub
    user = await mongodb["users"].find_one({"_id": user_id})
    if not user:
        raise ResourceNotFoundException(resource_type="User", resource_id=user_id)
    if "REFEREE" not in user["roles"]:
        raise AuthorizationException(
            message="User is not a referee",
            details={"user_id": user_id, "user_roles": user.get("roles", [])},
        )

    # Fetch assignments assigned to me using MatchService
    assignments = await match_service.get_referee_assignments(user_id)

    # Parse assignments into a list of AssignmentDB objects
    assignments_list = [AssignmentDB(**assignment) for assignment in assignments]
    response = StandardResponse(
        success=True,
        data=assignments_list,
        message=f"Retrieved {len(assignments_list)} assignments",
    )
    return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(response))


@router.get(
    "/referees",
    response_description="Get all referees",
    response_model=PaginatedResponse[CurrentUser],
)
async def get_all_referees(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(100, ge=1, le=100, description="Items per page"),
    token_payload: TokenPayload = Depends(auth.auth_wrapper),
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    if not any(
        role in ["ADMIN", "REFEREE", "REF_ADMIN", "CLUB_ADMIN"] for role in token_payload.roles
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    # Use pagination helper
    items, total_count = await PaginationHelper.paginate_query(
        collection=mongodb["users"],
        query={"roles": "REFEREE"},
        page=page,
        page_size=page_size,
        sort=[("lastName", 1), ("firstName", 1)],
    )

    # Update referee points for each referee
    for referee in items:
        total_points = await calculate_referee_points(mongodb, referee["_id"])
        if not referee.get("referee"):
            referee["referee"] = {"points": total_points}
        else:
            referee["referee"]["points"] = total_points

    paginated_result = PaginationHelper.create_response(
        items=[CurrentUser(**referee) for referee in items],
        page=page,
        page_size=page_size,
        total_count=total_count,
        message=f"Retrieved {len(items)} referees",
    )

    return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(paginated_result))


# get one user
@router.get(
    "/{user_id}",
    response_description="Get a user by ID",
    response_model=StandardResponse[CurrentUser],
)
async def get_user(
    request: Request, user_id: str, token_payload: TokenPayload = Depends(auth.auth_wrapper)
) -> JSONResponse:
    mongodb = request.app.state.mongodb
    user = await mongodb["users"].find_one({"_id": user_id})
    if not user:
        raise ResourceNotFoundException(resource_type="User", resource_id=user_id)

    # Calculate referee points if user is a referee
    if "REFEREE" in user.get("roles", []):
        total_points = await calculate_referee_points(mongodb, user_id)

        # Update user's referee points
        if not user.get("referee"):
            user["referee"] = {"points": total_points}
        else:
            user["referee"]["points"] = total_points

    response = StandardResponse(
        success=True, data=CurrentUser(**user), message="User retrieved successfully"
    )
    return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(response))


@router.post("/forgot-password", response_description="Send password reset email")
async def forgot_password(request: Request, payload: dict = Body(...)) -> JSONResponse:
    mongodb = request.app.state.mongodb
    email = payload.get("email")

    if not email:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Email is required"
        )

    user = await mongodb["users"].find_one({"email": email})
    if not user:
        # Return success even if email not found to prevent email enumeration
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": "If email exists, reset link has been sent"},
        )

    # Generate reset token
    reset_token = auth.encode_reset_token(user)

    # Send password reset email (skip in test and development environments)
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"

    # Only send email in production environment
    if settings.ENVIRONMENT == "production":
        try:
            email_body = f"""
                <p>Hallo,</p>
                <p>Klicke auf den folgenden Link, um ein neues Passwort zu setzen::</p>
                <p><a href="{reset_url}">Neues Passwort erstellen</a></p>
                <p>Dieser Link ist eine Stunde gültig.</p>
                <p>Wenn Sie das Zurücksetzen des Passworts nicht beantragt haben, ignorieren Sie bitte diese E-Mail.</p>
            """
            await send_email(subject="Passwort zurücksetzen", recipients=[email], body=email_body)
        except Exception as e:
            logger.error(f"Error sending password reset email: {e}")
    else:
        logger.info(
            f"Non-production mode ({settings.ENVIRONMENT}): Skipping password reset email to {email}. Reset URL: {reset_url}"
        )
        logger.info(f"Reset token: {reset_token}")

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": "Password reset instructions sent to your email"},
    )


@router.post("/reset-password", response_description="Reset password with token")
async def reset_password(request: Request, payload: dict = Body(...)) -> JSONResponse:
    mongodb = request.app.state.mongodb
    try:
        # Verify token and get user_id
        token = payload.get("token")
        new_password = payload.get("password")

        if not token or not new_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token and new password must be provided",
            )

        token_data = auth.decode_reset_token(token)
        user_id = token_data.sub

        # Hash new password
        hashed_password = auth.get_password_hash(new_password)

        # Update password in database
        result = await mongodb["users"].update_one(
            {"_id": user_id}, {"$set": {"password": hashed_password}}
        )

        if result.modified_count == 1:
            return JSONResponse(
                status_code=status.HTTP_200_OK, content={"message": "Password updated successfully"}
            )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Password update failed"
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token"
        ) from e


@router.post("/refresh", response_description="Refresh access token")
async def refresh_token(request: Request, payload: dict = Body(...)) -> JSONResponse:
    """
    Refresh access token using a valid refresh token.
    Returns new access and refresh tokens.
    """
    mongodb = request.app.state.mongodb
    refresh_token = payload.get("refresh_token")

    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Refresh token is required"
        )

    # Decode refresh token and get user ID
    user_id = auth.decode_refresh_token(refresh_token)

    # Fetch user from database
    user = await mongodb["users"].find_one({"_id": user_id})
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Calculate referee points if user is a referee
    if "REFEREE" in user.get("roles", []):
        total_points = await calculate_referee_points(mongodb, user_id)
        if not user.get("referee"):
            user["referee"] = {"points": total_points}
        else:
            user["referee"]["points"] = total_points

    # Generate new access and refresh tokens
    new_access_token = auth.encode_token(user)
    new_refresh_token = auth.encode_refresh_token(user)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
            "expires_in": 900,  # 15 minutes in seconds
        },
    )
