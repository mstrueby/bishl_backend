from datetime import datetime
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from bson import ObjectId
from typing import List, Callable
import re
import os
import aiohttp
import httpx
import cloudinary
import cloudinary.uploader

BASE_URL = os.environ['BE_API_URL']
DEBUG_LEVEL = int(os.environ['DEBUG_LEVEL'])


async def populate_event_player_fields(mongodb, event_player_dict):
  """Populate display fields for EventPlayer from player data"""
  if event_player_dict and event_player_dict.get("playerId"):
    player_doc = await mongodb["players"].find_one({"_id": event_player_dict["playerId"]})
    if player_doc:
      event_player_dict["displayFirstName"] = player_doc.get("displayFirstName")
      event_player_dict["displayLastName"] = player_doc.get("displayLastName")
      event_player_dict["imageUrl"] = player_doc.get("imageUrl")
      event_player_dict["imageVisible"] = bool(player_doc.get("imageVisible", False))
  return event_player_dict


def to_camel(string: str) -> str:
  components = string.split('_')
  return components[0] + ''.join(x.title() for x in components[1:])


def configure_cloudinary():
  cloudinary.config(
      cloud_name=os.environ["CLDY_CLOUD_NAME"],
      api_key=os.environ["CLDY_API_KEY"],
      api_secret=os.environ["CLDY_API_SECRET"],
  )


def parse_date(date_str):
  return datetime.strptime(date_str, '%Y-%m-%d') if date_str else None


def parse_datetime(datetime_str):
  return datetime.strptime(datetime_str,
                           '%Y-%m-%d %H:%M:%S') if datetime_str else None


def parse_time_to_seconds(time_str):
  if not time_str:
    return 0
  minutes, seconds = map(int, time_str.split(':'))
  return minutes * 60 + seconds


def parse_time_from_seconds(seconds):
  minutes = seconds // 60
  seconds = seconds % 60
  return f"{minutes:02d}:{seconds:02d}"


def flatten_dict(d, parent_key='', sep='.'):
  items = []
  for k, v in d.items():
    new_key = f'{parent_key}{sep}{k}' if parent_key else k
    if isinstance(v, dict):
      items.extend(flatten_dict(v, new_key, sep=sep).items())
    else:
      items.append((new_key, v))
  return dict(items)


def my_jsonable_encoder(obj):
  result = {}
  for field_name, val in obj.__dict__.items():
    #print(field_name, "/", val, "/", dict)
    if field_name == "id":
      # If the field name is 'id', use '_id' as the key instead.
      result["_id"] = str(val)
      continue
    if isinstance(val, datetime):
      result[field_name] = val
      continue
    if isinstance(val, BaseModel) and val:
      # Recursively encode nested collections
      result[field_name] = my_jsonable_encoder(val)
      continue
    result[field_name] = jsonable_encoder(val)
  return result


def empty_str_to_none(v, field_name: str):
  if v == "":
    print(f"Field '{field_name}' is an empty string and has been set to None.")
    return None
  return v


def prevent_empty_str(v, field_name: str):
  if v is None or v == "":
    raise ValueError(f"Field '{field_name}' cannot be null or empty string")
  return v


def validate_dict_of_strings(v, field_name: str):
  if not isinstance(v, dict):
    raise ValueError(f"Field '{field_name}' must be a dictionary")
  for key, value in v.items():
    if not isinstance(key, str) or not isinstance(value, str):
      raise ValueError(
          f"Field '{field_name}' must be a dictionary with string key-value pairs"
      )
  return v


def validate_match_time(v, field_name: str):
  if not isinstance(v, str) or not re.match(r'^\d{1,3}:[0-5][0-9]$', v):
    raise ValueError(f'Field {field_name} must be in the format MIN:SS')
  return v


# fetch_standings_settings has been moved to services.stats_service.StatsService.get_standings_settings()
# This function is deprecated - import StatsService directly instead


# calc_match_stats has been moved to services.stats_service.StatsService.calculate_match_stats()
# This function is deprecated - import StatsService directly instead


