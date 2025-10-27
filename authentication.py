import jwt
from typing import Optional
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHash
from datetime import datetime, timedelta
from exceptions import AuthenticationException
from config import settings


class AuthHandler:
  security = HTTPBearer()
  # Keep bcrypt for legacy password verification
  pwd_content_legacy = CryptContext(schemes=["bcrypt"], deprecated="auto")
  # New argon2 hasher
  argon2_hasher = PasswordHasher()
  secret = settings.SECRET_KEY

  def get_password_hash(self, password):
    """Hash password using argon2 (new standard)"""
    return self.argon2_hasher.hash(password)

  def verify_password(self, plain_password, hashed_password):
    """Verify password - supports both argon2 and legacy bcrypt"""
    # Try argon2 first (new format starts with $argon2)
    if hashed_password.startswith('$argon2'):
      try:
        return self.argon2_hasher.verify(hashed_password, plain_password)
      except (VerifyMismatchError, InvalidHash):
        return False
    
    # Fallback to bcrypt (legacy passwords)
    try:
      return self.pwd_content_legacy.verify(plain_password, hashed_password)
    except:
      return False
  
  def needs_rehash(self, hashed_password):
    """Check if password needs to be upgraded from bcrypt to argon2"""
    return not hashed_password.startswith('$argon2')

  def encode_token(self, user):
    payload = {
        "exp":
        datetime.now() +
        timedelta(days=0, minutes=settings.API_TIMEOUT_MIN),
        "iat":
        datetime.now(),
        "sub":
        user["_id"],
        "roles":
        user["roles"],
        "firstName":
        user["firstName"],
        "lastName":
        user["lastName"],
        "clubId":
        user["club"]["clubId"] if user["club"] else None,
        "clubName":
        user["club"]["clubName"] if user["club"] else None
    }
    return jwt.encode(payload, self.secret, algorithm="HS256")

  def decode_token(self, token):
    try:
      payload = jwt.decode(token, self.secret, algorithms=["HS256"])
      return TokenPayload(sub=payload["sub"],
        roles=payload["roles"],
        firstName=payload.get("firstName"),
        lastName=payload.get("lastName"),
        clubId=payload.get("clubId"),
        clubName=payload.get("clubName"))
    except jwt.ExpiredSignatureError:
      raise AuthenticationException(
        message="Token has expired",
        details={"reason": "expired_signature"}
      )
    except jwt.InvalidTokenError:
      raise AuthenticationException(
        message="Invalid token",
        details={"reason": "invalid_token"}
      )
  
  def encode_reset_token(self, user):
    payload = {
        "exp": datetime.now() + timedelta(hours=1),  # Token expires in 1 hour
        "iat": datetime.now(),
        "sub": user["_id"],
        "type": "reset"
    }
    return jwt.encode(payload, self.secret, algorithm="HS256")

  def decode_reset_token(self, token):
    try:
      payload = jwt.decode(token, self.secret, algorithms=["HS256"])
      if payload.get("type") != "reset":
          raise jwt.InvalidTokenError
      return TokenPayload(sub=payload["sub"], roles=[])
    except jwt.ExpiredSignatureError:
      raise AuthenticationException(
        message="Reset token has expired",
        details={"reason": "expired_reset_token"}
      )
    except jwt.InvalidTokenError:
      raise AuthenticationException(
        message="Invalid reset token",
        details={"reason": "invalid_reset_token"}
      )


  def auth_wrapper(self,
                   auth: HTTPAuthorizationCredentials = Security(security)):
    return self.decode_token(auth.credentials)


class TokenPayload:

  def __init__(self,
               sub: str,
               roles: list,
               firstName: Optional[str] = None,
               lastName: Optional[str] = None,
               clubId: Optional[str] = None,
               clubName: Optional[str] = None):
    self.sub = sub
    self.roles = roles
    self.firstName = firstName
    self.lastName = lastName
    self.clubId = clubId
    self.clubName = clubName
