from models.tournaments import MatchSettings


async def resolve_match_settings_batch(
    mongodb,
    matches: list[dict],
) -> list[dict]:
    t_aliases = set()
    for m in matches:
        t = m.get("tournament", {})
        s = m.get("season", {})
        if t and s and t.get("alias") and s.get("alias"):
            t_aliases.add(t["alias"])

    if not t_aliases:
        return matches

    tournaments = {}
    async for t in mongodb["tournaments"].find({"alias": {"$in": list(t_aliases)}}):
        tournaments[t["alias"]] = t

    for m in matches:
        if m.get("matchSettings"):
            m["matchSettingsSource"] = "match"
            continue

        t = m.get("tournament", {})
        s = m.get("season", {})
        r = m.get("round", {})
        md = m.get("matchday", {})

        t_alias = t.get("alias") if t else None
        s_alias = s.get("alias") if s else None
        r_alias = r.get("alias") if r else None
        md_alias = md.get("alias") if md else None

        if not t_alias or not s_alias or t_alias not in tournaments:
            continue

        tournament = tournaments[t_alias]
        season = next(
            (se for se in tournament.get("seasons", []) if se.get("alias") == s_alias),
            None,
        )
        if not season:
            continue

        resolved = None
        source = None

        if r_alias:
            round_data = next(
                (rd for rd in season.get("rounds", []) if rd.get("alias") == r_alias),
                None,
            )
            if round_data and md_alias:
                matchday = next(
                    (md_d for md_d in round_data.get("matchdays", []) if md_d.get("alias") == md_alias),
                    None,
                )
                if matchday and matchday.get("matchSettings"):
                    resolved = matchday["matchSettings"]
                    source = "matchday"

            if not resolved and round_data and round_data.get("matchSettings"):
                resolved = round_data["matchSettings"]
                source = "round"

        if not resolved and season.get("matchSettings"):
            resolved = season["matchSettings"]
            source = "season"

        if resolved:
            m["matchSettings"] = resolved
            m["matchSettingsSource"] = source

    return matches


async def resolve_match_settings(
    mongodb,
    tournament_alias: str | None,
    season_alias: str | None,
    round_alias: str | None,
    matchday_alias: str | None,
    match_settings: dict | None = None,
) -> tuple[MatchSettings | None, str | None]:
    if match_settings:
        return MatchSettings(**match_settings), "match"

    if not tournament_alias or not season_alias:
        return None, None

    tournament = await mongodb["tournaments"].find_one({"alias": tournament_alias})
    if not tournament:
        return None, None

    season = next(
        (s for s in tournament.get("seasons", []) if s.get("alias") == season_alias),
        None,
    )
    if not season:
        return None, None

    season_settings = season.get("matchSettings")

    if not round_alias:
        if season_settings:
            return MatchSettings(**season_settings), "season"
        return None, None

    round_data = next(
        (r for r in season.get("rounds", []) if r.get("alias") == round_alias),
        None,
    )

    if round_data and matchday_alias:
        matchday = next(
            (m for m in round_data.get("matchdays", []) if m.get("alias") == matchday_alias),
            None,
        )
        if matchday and matchday.get("matchSettings"):
            return MatchSettings(**matchday["matchSettings"]), "matchday"

    if round_data and round_data.get("matchSettings"):
        return MatchSettings(**round_data["matchSettings"]), "round"

    if season_settings:
        return MatchSettings(**season_settings), "season"

    return None, None
