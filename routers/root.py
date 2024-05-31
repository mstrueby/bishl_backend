from fastapi import APIRouter

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