# calc_standings_per_round has been moved to services.stats_service.StatsService.aggregate_round_standings()
# This function is deprecated - import StatsService directly instead


# calc_standings_per_matchday has been moved to services.stats_service.StatsService.aggregate_matchday_standings()
# This function is deprecated - import StatsService directly instead


async def fetch_ref_points(t_alias: str, s_alias: str, r_alias: str,
                           md_alias: str) -> int:
  if DEBUG_LEVEL > 0:
    print("fetching referee points...")
  async with aiohttp.ClientSession() as session:
    async with session.get(
        f"{BASE_URL}/tournaments/{t_alias}/seasons/{s_alias}/rounds/{r_alias}/matchdays/{md_alias}"
    ) as response:
      if response.status != 200:
        raise HTTPException(
            status_code=404,
            detail=
            f"Matchday {md_alias} not found for {t_alias} / {s_alias} / {r_alias}"
        )
      return (await response.json()).get('matchSettings').get('refereePoints')



  

async def get_sys_ref_tool_token(email: str, password: str):
  login_url = f"{os.environ['BE_API_URL']}/users/login"
  login_data = {
      "email": email,
      "password": password
  }
  async with httpx.AsyncClient() as client:
    login_response = await client.post(login_url, json=login_data)

  if login_response.status_code != 200:
    raise Exception(f"Error logging in: {login_response.json()}")
  return login_response.json()['token']

# calc_roster_stats has been moved to services.stats_service.StatsService.calculate_roster_stats()
# This function is deprecated - import StatsService directly instead
async def calc_roster_stats(mongodb, match_id: str, team_flag: str) -> None:
  """
  DEPRECATED: Use StatsService.calculate_roster_stats() instead.
  
  This is a temporary wrapper for backward compatibility.
  """
  from services.stats_service import StatsService
  stats_service = StatsService(mongodb)
  await stats_service.calculate_roster_stats(match_id, team_flag)


