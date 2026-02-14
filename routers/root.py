from fastapi import APIRouter

from config import settings
from mail_service import send_email

router = APIRouter()
endpoints = [
    {"name": "Tournaments", "url": "/tournaments"},
    {"name": "Venues", "url": "/venues"},
    {"name": "Clubs", "url": "/clubs"},
]


@router.get("/", response_description="List all entry API endpoints")
async def get_root():
    return endpoints


@router.get("/test-email", include_in_schema=False)
async def test_email():
    await send_email(
        subject="Test Email",
        recipients=[settings.MAIL_TEST_RECEIPIENT],
        body="<h1>Test Email</h1><p>This is a test email from FastAPI</p>",
    )
    return {"message": "Test email sent"}


@router.get("/cronjob_81243.html", include_in_schema=False)
async def get_cronjob():
    from fastapi.responses import FileResponse

    return FileResponse("cronjob_81243.html")
