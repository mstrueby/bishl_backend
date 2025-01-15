
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
import os

conf = ConnectionConfig(
    MAIL_USERNAME=os.environ["MAIL_USERNAME"],
    MAIL_PASSWORD=os.environ["MAIL_PASSWORD"],
    MAIL_FROM=os.environ["MAIL_FROM"],
    MAIL_FROM_NAME=os.environ.get("MAIL_FROM_NAME", "Refbox System"),
    MAIL_PORT=int(os.environ.get("MAIL_PORT", 587)),
    MAIL_SERVER=os.environ["MAIL_SERVER"],
    MAIL_STARTTLS=os.environ.get("MAIL_TLS", "True").lower() == "true",
    MAIL_SSL_TLS=os.environ.get("MAIL_SSL_TLS", "True").lower() == "true",
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True
)
print("conf", conf)

fastmail = FastMail(conf)

async def send_email(subject: str, recipients: list, body: str):
    message = MessageSchema(
        subject=subject,
        recipients=recipients,
        body=body,        
        subtype=MessageType.html
    )
    await fastmail.send_message(message)
