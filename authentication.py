import jwt
import os
from typing import Optional
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from datetime import datetime, timedelta


class AuthHandler:
  security = HTTPBearer()
  pwd_content = CryptContext(schemes=["bcrypt"], deprecated="auto")
  secret = os.environ.get("SECRET_KEY")

  def get_password_hash(self, password):
    return self.pwd_content.hash(password)

  def verify_password(self, plain_password, hashed_password):
    return self.pwd_content.verify(plain_password, hashed_password)

  def encode_token(self, user):
    payload = {
        "exp":
        datetime.now() +
        timedelta(days=0, minutes=int(os.environ['API_TIMEOUT_MIN'])),
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
      raise HTTPException(status_code=401, detail="Signature has expired")
    except jwt.InvalidTokenError:
      raise HTTPException(status_code=401, detail="Invalid token")

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
