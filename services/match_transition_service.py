from fastapi import HTTPException, status

STATUS_LABELS: dict[str, str] = {
    "SCHEDULED": "angesetzt",
    "INPROGRESS": "Live",
    "FINISHED": "beendet",
    "CANCELLED": "abgesagt",
    "FORFEITED": "gewertet",
}

ALL_STATUSES: list[str] = list(STATUS_LABELS.keys())

_ROLE_TRANSITIONS: dict[str, dict[str, list[str]]] = {
    "LEAGUE_ADMIN": {
        "SCHEDULED": ["INPROGRESS", "CANCELLED", "FORFEITED"],
        "INPROGRESS": ["FINISHED"],
        "FINISHED": ["FORFEITED"],
        "FORFEITED": ["FINISHED"],
        "CANCELLED": [],
    },
    "CLUB_ADMIN": {
        "SCHEDULED": ["INPROGRESS"],
        "INPROGRESS": ["FINISHED"],
        "FINISHED": [],
        "FORFEITED": [],
        "CANCELLED": [],
    },
}


def get_allowed_transitions(current_status: str, user_roles: list[str]) -> list[str]:
    """
    Return the list of target statuses the user may transition to from current_status.
    ADMIN is unrestricted (all statuses except the current one).
    Returns an empty list when no transition is permitted.
    """
    if "ADMIN" in user_roles:
        return [s for s in ALL_STATUSES if s != current_status]

    if "LEAGUE_ADMIN" in user_roles:
        return _ROLE_TRANSITIONS["LEAGUE_ADMIN"].get(current_status, [])

    if "CLUB_ADMIN" in user_roles:
        return _ROLE_TRANSITIONS["CLUB_ADMIN"].get(current_status, [])

    return []


def validate_match_transition(
    current_status: str, new_status: str, user_roles: list[str]
) -> None:
    """
    Validate that the transition from current_status → new_status is permitted
    for the given roles.  No-op when current == new.

    Raises:
        HTTPException 400 — if the transition is not defined for any role.
        HTTPException 403 — if the transition exists but the user's role does not permit it.
    """
    if current_status == new_status:
        return

    if "ADMIN" in user_roles:
        return

    user_allowed = get_allowed_transitions(current_status, user_roles)
    if new_status in user_allowed:
        return

    any_role_allowed: set[str] = set()
    for role_map in _ROLE_TRANSITIONS.values():
        any_role_allowed.update(role_map.get(current_status, []))

    if new_status not in any_role_allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status transition: {current_status} → {new_status}",
        )

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Your role does not permit the transition: {current_status} → {new_status}",
    )
