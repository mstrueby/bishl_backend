
# Match & Roster Permission Gates

*Created: 2026-04-14*  
*Status: Implemented*  
*Scope: Backend enforcement + Frontend display guidance*

---

## Overview

Every write operation on a match or its associated resources (roster, scores, penalties, supplementary sheet) is guarded by a named permission gate evaluated server-side in `MatchPermissionService`. The frontend **may** use the same logic to show or hide UI controls, but the backend is the authoritative enforcement layer.

Permissions are **deny by default**. A user must satisfy at least one explicit grant rule for a gate to open.

---

## Roles

| Role | Description |
|------|-------------|
| `ADMIN` | Full system administrator |
| `LEAGUE_ADMIN` | League-level administrator — treated identically to `ADMIN` for all match permissions |
| `CLUB_ADMIN` | Club-scoped administrator; carries a `clubId` claim in their JWT |

Any other role (e.g. `REFEREE`, `PLAYER_ADMIN`) receives no match-write access.

---

## Match Attributes Used

| Attribute | Source |
|-----------|--------|
| `startDate` | `matches.startDate` (UTC datetime) |
| `matchStatus.key` | `matches.matchStatus.key` — one of `SCHEDULED`, `INPROGRESS`, or a finished state |
| `season.alias` | `matches.season.alias` |
| `home.clubId` | `matches.home.clubId` |
| `away.clubId` | `matches.away.clubId` |
| `matchday.owner.clubId` | Retrieved from `tournaments → seasons → rounds → matchdays[alias].owner.clubId` |

---

## Derived Boolean Flags

These flags are computed fresh on every request from the match document and the current server timestamp. The frontend should compute equivalent flags locally for display purposes.

| Flag | Definition |
|------|------------|
| `isMatchDay` | `match.startDate` (date only) == today |
| `isMatchInPast` | `match.startDate` (date only) < today |
| `isMatchInProgress` | `matchStatus.key == "INPROGRESS"` |
| `isMatchFinished` | `matchStatus.key` is neither `"INPROGRESS"` nor `"SCHEDULED"` (includes `FINISHED`, `CANCELLED`, `FORFEITED`, …) |
| `isAdminOrLeagueAdmin` | user has role `ADMIN` or `LEAGUE_ADMIN` |
| `hasMatchdayOwner` | `matchday.owner.clubId` is non-null and non-empty |
| `isMatchdayOwner` | user is `CLUB_ADMIN` **and** `clubId == matchday.owner.clubId` **and** `hasMatchdayOwner` |
| `isHomeClubAdmin` | user is `CLUB_ADMIN` **and** `clubId == match.home.clubId` |
| `isAwayClubAdmin` | user is `CLUB_ADMIN` **and** `clubId == match.away.clubId` |
| `isCurrentSeason` | `match.season.alias == CURRENT_SEASON` env var (if env var is empty, all seasons pass) |

---

## Permission Gates

Each gate maps to one or more API endpoints. All gates default to `false`.

| Gate | `MatchAction` enum value | Protects |
|------|--------------------------|---------|
| `canEditMatch` | `EDIT_SCHEDULING` | `PATCH /matches/{id}` — `startDate`, `venue` fields |
| `canChangeStatus` | `EDIT_STATUS_RESULT` | `PATCH /matches/{id}` — `matchStatus`, `finishType` fields |
| `canEditRosterHome` | `EDIT_ROSTER_HOME` | `PUT /matches/{id}/home/roster`, `POST /matches/{id}/home/roster/validate`; `PATCH /matches/{id}` — `home.roster` |
| `canEditRosterAway` | `EDIT_ROSTER_AWAY` | `PUT /matches/{id}/away/roster`, `POST /matches/{id}/away/roster/validate`; `PATCH /matches/{id}` — `away.roster` |
| `canEditScoresHome` | `EDIT_SCORES_HOME` | `POST/PATCH/DELETE /matches/{id}/home/scores/{score_id}`; `PATCH /matches/{id}` — `home.scores` |
| `canEditScoresAway` | `EDIT_SCORES_AWAY` | `POST/PATCH/DELETE /matches/{id}/away/scores/{score_id}`; `PATCH /matches/{id}` — `away.scores` |
| `canEditPenaltiesHome` | `EDIT_PENALTIES_HOME` | `POST/PATCH/DELETE /matches/{id}/home/penalties/{penalty_id}`; `PATCH /matches/{id}` — `home.penalties` |
| `canEditPenaltiesAway` | `EDIT_PENALTIES_AWAY` | `POST/PATCH/DELETE /matches/{id}/away/penalties/{penalty_id}`; `PATCH /matches/{id}` — `away.penalties` |
| `canAccessMatchCenter` | `ACCESS_MATCH_CENTER` | `PATCH /matches/{id}` — `home.timeouts`, `away.timeouts`; future live-event endpoints |
| `canEditSupplementary` | `EDIT_SUPPLEMENTARY` | `PATCH /matches/{id}` — `supplementarySheet` field |