# Refresh Stats for EACH PLAYER(!) in a tournament/season/round/matchday
# calc stats for round / matchday if createStats is true
# ----------------------------------------------------------
async def calc_player_card_stats(mongodb, player_ids: List[str], t_alias: str,
                                 s_alias: str, r_alias: str,
                                 md_alias: str, token_payload=None) -> None:
  """
  Calculate and update player statistics for a given tournament/season/round/matchday.
  Also handles called matches logic for assignedTeams updates.
  """
  if DEBUG_LEVEL > 0:
    print(f'calculating player card stats for {t_alias}, {s_alias}, {r_alias}, {md_alias} with {len(player_ids)} players...')

  def _create_team_dict(match_team_data: dict) -> dict:
    """Create a standardized team dictionary from match data."""
    return {
        'name': match_team_data.get('name'),
        'fullName': match_team_data.get('fullName'),
        'shortName': match_team_data.get('shortName'),
        'tinyName': match_team_data.get('tinyName')
    }

  def _initialize_player_stats(player_id: str, team_key: str, team: dict, 
                               match_info: dict, player_card_stats: dict) -> None:
    """Initialize player stats structure if it doesn't exist."""
    if player_id not in player_card_stats:
      player_card_stats[player_id] = {}

    if team_key not in player_card_stats[player_id]:
      player_card_stats[player_id][team_key] = {
          'tournament': match_info['tournament'],
          'season': match_info['season'],
          'round': match_info['round'],
          'matchday': match_info['matchday'],
          'team': team,
          'gamesPlayed': 0,
          'goals': 0,
          'assists': 0,
          'points': 0,
          'penaltyMinutes': 0,
          'calledMatches': 0,
      }

  def _update_player_stats(player_id: str, team: dict, roster_player: dict, 
                          match_info: dict, player_card_stats: dict) -> None:
    """Update individual player statistics from roster data."""
    team_key = team['fullName']
    _initialize_player_stats(player_id, team_key, team, match_info, player_card_stats)

    # Only count stats for finished/active matches
    if match_info['match_status']['key'] in ['FINISHED', 'INPROGRESS', 'FORFEITED']:
      stats = player_card_stats[player_id][team_key]
      stats['gamesPlayed'] += 1
      stats['goals'] += roster_player.get('goals', 0)
      stats['assists'] += roster_player.get('assists', 0)
      stats['points'] += roster_player.get('points', 0)
      stats['penaltyMinutes'] += roster_player.get('penaltyMinutes', 0)

      # Track called matches
      if roster_player.get('called', False):
        stats['calledMatches'] += 1

  def _process_roster_for_team(matches: List[dict], team_flag: str, player_ids: List[str], 
                              player_card_stats: dict, flag: str) -> None:
    """Process roster data for a specific team (home/away) across all matches."""
    for match in matches:
      match_info = {
          'tournament': match.get('tournament', {}),
          'season': match.get('season', {}),
          'round': match.get('round', {}),
          'matchday': match.get('matchday', {}) if flag == 'MATCHDAY' else None,
          'match_status': match.get('matchStatus', {})
      }

      roster = match.get(team_flag, {}).get('roster', [])
      team = _create_team_dict(match.get(team_flag, {}))

      if DEBUG_LEVEL > 10:
        print(f"### {team_flag}_roster", roster)

      for roster_player in roster:
        player_id = roster_player.get('player', {}).get('playerId')
        if player_id and player_id in player_ids:
          if DEBUG_LEVEL > 10:
            print(f"### {team_flag}_roster_player", roster_player)
          _update_player_stats(player_id, team, roster_player, match_info, player_card_stats)

  async def _save_player_stats_to_db(mongodb, player_card_stats: dict, 
                                    t_alias: str, s_alias: str, r_alias: str, 
                                    md_alias: str, flag: str) -> None:
    """Save calculated player statistics to the database."""
    for player_id, stats_by_team in player_card_stats.items():
      for team_key, stats in stats_by_team.items():
        player = await mongodb['players'].find_one({"_id": player_id})
        if not player:
          raise HTTPException(
              status_code=404,
              detail=f"Player {player_id} not found in mongoDB")

        # Merge with existing stats or create new ones
        existing_stats = player.get('stats', [])
        updated_stats = []
        stat_found = False

        for existing_stat in existing_stats:
          # Check if this stat entry should be updated
          if (_should_update_stat(existing_stat, stats, t_alias, s_alias, 
                                 r_alias, md_alias, flag)):
            merged_stat = {**existing_stat, **stats, 
                          'team': existing_stat.get('team', stats['team'])}
            updated_stats.append(merged_stat)
            stat_found = True
          else:
            updated_stats.append(existing_stat)

        # Add new stat if no existing one was updated
        if not stat_found:
          updated_stats.append(stats)

        # Save to database
        result = await mongodb['players'].update_one(
            {"_id": player_id}, 
            {"$set": {"stats": updated_stats}}
        )
        if not result.acknowledged:
          print(f"Warning: Failed to update stats for player {player_id}")

  def _should_update_stat(existing_stat: dict, new_stats: dict, 
                         t_alias: str, s_alias: str, r_alias: str, 
                         md_alias: str, flag: str) -> bool:
    """Check if an existing stat entry should be updated with new data."""
    return (existing_stat.get('tournament', {}).get('alias') == t_alias and
            existing_stat.get('season', {}).get('alias') == s_alias and
            existing_stat.get('round', {}).get('alias') == r_alias and
            existing_stat.get('team', {}).get('fullName') == new_stats['team']['fullName'] and
            (existing_stat.get('matchday', {}).get('alias') == md_alias if flag == 'MATCHDAY' else True))

  async def _process_called_teams_assignments(player_ids: List[str], matches: List[dict],
                                            t_alias: str, s_alias: str) -> None:
    """Check calledMatches for affected players and update assignedTeams if needed."""
    base_url = os.environ.get('BE_API_URL', '')
    if not base_url or not token_payload:
      return

    # Prepare authentication headers
    from authentication import AuthHandler
    auth_handler = AuthHandler()
    auth_token = auth_handler.encode_token({
        "_id": token_payload.sub,
        "roles": token_payload.roles,
        "firstName": token_payload.firstName,
        "lastName": token_payload.lastName,
        "club": {
            "clubId": token_payload.clubId,
            "clubName": token_payload.clubName
        } if token_payload.clubId else None
    })
    headers = {"Authorization": f"Bearer {auth_token}"}

    for player_id in player_ids:
      try:
        async with httpx.AsyncClient() as client:
          player_response = await client.get(f"{base_url}/players/{player_id}", headers=headers)
          if player_response.status_code != 200:
            continue

          player_data = player_response.json()
          teams_to_check = _find_called_teams(player_id, matches)

          await _update_assigned_teams_for_called_matches(
              client, player_id, player_data, teams_to_check, t_alias, s_alias, base_url, headers)

      except Exception as e:
        if DEBUG_LEVEL > 0:
          print(f"Error processing called matches for player {player_id}: {str(e)}")
        continue

  def _find_called_teams(player_id: str, matches: List[dict]) -> set:
    """Find all teams this player was called for across matches."""
    teams_to_check = set()

    for match in matches:
      for team_flag in ['home', 'away']:
        roster = match.get(team_flag, {}).get('roster', [])
        for roster_player in roster:
          if (roster_player.get('player', {}).get('playerId') == player_id and
              roster_player.get('called', False)):
            current_team = match.get(team_flag, {}).get('team', {})
            current_club = match.get(team_flag, {}).get('club', {})
            if current_team and current_club:
              teams_to_check.add((
                current_team.get('teamId'),
                current_team.get('name'),
                current_team.get('alias'),
                current_team.get('ageGroup', ''),
                current_team.get('ishdId'),
                current_club.get('clubId'),
                current_club.get('name'),
                current_club.get('alias'),
                current_club.get('ishdId')
              ))

    return teams_to_check

  async def _update_assigned_teams_for_called_matches(client, player_id: str, player_data: dict,
                                                     teams_to_check: set, t_alias: str, 
                                                     s_alias: str, base_url: str, headers: dict) -> None:
    """Update assignedTeams for players with 5+ called matches."""
    for team_info in teams_to_check:
      (team_id, team_name, team_alias, team_age_group, team_ishd_id,
       club_id, club_name, club_alias, club_ishd_id) = team_info

      # Check if player has 5+ called matches for this team
      player_stats = player_data.get('stats', [])
      for stat in player_stats:
        if (_has_enough_called_matches(stat, t_alias, s_alias, team_name) and
            not _team_already_assigned(player_data, team_id)):

          await _add_called_team_assignment(
              client, player_id, player_data, team_info, base_url, headers)
          break

  def _has_enough_called_matches(stat: dict, t_alias: str, s_alias: str, team_name: str) -> bool:
    """Check if a player has enough called matches for a team."""
    return (stat.get('tournament', {}).get('alias') == t_alias and
            stat.get('season', {}).get('alias') == s_alias and
            stat.get('team', {}).get('name') == team_name and
            stat.get('calledMatches', 0) >= 5)

  def _team_already_assigned(player_data: dict, team_id: str) -> bool:
    """Check if team is already in player's assignedTeams."""
    assigned_teams = player_data.get('assignedTeams', [])
    for club in assigned_teams:
      for team in club.get('teams', []):
        if team.get('teamId') == team_id:
          return True
    return False

  async def _add_called_team_assignment(client, player_id: str, player_data: dict,
                                       team_info: tuple, base_url: str, headers: dict) -> None:
    """Add a new team assignment with CALLED source."""
    (team_id, team_name, team_alias, team_age_group, team_ishd_id,
     club_id, club_name, club_alias, club_ishd_id) = team_info

    assigned_teams = player_data.get('assignedTeams', [])

    # Try to add to existing club or create new club
    club_found = False
    for club in assigned_teams:
      if club.get('clubId') == club_id:
        club['teams'].append(_create_team_assignment(team_info))
        club_found = True
        break

    if not club_found and club_id:
      assigned_teams.append(_create_club_assignment(team_info))

    # Update player in database
    update_response = await client.patch(
        f"{base_url}/players/{player_id}",
        json={"assignedTeams": assigned_teams},
        headers=headers
    )
    if update_response.status_code == 200 and DEBUG_LEVEL > 0:
      if DEBUG_LEVEL > 10:
        print(f"Added CALLED team assignment for player {player_id}")

  def _create_team_assignment(team_info: tuple) -> dict:
    """Create a team assignment dictionary."""
    team_id, team_name, team_alias, team_age_group, team_ishd_id = team_info[:5]
    return {
        "teamId": team_id,
        "teamName": team_name,
        "teamAlias": team_alias,
        "teamAgeGroup": team_age_group,
        "teamIshdId": team_ishd_id,
        "passNo": "",
        "source": "CALLED",
        "modifyDate": None,
        "active": True,
        "jerseyNo": None
    }

  def _create_club_assignment(team_info: tuple) -> dict:
    """Create a club assignment dictionary with team."""
    club_id, club_name, club_alias, club_ishd_id = team_info[5:]
    return {
        "clubId": club_id,
        "clubName": club_name,
        "clubAlias": club_alias,
        "clubIshdId": club_ishd_id,
        "teams": [_create_team_assignment(team_info)]
    }

  async def _update_player_card_stats(flag: str, matches: List[dict], 
                                     player_card_stats: dict) -> None:
    """Main function to update player card statistics."""
    if flag not in ['ROUND', 'MATCHDAY']:
      raise ValueError("Invalid flag, only 'ROUND' or 'MATCHDAY' are accepted.")

    if DEBUG_LEVEL > 10:
      print("count matches", len(matches))

    # Process rosters for both home and away teams
    _process_roster_for_team(matches, 'home', player_ids, player_card_stats, flag)
    _process_roster_for_team(matches, 'away', player_ids, player_card_stats, flag)

    if DEBUG_LEVEL > 10:
      print("### player_card_stats", player_card_stats)

    # Save statistics to database
    await _save_player_stats_to_db(mongodb, player_card_stats, t_alias, s_alias, 
                                  r_alias, md_alias, flag)

  # Main execution logic
  if not all([t_alias, s_alias, r_alias, md_alias]):
    return

  # Fetch round information
  async with httpx.AsyncClient() as client:
    response = await client.get(
        f"{BASE_URL}/tournaments/{t_alias}/seasons/{s_alias}/rounds/{r_alias}")
    if response.status_code != 200:
      raise HTTPException(status_code=response.status_code,
                          detail="Could not fetch the round information")
    round_info = response.json()

  # Process round statistics
  matches = []
  if round_info.get('createStats', False):
    matches = await mongodb["matches"].find({
        "tournament.alias": t_alias,
        "season.alias": s_alias,
        "round.alias": r_alias
    }).to_list(length=None)

    player_card_stats = {}
    await _update_player_card_stats("ROUND", matches, player_card_stats)

    if DEBUG_LEVEL > 10:
      print("### round - player_card_stats", player_card_stats)
  elif DEBUG_LEVEL > 10:
    print("### no round stats")

  # Process matchday statistics
  for matchday in round_info.get('matchdays', []):
    if matchday.get('createStats', False):
      matchday_matches = await mongodb["matches"].find({
          "tournament.alias": t_alias,
          "season.alias": s_alias,
          "round.alias": r_alias,
          "matchday.alias": md_alias
      }).to_list(length=None)

      player_card_stats = {}
      await _update_player_card_stats("MATCHDAY", matchday_matches, player_card_stats)

      if DEBUG_LEVEL > 10:
        print("### matchday - player_card_stats", player_card_stats)

      # Update matches for called teams processing
      if not matches:
        matches = matchday_matches
    elif DEBUG_LEVEL > 10:
      print("### no matchday stats")

  # Process called teams assignments
  if matches:
    await _process_called_teams_assignments(player_ids, matches, t_alias, s_alias)