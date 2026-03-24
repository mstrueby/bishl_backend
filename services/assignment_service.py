"""
Assignment Service - Business logic for referee assignment management

Handles assignment creation, updates, validation, and synchronization with matches.
"""

from datetime import date, datetime, timedelta

from fastapi.encoders import jsonable_encoder
from motor.motor_asyncio import AsyncIOMotorClientSession

from config import settings
from exceptions import (
    ResourceNotFoundException,
    ValidationException,
)
from logging_config import logger
from models.assignments import AssignmentDB, Referee, Status, StatusHistory


class AssignmentService:
    """Service for managing referee assignments"""

    def __init__(self, db):
        self.db = db

    async def get_assignment_by_id(self, assignment_id: str) -> dict | None:
        """Get assignment by ID"""
        result = await self.db["assignments"].find_one({"_id": assignment_id})
        return dict(result) if result else None

    async def get_assignments_by_match(self, match_id: str) -> list[dict]:
        """Get all assignments for a match"""
        assignments = await self.db["assignments"].find({"matchId": match_id}).to_list(length=None)
        return list(assignments)

    async def get_assignments_by_referee(self, referee_id: str) -> list[dict]:
        """Get all assignments for a referee"""
        assignments = (
            await self.db["assignments"].find({"referee.userId": referee_id}).to_list(length=None)
        )
        return list(assignments)

    async def validate_assignment_status_transition(
        self, current_status: Status, new_status: Status, is_ref_admin: bool
    ) -> bool:
        """
        Validate if status transition is allowed

        Args:
            current_status: Current assignment status
            new_status: Proposed new status
            is_ref_admin: Whether user has ref admin privileges

        Returns:
            True if transition is valid

        Raises:
            ValidationException: If transition is invalid
        """
        if is_ref_admin:
            # REF_ADMIN allowed transitions
            valid_transitions = {
                Status.requested: [Status.assigned],
                Status.assigned: [Status.unavailable],
                Status.accepted: [Status.unavailable],
            }
        else:
            # REFEREE allowed transitions
            valid_transitions = {
                Status.unavailable: [Status.requested],
                Status.requested: [Status.unavailable],
                Status.assigned: [Status.accepted],
            }

        allowed = valid_transitions.get(current_status, [])
        if new_status not in allowed:
            raise ValidationException(
                field="status",
                message=f"Invalid status transition: {current_status} -> {new_status}",
                details={
                    "current_status": current_status,
                    "new_status": new_status,
                    "is_ref_admin": is_ref_admin,
                },
            )
        return True

    async def add_status_history(
        self,
        assignment_id: str,
        new_status: Status,
        updated_by: str | None = None,
        updated_by_name: str | None = None,
        session: AsyncIOMotorClientSession | None = None,
    ) -> None:
        """Add status history entry to assignment"""
        status_entry = StatusHistory(
            status=new_status,
            updateDate=datetime.now().replace(microsecond=0),
            updatedBy=updated_by,
            updatedByName=updated_by_name,
        )

        await self.db["assignments"].update_one(
            {"_id": assignment_id},
            {"$push": {"statusHistory": jsonable_encoder(status_entry)}},
            session=session,
        )

    async def create_referee_object(self, user_id: str) -> Referee:
        """
        Create referee object from user data

        Args:
            user_id: User ID of the referee

        Returns:
            Referee object

        Raises:
            ResourceNotFoundException: If user not found or not a referee
        """
        ref_user = await self.db["users"].find_one({"_id": user_id})
        if not ref_user or "REFEREE" not in ref_user.get("roles", []):
            raise ResourceNotFoundException(
                resource_type="User",
                resource_id=user_id,
                details={"reason": "Referee not found or not a referee"},
            )

        club_info = ref_user.get("referee", {}).get("club", {})

        return Referee(
            userId=user_id,
            firstName=ref_user["firstName"],
            lastName=ref_user["lastName"],
            clubId=club_info.get("clubId"),
            clubName=club_info.get("clubName"),
            logoUrl=club_info.get("logoUrl"),
            points=ref_user.get("referee", {}).get("points", 0),
            level=ref_user.get("referee", {}).get("level", "n/a"),
        )

    async def set_referee_in_match(
        self,
        match_id: str,
        referee: dict,
        position: int,
        session: AsyncIOMotorClientSession | None = None,
    ) -> None:
        """Update match document with referee assignment"""
        if settings.DEBUG_LEVEL > 0:
            logger.debug(
                f"Setting referee in match - match_id: {match_id}, position: {position}, referee: {referee['firstName']} {referee['lastName']} ({referee['userId']})"
            )

        await self.db["matches"].update_one(
            {"_id": match_id},
            {
                "$set": {
                    f"referee{position}": {
                        "userId": referee["userId"],
                        "firstName": referee["firstName"],
                        "lastName": referee["lastName"],
                        "clubId": referee["clubId"],
                        "clubName": referee["clubName"],
                        "logoUrl": referee["logoUrl"],
                    }
                }
            },
            session=session,
        )

        if settings.DEBUG_LEVEL > 0:
            logger.debug(
                f"Referee set in match successfully - match_id: {match_id}, position: referee{position}"
            )

    async def remove_referee_from_match(
        self, match_id: str, position: int, session: AsyncIOMotorClientSession | None = None
    ) -> None:
        """Remove referee from match document"""
        await self.db["matches"].update_one(
            {"_id": match_id}, {"$set": {f"referee{position}": None}}, session=session
        )

    async def create_assignment(
        self,
        match_id: str,
        referee: Referee,
        status: Status,
        position: int | None = None,
        updated_by: str | None = None,
        updated_by_name: str | None = None,
        session: AsyncIOMotorClientSession | None = None,
    ) -> dict:
        """
        Create new assignment

        Args:
            match_id: Match ID
            referee: Referee object
            status: Initial status
            position: Optional position (1 or 2)
            updated_by: User ID who created the assignment
            updated_by_name: Name of user who created the assignment
            session: Optional database session for transactions

        Returns:
            Created assignment document
        """
        if settings.DEBUG_LEVEL > 0:
            logger.debug(
                f"Creating assignment - match_id: {match_id}, referee: {referee.firstName} {referee.lastName} ({referee.userId}), status: {status}, position: {position}"
            )

        # Create initial status history
        initial_status_history = [
            StatusHistory(
                status=status,
                updateDate=datetime.now().replace(microsecond=0),
                updatedBy=updated_by,
                updatedByName=updated_by_name,
            )
        ]

        assignment = AssignmentDB(
            matchId=match_id,
            referee=referee,
            status=status,
            position=position,
            statusHistory=initial_status_history,
        )

        insert_response = await self.db["assignments"].insert_one(
            jsonable_encoder(assignment), session=session
        )

        result = await self.db["assignments"].find_one(
            {"_id": insert_response.inserted_id}, session=session
        )
        created_assignment = dict(result) if result else {}

        logger.info(
            "Assignment created",
            extra={
                "assignment_id": str(insert_response.inserted_id),
                "match_id": match_id,
                "referee_id": referee.userId,
                "status": status,
            },
        )

        if settings.DEBUG_LEVEL > 0:
            logger.debug(
                f"Assignment created successfully - assignment_id: {insert_response.inserted_id}"
            )

        return created_assignment

    async def update_assignment(
        self,
        assignment_id: str,
        update_data: dict,
        updated_by: str | None = None,
        updated_by_name: str | None = None,
        session: AsyncIOMotorClientSession | None = None,
    ) -> dict | None:
        """
        Update assignment

        Args:
            assignment_id: Assignment ID
            update_data: Fields to update
            updated_by: User ID who updated the assignment
            updated_by_name: Name of user who updated the assignment
            session: Optional database session for transactions

        Returns:
            Updated assignment or None if no changes
        """
        result = await self.db["assignments"].update_one(
            {"_id": assignment_id}, {"$set": update_data}, session=session
        )

        if result.modified_count == 0:
            return None

        # Add status history if status changed
        if "status" in update_data:
            await self.add_status_history(
                assignment_id, update_data["status"], updated_by, updated_by_name, session
            )

        result = await self.db["assignments"].find_one({"_id": assignment_id}, session=session)
        updated_assignment = dict(result) if result else None

        logger.info(
            "Assignment updated",
            extra={
                "assignment_id": assignment_id,
                "updated_fields": list(update_data.keys()),
            },
        )

        return updated_assignment

    async def delete_assignment(
        self, assignment_id: str, session: AsyncIOMotorClientSession | None = None
    ) -> bool:
        """
        Delete assignment

        Args:
            assignment_id: Assignment ID
            session: Optional database session for transactions

        Returns:
            True if deleted, False otherwise
        """
        result = await self.db["assignments"].delete_one({"_id": assignment_id}, session=session)

        if result.deleted_count == 1:
            logger.info("Assignment deleted", extra={"assignment_id": assignment_id})
            return True
        return False

    async def check_assignment_exists(self, match_id: str, referee_id: str) -> bool:
        """Check if assignment already exists for match and referee"""
        existing = await self.db["assignments"].find_one(
            {"matchId": match_id, "referee.userId": referee_id}
        )
        return existing is not None

    async def get_match(self, match_id: str) -> dict:
        """
        Get match by ID

        Raises:
            ResourceNotFoundException: If match not found
        """
        match = await self.db["matches"].find_one({"_id": match_id})
        if not match:
            raise ResourceNotFoundException(resource_type="Match", resource_id=match_id)
        return dict(match)

    async def get_matches_by_day_range(
        self,
        start_date: date,
        end_date: date,
        filters: dict | None = None,
    ) -> list[dict]:
        """
        Fetch matches in a date range with aggregated refSummary counts.

        Uses a MongoDB aggregation pipeline to join with the assignments collection
        and compute refSummary (assignedCount, requestedCount, availableCount,
        requestsByLevel) in a single database pass.

        Args:
            start_date: Start of date range (inclusive)
            end_date: End of date range (inclusive); must be < 30 days after start
            filters: Optional additional MongoDB filter criteria

        Raises:
            ValidationException: If date range exceeds 30 days

        Returns:
            List of match dicts with refSummary aggregations
        """
        if (end_date - start_date).days >= 30:
            raise ValidationException(
                field="end_date",
                message="Date range must not exceed 30 days.",
                details={"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
            )

        start_dt = datetime(start_date.year, start_date.month, start_date.day, 0, 0, 0)
        end_dt = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59)

        date_filter: dict = {"startDate": {"$gte": start_dt, "$lte": end_dt}}
        if filters:
            date_filter.update(filters)

        total_active_referees = await self.db["users"].count_documents(
            {"roles": "REFEREE", "referee.active": True}
        )

        pipeline = [
            {"$match": date_filter},
            {
                "$lookup": {
                    "from": "assignments",
                    "localField": "_id",
                    "foreignField": "matchId",
                    "as": "_assignments",
                }
            },
            {
                "$addFields": {
                    "refSummary": {
                        "assignedCount": {
                            "$size": {
                                "$filter": {
                                    "input": "$_assignments",
                                    "as": "a",
                                    "cond": {
                                        "$in": ["$$a.status", ["ASSIGNED", "ACCEPTED"]]
                                    },
                                }
                            }
                        },
                        "requestedCount": {
                            "$size": {
                                "$filter": {
                                    "input": "$_assignments",
                                    "as": "a",
                                    "cond": {"$eq": ["$$a.status", "REQUESTED"]},
                                }
                            }
                        },
                        "availableCount": {
                            "$max": [
                                0,
                                {
                                    "$subtract": [
                                        total_active_referees,
                                        {"$size": "$_assignments"},
                                    ]
                                },
                            ]
                        },
                        "requestsByLevel": {
                            "$arrayToObject": {
                                "$map": {
                                    "input": {
                                        "$reduce": {
                                            "input": {
                                                "$filter": {
                                                    "input": "$_assignments",
                                                    "as": "a",
                                                    "cond": {"$eq": ["$$a.status", "REQUESTED"]},
                                                }
                                            },
                                            "initialValue": [],
                                            "in": {
                                                "$let": {
                                                    "vars": {
                                                        "lvl": {
                                                            "$ifNull": [
                                                                "$$this.referee.level",
                                                                "n/a",
                                                            ]
                                                        }
                                                    },
                                                    "in": {
                                                        "$cond": {
                                                            "if": {"$in": ["$$lvl", "$$value"]},
                                                            "then": "$$value",
                                                            "else": {"$concatArrays": ["$$value", ["$$lvl"]]},
                                                        }
                                                    },
                                                }
                                            },
                                        }
                                    },
                                    "as": "level",
                                    "in": {
                                        "k": "$$level",
                                        "v": {
                                            "$size": {
                                                "$filter": {
                                                    "input": "$_assignments",
                                                    "as": "a",
                                                    "cond": {
                                                        "$and": [
                                                            {"$eq": ["$$a.status", "REQUESTED"]},
                                                            {
                                                                "$eq": [
                                                                    {
                                                                        "$ifNull": [
                                                                            "$$a.referee.level",
                                                                            "n/a",
                                                                        ]
                                                                    },
                                                                    "$$level",
                                                                ]
                                                            },
                                                        ]
                                                    },
                                                }
                                            }
                                        },
                                    },
                                }
                            }
                        },
                    }
                }
            },
            {"$unset": "_assignments"},
        ]

        cursor = self.db["matches"].aggregate(pipeline)
        results = await cursor.to_list(length=None)
        return [dict(r) for r in results]

    async def get_referee_options_for_match(
        self,
        match_id: str,
        scope: str | None = None,
        level_filter: str | None = None,
    ) -> dict:
        """
        Return assigned, requested, and available referee lists for a match.

        Args:
            match_id: Match ID to fetch referee options for
            scope: Optional club-ID scope filter. When provided, only referees
                   belonging to that club (referee.club.clubId) are included
                   in the available list.
            level_filter: Optional referee level to filter active referees
                          (e.g. "S1", "S2").

        Returns:
            Dict with keys 'matchId', 'assigned', 'requested', 'available'

        Raises:
            ResourceNotFoundException: If match is not found
        """
        match = await self.db["matches"].find_one({"_id": match_id})
        if not match:
            raise ResourceNotFoundException(resource_type="Match", resource_id=match_id)

        assignments = await self.get_assignments_by_match(match_id)

        assignment_dict = {a["referee"]["userId"]: a for a in assignments}

        user_query: dict = {"roles": "REFEREE", "referee.active": True}
        if level_filter:
            user_query["referee.level"] = level_filter
        if scope:
            user_query["referee.club.clubId"] = scope

        active_referees = await self.db["users"].find(
            user_query, {"password": 0}
        ).to_list(length=None)

        assigned: list[dict] = []
        requested: list[dict] = []
        available: list[dict] = []

        for referee in active_referees:
            ref_id = referee["_id"]
            club_info = referee.get("referee", {}).get("club", {}) or {}
            ref_obj = {
                "userId": ref_id,
                "firstName": referee["firstName"],
                "lastName": referee["lastName"],
                "clubId": club_info.get("clubId"),
                "clubName": club_info.get("clubName"),
                "logoUrl": club_info.get("logoUrl"),
                "level": referee.get("referee", {}).get("level", "n/a"),
            }
            if ref_id in assignment_dict:
                a = assignment_dict[ref_id]
                status = a.get("status")
                entry = {
                    **ref_obj,
                    "_id": a.get("_id"),
                    "status": status,
                    "position": a.get("position"),
                }
                if status in ("ASSIGNED", "ACCEPTED"):
                    assigned.append(entry)
                elif status == "REQUESTED":
                    requested.append(entry)
            else:
                available.append(ref_obj)

        return {
            "matchId": match_id,
            "assigned": assigned,
            "requested": requested,
            "available": available,
        }

    async def get_day_summaries(
        self,
        start_date: date,
        days: int,
    ) -> list[dict]:
        """
        Return per-day totals for navigation tiles.

        For each day in the range [start_date, start_date + days - 1], returns:
          date, totalMatches, fullyAssigned, partiallyAssigned, unassigned

        A match is 'fullyAssigned' when both referee1 and referee2 are set,
        'partiallyAssigned' when exactly one is set, and 'unassigned' otherwise.

        Args:
            start_date: First day of range
            days: Number of days to include

        Returns:
            List of per-day summary dicts ordered by date
        """
        end_date = start_date + timedelta(days=days - 1)
        start_dt = datetime(start_date.year, start_date.month, start_date.day, 0, 0, 0)
        end_dt = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59)

        matches = await self.db["matches"].find(
            {"startDate": {"$gte": start_dt, "$lte": end_dt}}
        ).to_list(length=None)

        day_map: dict[str, dict] = {}
        for i in range(days):
            d = start_date + timedelta(days=i)
            day_key = d.isoformat()
            day_map[day_key] = {
                "date": day_key,
                "totalMatches": 0,
                "fullyAssigned": 0,
                "partiallyAssigned": 0,
                "unassigned": 0,
            }

        for match in matches:
            match_date = match.get("startDate")
            if not match_date:
                continue
            if isinstance(match_date, datetime):
                day_key = match_date.date().isoformat()
            else:
                day_key = str(match_date)[:10]

            if day_key not in day_map:
                continue

            day_map[day_key]["totalMatches"] += 1

            ref1 = match.get("referee1")
            ref2 = match.get("referee2")
            assigned_count = (1 if ref1 else 0) + (1 if ref2 else 0)

            if assigned_count == 2:
                day_map[day_key]["fullyAssigned"] += 1
            elif assigned_count == 1:
                day_map[day_key]["partiallyAssigned"] += 1
            else:
                day_map[day_key]["unassigned"] += 1

        return list(day_map.values())
