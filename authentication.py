from datetime import datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerifyMismatchError
from fastapi import Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext

from config import settings
from exceptions import AuthenticationException


class AuthHandler:
    security = HTTPBearer()
    # Keep bcrypt for legacy password verification
    pwd_content_legacy = CryptContext(schemes=["bcrypt"], deprecated="auto")
    # New argon2 hasher
    argon2_hasher = PasswordHasher()
    secret = settings.SECRET_KEY
    refresh_secret = settings.SECRET_KEY + "_refresh"  # Separate secret for refresh tokens

    def get_password_hash(self, password):
        """Hash password using argon2 (new standard)"""
        return self.argon2_hasher.hash(password)

    def verify_password(self, plain_password, hashed_password):
        """Verify password - supports both argon2 and legacy bcrypt"""
        # Try argon2 first (new format starts with $argon2)
        if hashed_password.startswith("$argon2"):
            try:
                return self.argon2_hasher.verify(hashed_password, plain_password)
            except (VerifyMismatchError, InvalidHash):
                return False

        # Fallback to bcrypt (legacy passwords)
        try:
            return self.pwd_content_legacy.verify(plain_password, hashed_password)
        except Exception:
            return False

    def needs_rehash(self, hashed_password):
        """Check if password needs to be upgraded from bcrypt to argon2"""
        return not hashed_password.startswith("$argon2")

    def encode_token(self, user):
        """Generate short-lived access token (15 minutes)"""
        payload = {
            "exp": datetime.now() + timedelta(minutes=15),  # Short-lived access token
            "iat": datetime.now(),
            "sub": user["_id"],
            "roles": user["roles"],
            "firstName": user["firstName"],
            "lastName": user["lastName"],
            "clubId": user["club"]["clubId"] if user["club"] else None,
            "clubName": user["club"]["clubName"] if user["club"] else None,
            "type": "access",
        }
        return jwt.encode(payload, self.secret, algorithm="HS256")

    def encode_refresh_token(self, user):
        """Generate long-lived refresh token (7 days)"""
        payload = {
            "exp": datetime.now() + timedelta(days=7),  # Long-lived refresh token
            "iat": datetime.now(),
            "sub": user["_id"],
            "type": "refresh",
        }
        return jwt.encode(payload, self.refresh_secret, algorithm="HS256")

    def decode_token(self, token):
        """Decode and validate access token"""
        try:
            payload = jwt.decode(token, self.secret, algorithms=["HS256"])
            if payload.get("type") != "access":
                raise jwt.InvalidTokenError("Not an access token")
            return TokenPayload(
                sub=payload["sub"],
                roles=payload["roles"],
                firstName=payload.get("firstName"),
                lastName=payload.get("lastName"),
                clubId=payload.get("clubId"),
                clubName=payload.get("clubName"),
            )
        except jwt.ExpiredSignatureError as e:
            raise AuthenticationException(
                message="Token has expired", details={"reason": "expired_signature"}
            ) from e
        except jwt.InvalidTokenError as e:
            raise AuthenticationException(
                message="Invalid token", details={"reason": "invalid_token"}
            ) from e

    def decode_refresh_token(self, token):
        """Decode and validate refresh token"""
        try:
            payload = jwt.decode(token, self.refresh_secret, algorithms=["HS256"])
            if payload.get("type") != "refresh":
                raise jwt.InvalidTokenError("Not a refresh token")
            return payload["sub"]  # Return only user ID
        except jwt.ExpiredSignatureError as e:
            raise AuthenticationException(
                message="Refresh token has expired", details={"reason": "expired_refresh_token"}
            ) from e
        except jwt.InvalidTokenError as e:
            raise AuthenticationException(
                message="Invalid refresh token", details={"reason": "invalid_refresh_token"}
            ) from e

    def encode_reset_token(self, user):
        payload = {
            "exp": datetime.now() + timedelta(hours=1),  # Token expires in 1 hour
            "iat": datetime.now(),
            "sub": user["_id"],
            "type": "reset",
        }
        return jwt.encode(payload, self.secret, algorithm="HS256")

    def decode_reset_token(self, token):
        try:
            payload = jwt.decode(token, self.secret, algorithms=["HS256"])
            if payload.get("type") != "reset":
                raise jwt.InvalidTokenError
            return TokenPayload(sub=payload["sub"], roles=[])
        except jwt.ExpiredSignatureError as e:
            raise AuthenticationException(
                message="Reset token has expired", details={"reason": "expired_reset_token"}
            ) from e
        except jwt.InvalidTokenError as e:
            raise AuthenticationException(
                message="Invalid reset token", details={"reason": "invalid_reset_token"}
            ) from e

    def auth_wrapper(self, auth: HTTPAuthorizationCredentials = Security(security)):
        return self.decode_token(auth.credentials)


class TokenPayload:

    def __init__(
        self,
        sub: str,
        roles: list,
        firstName: str | None = None,
        lastName: str | None = None,
        clubId: str | None = None,
        clubName: str | None = None,
    ):
        self.sub = sub
        self.roles = roles
        self.firstName = firstName
        self.lastName = lastName
        self.clubId = clubId
        self.clubName = clubName
