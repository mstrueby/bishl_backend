
# Monkey-patch SecretStr for fastapi-mail compatibility with Pydantic v2
from pydantic import SecretStr
import sys
from types import ModuleType

# Create a fake pydantic module with SecretStr available at module level
# This fixes fastapi-mail's assumption that SecretStr is globally available
pydantic_types = ModuleType('pydantic.types')
pydantic_types.SecretStr = SecretStr
sys.modules['pydantic.types'] = pydantic_types

# Also add to main pydantic module
import pydantic
pydantic.SecretStr = SecretStr

# Now import fastapi-mail
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
import os

conf = ConnectionConfig(
    MAIL_USERNAME=os.environ["MAIL_USERNAME"],
    MAIL_PASSWORD=os.environ["MAIL_PASSWORD"],
    MAIL_FROM=os.environ["MAIL_FROM"],
    MAIL_FROM_NAME=os.environ.get("MAIL_FROM_NAME", "BISHL System"),
    MAIL_PORT=int(os.environ.get("MAIL_PORT", 587)),
    MAIL_SERVER=os.environ["MAIL_SERVER"],
    MAIL_STARTTLS=os.environ.get("MAIL_TLS", "True").lower() == "true",
    MAIL_SSL_TLS=os.environ.get("MAIL_SSL_TLS", "False").lower() == "true",
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True
)

fastmail = FastMail(conf)

async def send_email(subject: str, recipients: list, body: str, cc: list = None):
    message = MessageSchema(
        subject=subject,
        recipients=recipients,
        cc=cc or [],
        body=body,        
        subtype=MessageType.html
    )
    await fastmail.send_message(message)
