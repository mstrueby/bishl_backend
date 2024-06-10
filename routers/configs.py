# routers/configs.py
from fastapi import APIRouter, Request, status, HTTPException, Path
from fastapi.responses import JSONResponse
from models.configs import Config, ConfigValue
from authentication import AuthHandler
from typing import List

router = APIRouter()
auth = AuthHandler()

# Config document
configs: List[Config] = [  # Use List[Config] for type hinting
  Config(key="COUNTRY",
         name="Land",
         value=[
           ConfigValue(key="DE", value="Deutschland", sortOrder=1),
           ConfigValue(key="CH", value="Schweiz", sortOrder=2),
           ConfigValue(key="AT", value="Österreich", sortOrder=3),
           ConfigValue(key="DK", value="Dänemark", sortOrder=4),
         ]),
  Config(key="AGEGROUP",
         name="Altersklasse",
         value=[
           ConfigValue(key="MEN", value="Herren", sortOrder=1),
           ConfigValue(key="WOMEN", value="Damen", sortOrder=2),
           ConfigValue(key="U19", value="U19", sortOrder=3),
           ConfigValue(key="U16", value="U16", sortOrder=4),
           ConfigValue(key="U13", value="U13", sortOrder=5),
           ConfigValue(key="U10", value="U10", sortOrder=6),
           ConfigValue(key="U8", value="U8", sortOrder=7)
         ]),
  Config(key="MATCHDAYSTYPE",
         name="Matchdays Type",
         value=[
           ConfigValue(key="MATCHDAY", value="Spieltag", sortOrder=1),
           ConfigValue(key="TOURNAMENT", value="Turnier", sortOrder=2),
           ConfigValue(key="ROUND", value="Runde", sortOrder=3),
           ConfigValue(key="GROUP", value="Gruppe", sortOrder=4)
         ]),
  Config(key="MATCHDAYSSORTEDBY",
         name="Spieltagsortierung",
         value=[
           ConfigValue(key="NAME", value="Name", sortOrder=1),
           ConfigValue(key="STARTDATE", value="Startdatum", sortOrder=2)
         ])
]


# Get all configs
@router.get("/",
            response_model=List[Config],
            response_description="Get all configs")
async def get_all_configs(request: Request):
  return JSONResponse(status_code=status.HTTP_200_OK,
                      content=[config.dict() for config in configs])


# Get one config
@router.get("/{key}",
            response_model=Config,
            response_description="Get one config")
async def get_one_config(request: Request, key: str = Path(...)):
  lower_key = key.lower()
  for config in configs:
    if config.key.lower() == lower_key:
      return JSONResponse(status_code=status.HTTP_200_OK,
                          content=config.dict())
  raise HTTPException(status_code=404,
                      detail=f"Config with key {key} not found")
