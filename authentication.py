import jwt
import os
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
      "exp": datetime.utcnow() + timedelta(days=0, minutes=int(os.environ['API_TIMEOUT_MIN'])),
      "iat": datetime.utcnow(),
      "sub": user["_id"],
      "roles": user["roles"],
      "firstname": user["firstname"],
      "lastname": user["lastname"],
      "club_id": user["club"]["club_id"] if user["club"] else None,
      "club_name": user["club"]["club_name"] if user["club"] else None
    }
    return jwt.encode(payload, self.secret, algorithm="HS256")

  def decode_token(self, token):
    try:
      payload = jwt.decode(token, self.secret, algorithms=["HS256"])
      return TokenPayload(
        sub=payload["sub"],
        roles=payload["roles"],
        firstname=payload.get("firstname"),
        lastname=payload.get("lastname"),
        club_id=payload.get("club_id"),
        club_name=payload.get("club_name")
      )
    except jwt.ExpiredSignatureError:
      raise HTTPException(status_code=401, detail="Signature has expired")
    except jwt.InvalidTokenError:
      raise HTTPException(status_code=401, detail="Invalid token")

  def auth_wrapper(self, auth: HTTPAuthorizationCredentials = Security(security)):
    return self.decode_token(auth.credentials)

class TokenPayload:
    def __init__(self, sub: str, roles: list, firstname: str = None, lastname: str = None, club_id: str = None, club_name: str = None):
        self.sub = sub
        self.roles = roles
        self.firstname = firstname
        self.lastname = lastname
        self.club_id = club_id
        self.club_name = club_name
        