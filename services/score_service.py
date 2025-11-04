
"""
Score Service - Business logic for score management

Handles score creation, updates, deletion with incremental stats updates
and validation.
"""

from typing import Any

from bson import ObjectId
from fastapi.encoders import jsonable_encoder

from exceptions import (
    DatabaseOperationException,
    ResourceNotFoundException,
    ValidationException,
)
from logging_config import logger
from models.matches import ScoresBase, ScoresDB, ScoresUpdate
from services.stats_service import StatsService
from utils import parse_time_from_seconds, parse_time_to_seconds, populate_event_player_fields


class ScoreService:
    """Service for managing scores in matches"""

    def __init__(self, db):
        self.db = db
        self.stats_service = StatsService(db)

    async def _get_match(self, match_id: str) -> dict:
        """Get match document or raise exception"""
        match = await self.db["matches"].find_one({"_id": match_id})
        if match is None:
            raise ResourceNotFoundException(resource_type="Match", resource_id=match_id)
        return match

    async def _validate_match_status(self, match: dict) -> None:
        """Validate match status allows modifications"""
        match_status = match.get("matchStatus", {}).get("key")
        if match_status != "INPROGRESS":
            raise ValidationException(
                field="matchStatus",
                message="Scores can only be modified when match status is INPROGRESS",
                details={"current_status": match_status},
            )

    async def _validate_player_in_roster(
        self, match: dict, team_flag: str, score_data: dict
    ) -> None:
        """Validate that goal and assist players are in the roster"""
        roster = match.get(team_flag, {}).get("roster") or []
        roster_player_ids = {player["player"]["playerId"] for player in roster}

        # Check goal player
        goal_player = score_data.get("goalPlayer")
        if goal_player and goal_player.get("playerId"):
            if goal_player["playerId"] not in roster_player_ids:
                raise ValidationException(
                    field="goalPlayer",
                    message=f"Goal player {goal_player['playerId']} not in roster",
                    details={"match_id": match["_id"], "team_flag": team_flag},
                )

        # Check assist player
        assist_player = score_data.get("assistPlayer")
        if assist_player and assist_player.get("playerId"):
            if assist_player["playerId"] not in roster_player_ids:
                raise ValidationException(
                    field="assistPlayer",
                    message=f"Assist player {assist_player['playerId']} not in roster",
                    details={"match_id": match["_id"], "team_flag": team_flag},
                )

    async def get_scores(self, match_id: str, team_flag: str) -> list[ScoresDB]:
        """
        Fetch and populate score sheet for a team

        Args:
            match_id: The match ID
            team_flag: Either 'home' or 'away'

        Returns:
            List of ScoresDB objects with populated player fields
        """
        team_flag = team_flag.lower()
        if team_flag not in ["home", "away"]:
            raise ValidationException(
                field="team_flag", message=f"Must be 'home' or 'away', got '{team_flag}'"
            )

        match = await self._get_match(match_id)
        scores = match.get(team_flag, {}).get("scores") or []

        # Parse time and populate player fields
        for score in scores:
            if "matchSeconds" in score:
                score["matchTime"] = parse_time_from_seconds(score["matchSeconds"])
            if score.get("goalPlayer"):
                await populate_event_player_fields(self.db, score["goalPlayer"])
            if score.get("assistPlayer"):
                await populate_event_player_fields(self.db, score["assistPlayer"])

        return [ScoresDB(**score) for score in scores]

    async def get_score_by_id(self, match_id: str, team_flag: str, score_id: str) -> ScoresDB:
        """
        Fetch a single score by ID

        Args:
            match_id: The match ID
            team_flag: Either 'home' or 'away'
            score_id: The score ID

        Returns:
            ScoresDB object with populated fields
        """
        team_flag = team_flag.lower()
        if team_flag not in ["home", "away"]:
            raise ValidationException(
                field="team_flag", message=f"Must be 'home' or 'away', got '{team_flag}'"
            )

        score = await self.db["matches"].find_one(
            {"_id": match_id, f"{team_flag}.scores._id": score_id},
            {"_id": 0, f"{team_flag}.scores.$": 1},
        )

        if not score or not score.get(team_flag) or "scores" not in score.get(team_flag):
            raise ResourceNotFoundException(
                resource_type="Score",
                resource_id=score_id,
                details={"match_id": match_id, "team_flag": team_flag},
            )

        score_data = score[team_flag]["scores"][0]

        # Parse time and populate player fields
        if "matchSeconds" in score_data:
            score_data["matchTime"] = parse_time_from_seconds(score_data["matchSeconds"])
        if score_data.get("goalPlayer"):
            await populate_event_player_fields(self.db, score_data["goalPlayer"])
        if score_data.get("assistPlayer"):
            await populate_event_player_fields(self.db, score_data["assistPlayer"])

        return ScoresDB(**score_data)

    async def create_score(
        self, match_id: str, team_flag: str, score: ScoresBase
    ) -> ScoresDB:
        """
        Create a new score with incremental stats updates

        Args:
            match_id: The match ID
            team_flag: Either 'home' or 'away'
            score: The score data

        Returns:
            Created ScoresDB object
        """
        team_flag = team_flag.lower()
        if team_flag not in ["home", "away"]:
            raise ValidationException(
                field="team_flag", message=f"Must be 'home' or 'away', got '{team_flag}'"
            )

        match = await self._get_match(match_id)
        await self._validate_match_status(match)

        # Convert to dict for validation
        score_dict = score.model_dump()
        await self._validate_player_in_roster(match, team_flag, score_dict)

        # Get match info for standings updates
        t_alias = match.get("tournament", {}).get("alias")
        s_alias = match.get("season", {}).get("alias")
        r_alias = match.get("round", {}).get("alias")
        md_alias = match.get("matchday", {}).get("alias")
        goal_player_id = score.goalPlayer.playerId if score.goalPlayer else None
        assist_player_id = score.assistPlayer.playerId if score.assistPlayer else None

        # Prepare score data
        new_score_id = str(ObjectId())
        score_data: dict[str, Any] = {
            "_id": new_score_id,
            **score_dict,
            "matchSeconds": parse_time_to_seconds(score.matchTime),
        }
        score_data.pop("id", None)
        score_data = jsonable_encoder(score_data)

        # Build incremental update operations
        array_filters = []
        if goal_player_id:
            array_filters.append({"goalPlayer.player.playerId": goal_player_id})
        if assist_player_id:
            array_filters.append({"assistPlayer.player.playerId": assist_player_id})

        update_operations: dict[str, Any] = {
            "$push": {f"{team_flag}.scores": score_data},
            "$inc": {
                f"{team_flag}.stats.goalsFor": 1,
                f"{'away' if team_flag == 'home' else 'home'}.stats.goalsAgainst": 1,
            },
        }

        # Add roster incremental updates
        roster_increments: dict[str, int] = {}
        if goal_player_id:
            roster_increments[f"{team_flag}.roster.$[goalPlayer].goals"] = 1
            roster_increments[f"{team_flag}.roster.$[goalPlayer].points"] = 1
        if assist_player_id:
            roster_increments[f"{team_flag}.roster.$[assistPlayer].assists"] = 1
            roster_increments[f"{team_flag}.roster.$[assistPlayer].points"] = 1

        if roster_increments:
            update_operations["$inc"].update(roster_increments)

        # Execute update
        update_result = await self.db["matches"].update_one(
            {"_id": match_id},
            update_operations,
            array_filters=array_filters if array_filters else None,
        )

        if update_result.modified_count == 0:
            raise DatabaseOperationException(
                operation="create_score",
                collection="matches",
                details={"match_id": match_id, "score_data": score_data},
            )

        # Update standings
        await self.stats_service.aggregate_round_standings(t_alias, s_alias, r_alias)
        await self.stats_service.aggregate_matchday_standings(t_alias, s_alias, r_alias, md_alias)

        logger.info(
            "Score created with incremental updates",
            extra={
                "match_id": match_id,
                "score_id": new_score_id,
                "goal_player": goal_player_id,
                "assist_player": assist_player_id,
            },
        )

        return await self.get_score_by_id(match_id, team_flag, new_score_id)

    async def update_score(
        self, match_id: str, team_flag: str, score_id: str, score: ScoresUpdate
    ) -> ScoresDB:
        """
        Update an existing score

        Args:
            match_id: The match ID
            team_flag: Either 'home' or 'away'
            score_id: The score ID
            score: The updated score data

        Returns:
            Updated ScoresDB object
        """
        team_flag = team_flag.lower()
        if team_flag not in ["home", "away"]:
            raise ValidationException(
                field="team_flag", message=f"Must be 'home' or 'away', got '{team_flag}'"
            )

        match = await self._get_match(match_id)
        await self._validate_match_status(match)

        # Convert to dict for validation
        score_dict = score.model_dump(exclude_unset=True)
        if score_dict:
            await self._validate_player_in_roster(match, team_flag, score_dict)

        # Prepare update data
        score_dict.pop("id", None)
        if "matchTime" in score_dict:
            score_dict["matchSeconds"] = parse_time_to_seconds(score_dict["matchTime"])
        score_dict = jsonable_encoder(score_dict)

        update_data: dict[str, dict[str, Any]] = {"$set": {}}
        for key, value in score_dict.items():
            update_data["$set"][f"{team_flag}.scores.$.{key}"] = value

        if not update_data.get("$set"):
            # No changes
            return await self.get_score_by_id(match_id, team_flag, score_id)

        # Execute update
        await self.db["matches"].update_one(
            {"_id": match_id, f"{team_flag}.scores._id": score_id}, update_data
        )

        # Recalculate roster stats
        await self.stats_service.calculate_roster_stats(match_id, team_flag)

        logger.info(
            "Score updated",
            extra={"match_id": match_id, "score_id": score_id, "team_flag": team_flag},
        )

        return await self.get_score_by_id(match_id, team_flag, score_id)

    async def delete_score(self, match_id: str, team_flag: str, score_id: str) -> None:
        """
        Delete a score with decremental stats updates

        Args:
            match_id: The match ID
            team_flag: Either 'home' or 'away'
            score_id: The score ID
        """
        team_flag = team_flag.lower()
        if team_flag not in ["home", "away"]:
            raise ValidationException(
                field="team_flag", message=f"Must be 'home' or 'away', got '{team_flag}'"
            )

        match = await self._get_match(match_id)
        await self._validate_match_status(match)

        # Find the score to delete
        current_score = None
        for score_entry in match.get(team_flag, {}).get("scores", []):
            if score_entry["_id"] == score_id:
                current_score = score_entry
                break

        if current_score is None:
            raise ResourceNotFoundException(
                resource_type="Score",
                resource_id=score_id,
                details={"match_id": match_id, "team_flag": team_flag},
            )

        # Get match info
        t_alias = match.get("tournament", {}).get("alias")
        s_alias = match.get("season", {}).get("alias")
        r_alias = match.get("round", {}).get("alias")
        md_alias = match.get("matchday", {}).get("alias")
        goal_player_id = current_score.get("goalPlayer", {}).get("playerId")
        assist_player = current_score.get("assistPlayer")
        assist_player_id = assist_player.get("playerId") if assist_player else None

        # Build decremental update operations
        array_filters = []
        if goal_player_id:
            array_filters.append({"goalPlayer.player.playerId": goal_player_id})
        if assist_player_id:
            array_filters.append({"assistPlayer.player.playerId": assist_player_id})

        roster_decrements: dict[str, int] = {}
        if goal_player_id:
            roster_decrements[f"{team_flag}.roster.$[goalPlayer].goals"] = -1
            roster_decrements[f"{team_flag}.roster.$[goalPlayer].points"] = -1
        if assist_player_id:
            roster_decrements[f"{team_flag}.roster.$[assistPlayer].assists"] = -1
            roster_decrements[f"{team_flag}.roster.$[assistPlayer].points"] = -1

        inc_operations = {
            f"{team_flag}.stats.goalsFor": -1,
            f"{'away' if team_flag == 'home' else 'home'}.stats.goalsAgainst": -1,
        }
        inc_operations.update(roster_decrements)

        update_operations = {
            "$pull": {f"{team_flag}.scores": {"_id": score_id}},
            "$inc": inc_operations,
        }

        # Execute update
        result = await self.db["matches"].update_one(
            {"_id": match_id, f"{team_flag}.scores._id": score_id},
            update_operations,
            array_filters=array_filters if array_filters else None,
        )

        if result.modified_count == 0:
            raise ResourceNotFoundException(
                resource_type="Score",
                resource_id=score_id,
                details={"match_id": match_id, "team_flag": team_flag},
            )

        # Update standings
        await self.stats_service.aggregate_round_standings(t_alias, s_alias, r_alias)
        await self.stats_service.aggregate_matchday_standings(t_alias, s_alias, r_alias, md_alias)

        logger.info(
            "Score deleted with decremental updates",
            extra={
                "match_id": match_id,
                "score_id": score_id,
                "goal_player": goal_player_id,
                "assist_player": assist_player_id,
            },
        )
