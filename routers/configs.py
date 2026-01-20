# routers/configs.py

from fastapi import APIRouter, Path, Request, status
from fastapi.responses import JSONResponse

from authentication import AuthHandler
from exceptions import ResourceNotFoundException
from logging_config import logger
from models.configs import Config, ConfigValue

router = APIRouter()
auth = AuthHandler()

# Config document
configs: list[Config] = [  # Use List[Config] for type hinting
    Config(
        key="PLAYER_ASSIGNMENT_WINDOW",
        name="Zeitfenster für Spielerzuweisungen",
        value=[
            ConfigValue(key="ENABLED", value=True, sortOrder=1),
            ConfigValue(key="START_MONTH", value=1, sortOrder=2),
            ConfigValue(key="START_DAY", value=1, sortOrder=3),
            ConfigValue(key="END_MONTH", value=3, sortOrder=4),
            ConfigValue(key="END_DAY", value=1, sortOrder=5),
        ],
    ),
    Config(
        key="COUNTRY",
        name="Land",
        value=[
            ConfigValue(key="DE", value="Deutschland", sortOrder=1),
            ConfigValue(key="CH", value="Schweiz", sortOrder=2),
            ConfigValue(key="AT", value="Österreich", sortOrder=3),
            ConfigValue(key="DK", value="Dänemark", sortOrder=4),
        ],
    ),
    Config(
        key="AGEGROUP",
        name="Altersklasse",
        value=[
            ConfigValue(key="MEN", value="Herren", sortOrder=1),
            ConfigValue(key="WOMEN", value="Damen", sortOrder=2),
            ConfigValue(key="U19", value="U19", sortOrder=3),
            ConfigValue(key="U16", value="U16", sortOrder=4),
            ConfigValue(key="U13", value="U13", sortOrder=5),
            ConfigValue(key="U10", value="U10", sortOrder=6),
            ConfigValue(key="U8", value="U8", sortOrder=7),
        ],
    ),
    Config(
        key="MATCHDAYSTYPE",
        name="Spieltagtyp",
        value=[
            ConfigValue(key="MATCHDAY", value="Spieltag", sortOrder=1),
            ConfigValue(key="TOURNAMENT", value="Turnier", sortOrder=2),
            ConfigValue(key="ROUND", value="Runde", sortOrder=3),
            ConfigValue(key="GROUP", value="Gruppe", sortOrder=4),
        ],
    ),
    Config(
        key="MATCHDAYSSORTEDBY",
        name="Spieltagsortierung",
        value=[
            ConfigValue(key="NAME", value="Name", sortOrder=1),
            ConfigValue(key="STARTDATE", value="Startdatum", sortOrder=2),
        ],
    ),
    Config(
        key="MATCHDAYTYPE",
        name="Spieltagstyp",
        value=[
            ConfigValue(key="PLAYOFFS", value="Playoffs", sortOrder=1),
            ConfigValue(key="REGULAR", value="Regulär", sortOrder=2),
        ],
    ),
    Config(
        key="MATCHSTATUS",
        name="Spielstatus",
        value=[
            ConfigValue(key="SCHEDULED", value="Angesetzt", sortOrder=1),
            ConfigValue(key="INPROGRESS", value="Live", sortOrder=2),
            ConfigValue(key="FINISHED", value="Beendet", sortOrder=3),
            ConfigValue(key="CANCELLED", value="Abgesagt", sortOrder=4),
            ConfigValue(key="FORFEITED", value="Gewertet", sortOrder=5),
        ],
    ),
    Config(
        key="PENALTYCODE",
        name="Penalty Code",
        value=[
            ConfigValue(key="A", value="Behinderung", sortOrder=1),
            ConfigValue(key="B", value="Unerlaubter Körperangriff", sortOrder=2),
            ConfigValue(key="C", value="Übertriebene Härte", sortOrder=3),
            ConfigValue(key="D", value="Cross-Check", sortOrder=4),
            ConfigValue(key="E", value="Halten", sortOrder=5),
            ConfigValue(key="F", value="Stockstich", sortOrder=6),
            ConfigValue(key="G", value="Stockschlag", sortOrder=7),
            ConfigValue(key="H", value="Beinstellen", sortOrder=8),
            ConfigValue(key="I", value="Haken", sortOrder=9),
            ConfigValue(key="J", value="Hoher Stock", sortOrder=10),
            ConfigValue(key="K", value="Ellbogencheck", sortOrder=11),
            ConfigValue(key="L", value="Check von Hinten", sortOrder=12),
            ConfigValue(key="M", value="Bandencheck", sortOrder=13),
            ConfigValue(key="N", value="Stockendstoß", sortOrder=14),
            ConfigValue(key="O", value="Kniecheck", sortOrder=15),
            ConfigValue(key="P", value="Kopfstoß", sortOrder=16),
            ConfigValue(key="Q", value="Check gegen Kopf- und Nackenbereich", sortOrder=17),
            ConfigValue(key="R", value="Fußtritt", sortOrder=18),
            ConfigValue(key="W", value="Wechselfehler", sortOrder=19),
            ConfigValue(key="X", value="Spielverzögerung", sortOrder=20),
            ConfigValue(key="Y", value="Vergehen von Torhütern", sortOrder=21),
            ConfigValue(key="ZA", value="Bankstrafe, Fehlverhalten", sortOrder=23),
            ConfigValue(key="ZB", value="Vergehen auf der Strafbank", sortOrder=24),
            ConfigValue(key="ZC", value="Vergehen im Zusammenhang mit Ausrüstung", sortOrder=25),
        ],
    ),
    Config(
        key="PLAYERPOSITION",
        name="Spielerposition",
        value=[
            ConfigValue(key="C", value="Captain", sortOrder=1),
            ConfigValue(key="A", value="Assistant", sortOrder=2),
            ConfigValue(key="G", value="Goalie", sortOrder=3),
            ConfigValue(key="F", value="Feldspieler", sortOrder=4),
        ],
    ),
    Config(
        key="FINISHTYPE",
        name="Abschluss",
        value=[
            ConfigValue(key="REGULAR", value="Regulär", sortOrder=1),
            ConfigValue(key="OVERTIME", value="Verlängerung", sortOrder=2),
            ConfigValue(key="SHOOTOUT", value="Penaltyschießen", sortOrder=3),
        ],
    ),
]


# Get all configs
@router.get("", response_model=list[Config], response_description="Get all configs")
async def get_all_configs(request: Request):
    return JSONResponse(
        status_code=status.HTTP_200_OK, content=[config.model_dump() for config in configs]
    )


# Get one config
@router.get("/{key}", response_model=Config, response_description="Get one config")
async def get_one_config(request: Request, key: str = Path(...)):
    lower_key = key.lower()
    for config in configs:
        if config.key.lower() == lower_key:
            logger.debug(f"Config retrieved: {key}")
            return JSONResponse(status_code=status.HTTP_200_OK, content=config.model_dump())
    raise ResourceNotFoundException(
        resource_type="Config", resource_id=key, details={"searched_key": lower_key}
    )
