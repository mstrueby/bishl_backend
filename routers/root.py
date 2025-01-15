from fastapi import APIRouter
from utils.email import send_email

router = APIRouter()
endpoints = [
    {
        "name": "Tournaments",
        "url": "/tournaments"
    },
    {
        "name": "Venues",
        "url": "/venues"
    },
    {
        "name": "Clubs",
        "url": "/clubs"
    }
]

@router.get("/", response_description="List all entry API endpoints")
async def get_root():
    return endpoints

@router.get("/test-email")
async def test_email():
    await send_email(
        subject="Test Email",
        recipients=["marian.strueby@web.de"],
        body="<h1>Test Email</h1><p>This is a test email from FastAPI</p>"
    )
    return {"message": "Test email sent"}