> **Note:** `referee1`, `referee2`, and `matchSheetComplete` are covered by an internal `EDIT_MATCH_DATA` action that follows the same access rules as `canAccessMatchCenter` (effective home admin or matchday owner on match day). These are not part of the ten public-facing spec gates.

---

## Permission Rules

Rules are applied in order; later rules override earlier ones.

---

### Rule 1 — Unauthenticated

All gates → `false`. Enforced by JWT middleware before any route handler is reached.

---

### Rule 2 — Non-admins blocked from past matches

**Condition:** `isMatchInPast AND NOT isAdminOrLeagueAdmin`

All ten gates → `false`. No further rules are evaluated.

---

### Rule 3 — ADMIN / LEAGUE_ADMIN baseline

| Gate | Granted when |
|------|-------------|
| `canEditMatch` | Always |
| `canChangeStatus` | Always |
| `canEditRosterHome` | `isMatchDay OR isMatchInProgress` |
| `canEditRosterAway` | `isMatchDay OR isMatchInProgress` |
| `canAccessMatchCenter` | `isMatchDay OR isMatchInProgress` |
| `canEditSupplementary` | `isMatchDay OR isMatchInProgress` |
| `canEditScoresHome/Away` | `isMatchDay OR isMatchInProgress` |
| `canEditPenaltiesHome/Away` | `isMatchDay OR isMatchInProgress` |

---

### Rule 4 — Home CLUB_ADMIN

**Condition:** `isHomeClubAdmin`

| Gate | Granted when |
|------|-------------|
| `canEditRosterHome` | Always (regardless of match day) |
| `canEditRosterAway` | `isMatchDay` |
| `canChangeStatus` | `isMatchDay` |
| `canAccessMatchCenter` | `isMatchDay` |
| `canEditSupplementary` | `isMatchDay` |
| `canEditScoresHome/Away` | Via `canAccessMatchCenter` (same condition) |
| `canEditPenaltiesHome/Away` | Via `canAccessMatchCenter` (same condition) |

The home club admin always receives full match-day privileges, regardless of whether a matchday owner is assigned. When both are present, Rule 4 and Rule 6 grant the same set of permissions and do not conflict.

---

### Rule 5 — Away CLUB_ADMIN

**Condition:** `isAwayClubAdmin`

| Gate | Granted when |
|------|-------------|
| `canEditRosterAway` | `NOT isMatchDay AND NOT isMatchInPast` (future match) |
| `canEditRosterAway` | `isMatchDay AND NOT isMatchInProgress` (match day, pre-kickoff) |

The away admin never receives match center, status, or supplementary access.

---

### Rule 6 — Matchday owner CLUB_ADMIN

**Condition:** `isMatchdayOwner AND isMatchDay`

| Gate | Granted |
|------|---------|
| `canEditRosterHome` | Yes |
| `canEditRosterAway` | Yes |
| `canChangeStatus` | Yes |
| `canAccessMatchCenter` | Yes |
| `canEditSupplementary` | Yes |
| `canEditScoresHome/Away` | Yes (via `canAccessMatchCenter`) |
| `canEditPenaltiesHome/Away` | Yes (via `canAccessMatchCenter`) |

The matchday owner does **not** receive `canEditMatch` (scheduling) through this rule — see Rule 7 for the non-production exception.

---

### Rule 7 — Non-production scheduling (environment flag)

**Condition:** `settings.ENVIRONMENT != "production"`

| Gate | Granted to |
|------|-----------|
| `canEditMatch` | `isHomeClubAdmin` |
| `canEditMatch` | `isMatchdayOwner` (any day, not just match day) |

This allows club admins to reschedule matches to today during development and staging, enabling match-centre testing without waiting for the actual match date. All other constraints (season lock, role check, past-match guard) still apply.

---

### Rule 8 — Finished match overrides

Applied when `isMatchFinished`. Overrides all previous rules for the affected gates.

**If `isAdminOrLeagueAdmin`:** All ten gates → `true`.

**Otherwise (CLUB_ADMIN):**

