# filename: routers/configs.py
from fastapi import APIRouter, Request, status, HTTPException, Path
from fastapi.responses import JSONResponse
from models.configs import ConfigBase, ConfigDB, ConfigUpdate
from authentication import AuthHandler

router = APIRouter()
auth = AuthHandler()

# Config document
config = [{
  "key":
  "AGEGROUP",
  "name":
  "Altersklasse",
  "value": [
    {
      "key": "MEN",
      "value": "Herren",
      "sortOrder": 1
    },
    {
      "key": "WOMEN",
      "value": "Damen",
      "sortOrder": 2
    },
    {
      "key": "U19",
      "value": "U19",
      "sortOrder": 3
    },
    {
      "key": "U16",
      "value": "U16",
      "sortOrder": 4
    },
    {
      "key": "U13",
      "value": "U13",
      "sortOrder": 5
    },
    {
      "key": "U10",
      "value": "U10",
      "sortOrder": 6
    },
    {
      "key": "U8",
      "value": "U8",
      "sortOrder": 7
    },
  ]
}, {
  "key":
  "MATCHDAYSTYPE",
  "name":
  "Matchdays Type",
  "value": [
    {
      "key": "MATCHDAY",
      "value": "Spieltag",
      "sortOrder": 1
    },
    {
      "key": "TOURNAMENT",
      "value": "Turnier",
      "sortOrder": 2
    },
    {
      "key": "ROUND",
      "value": "Runde",
      "sortOrder": 3
    },
    {
      "key": "GROUP",
      "value": "Gruppe",
      "sortOrder": 4
    },
  ]
}, {
  "key":
  "MATCHDAYSSORTEDBY",
  "name":
  "Spieltagsortierung",
  "value": [
    {
      "key": "NAME",
      "value": "Name",
      "sortOrder": 1
    },
    {
      "key": "STARTDATE",
      "value": "Startdatum",
      "sortOrder": 2
    },
  ]
}]


# get all configs
@router.get("/", response_description="Get all configs")
async def get_all_configs(request: Request):
  return JSONResponse(status_code=status.HTTP_200_OK, content=config)


# get one config
@router.get("/{key}", response_description="Get one config")
async def get_one_config(request: Request, key: str = Path(...)):
    for config_doc in config:
        if config_doc["key"].lower() == key.lower():
            return JSONResponse(status_code=status.HTTP_200_OK, content=config_doc)
    raise HTTPException(status_code=404, detail=f"Config with key {key} not found")