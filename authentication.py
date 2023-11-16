import jwt
import os
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from datetime import datetime, timedelta


class AuthHandler:
  security = HTTPBearer()
  pwd_content = CryptContext(schemes=["bcrypt"], deprecated="auto")
  secret = "Sm9HZbZbNhwurU42ijTsLNJm"

  def get_password_hash(self, password):
    return self.pwd_content.hash(password)

  def verify_password(self, plain_password, hashed_password):
    return self.pwd_content.verify(plain_password, hashed_password)

  def encode_token(self, user_id):
    payLoad = {
      "exp": datetime.utcnow() + timedelta(days=0, minutes= int(os.environ['API_TIMEOUT_MIN'])),
      "iat": datetime.utcnow(),
      "sub": user_id,
    }
    return jwt.encode(payLoad, self.secret, algorithm="HS256")

  def decode_token(self, token):
    try:
      payLoad = jwt.decode(token, self.secret, algorithms=["HS256"])
      return payLoad["sub"]
    except jwt.ExpiredSignatureError:
      raise HTTPException(status_code=401, detail="Signature has expired")
    except jwt.InvalidTokenError:
      raise HTTPException(status_code=401, detail="Invalid token")

  def auth_wrapper(self,
                   auth: HTTPAuthorizationCredentials = Security(security)):
    return self.decode_token(auth.credentials)