| Gate | Result |
|------|--------|
| `canEditMatch` | Revoked → `false` |
| `canChangeStatus` | `true` only if `isMatchDay AND (isHomeClubAdmin OR isMatchdayOwner)` |
| `canEditRosterHome` | Revoked → `false` |
| `canEditRosterAway` | Revoked → `false` |
| `canAccessMatchCenter` | `true` only if `isMatchDay AND (isHomeClubAdmin OR isMatchdayOwner)` |
| `canEditSupplementary` | Revoked → `false` |
| `canEditScoresHome/Away` | `true` only if `isMatchDay AND (isHomeClubAdmin OR isMatchdayOwner)` |
| `canEditPenaltiesHome/Away` | `true` only if `isMatchDay AND (isHomeClubAdmin OR isMatchdayOwner)` |

Status/result, match center, score and penalty editing after the final whistle is limited to the **same match day** so that late corrections (e.g. setting `finishType`, scoresheet review) are possible while preventing retroactive edits on other days.

---

### Rule 9 — Season restriction (final override)

**Condition:** `NOT isCurrentSeason`

All ten gates → `false`, unconditionally. This overrides **every** other rule, including admin access. The current season is configured via the `CURRENT_SEASON` environment variable.

---

## Rule Evaluation Order (summary)

```
1. Unauthenticated              → deny all, stop
2. isMatchInPast + non-admin    → deny all, skip to Rule 9
3. Admin/LeagueAdmin baseline   → set scheduling + status always; roster/center on match day
4. Home CLUB_ADMIN              → home roster always; full match-day gates on match day
5. Away CLUB_ADMIN              → away roster before/on match day (pre-kickoff only)
6. Matchday owner CLUB_ADMIN    → full gate set on match day
7. Non-prod environment         → home/owner admin gets scheduling regardless of day
8. isMatchFinished override     → admin gets all; home/owner admin gets status+center+scores+penalties on match day
9. NOT isCurrentSeason          → deny all (final override, no exceptions)
```

---

## Quick Reference Matrix

`✓` = granted · `—` = denied · `(md)` = match day only · `(md/ip)` = match day or in-progress

| Gate | ADMIN / LEAGUE_ADMIN | Home CLUB_ADMIN | Away CLUB_ADMIN | Matchday Owner |
|------|---------------------|-----------------|-----------------|----------------|
| canEditMatch | ✓ always | ✓ non-prod only (md/any) | — | ✓ non-prod only |
| canChangeStatus | ✓ always | ✓ (md; or finished+md) | — | ✓ (md; or finished+md) |
| canEditRosterHome | ✓ (md/ip) | ✓ always | — | ✓ (md) |
| canEditRosterAway | ✓ (md/ip) | ✓ (md) | ✓ future/pre-kickoff | ✓ (md) |
| canEditScoresHome | ✓ (md/ip or finished) | ✓ (md or finished+md) | — | ✓ (md or finished+md) |
| canEditScoresAway | ✓ (md/ip or finished) | ✓ (md or finished+md) | — | ✓ (md or finished+md) |
| canEditPenaltiesHome | ✓ (md/ip or finished) | ✓ (md or finished+md) | — | ✓ (md or finished+md) |
| canEditPenaltiesAway | ✓ (md/ip or finished) | ✓ (md or finished+md) | — | ✓ (md or finished+md) |
| canAccessMatchCenter | ✓ (md/ip) | ✓ (md or finished+md) | — | ✓ (md or finished+md) |
| canEditSupplementary | ✓ (md/ip) | ✓ (md) | — | ✓ (md) |

> **Season lock (Rule 9):** All cells above become `—` when the match belongs to a non-current season.

---

## Implementation Reference

| Component | File |
|-----------|------|
| Permission service | `services/match_permission_service.py` |
| `MatchAction` enum | `services/match_permission_service.py` |
| Match PATCH gating | `routers/matches.py` — `update_match()` |
| Roster gating | `routers/roster.py` — `update_roster()`, `validate_roster()` |
| Score gating | `routers/scores.py` — `create_score()`, `patch_one_score()`, `delete_one_score()` |
| Penalty gating | `routers/penalties.py` — `create_penalty()`, `patch_one_penalty()`, `delete_one_penalty()` |
| Unit tests | `tests/unit/test_match_permission_service.py` |
| Current season config | `CURRENT_SEASON` env var (see `config.py`) |
| Environment flag | `ENVIRONMENT` env var — `"production"` disables Rule 7 relaxation |
