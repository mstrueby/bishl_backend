from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
from pydantic import SecretStr

from config import settings
from logging_config import logger

conf = ConnectionConfig(
    MAIL_USERNAME=settings.MAIL_USERNAME,
    MAIL_PASSWORD=SecretStr(settings.MAIL_PASSWORD),
    MAIL_FROM=settings.MAIL_FROM,
    MAIL_FROM_NAME=settings.MAIL_FROM_NAME,
    MAIL_PORT=settings.MAIL_PORT,
    MAIL_SERVER=settings.MAIL_SERVER,
    MAIL_STARTTLS=settings.MAIL_TLS,
    MAIL_SSL_TLS=settings.MAIL_SSL_TLS,
    USE_CREDENTIALS=settings.USE_CREDENTIALS,
    VALIDATE_CERTS=settings.VALIDATE_CERTS,
)

fastmail = FastMail(conf)


async def send_email(subject: str, recipients: list, body: str, cc: list | None = None, reply_to: list | None = None):
    """Send email"""
    # Force sending in development for testing if needed, or check environment
    logger.info(f"Sending email '{subject}' to {recipients}. Environment: {settings.ENVIRONMENT}")

    # Explicitly removed the production check to allow emails in dev if secrets are present
    message = MessageSchema(
        subject=subject,
        recipients=recipients,
        cc=cc or [],
        body=body,
        subtype=MessageType.html,
        reply_to=reply_to
    )
    await fastmail.send_message(message)
