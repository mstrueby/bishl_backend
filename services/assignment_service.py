
"""
Assignment Service - Business logic for referee assignment management

Handles assignment creation, updates, validation, and synchronization with matches.
"""

from datetime import datetime
from typing import Any

from fastapi.encoders import jsonable_encoder
from motor.motor_asyncio import AsyncIOMotorClientSession

from exceptions import (
    AuthorizationException,
    DatabaseOperationException,
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
        return await self.db["assignments"].find_one({"_id": assignment_id})

    async def get_assignments_by_match(self, match_id: str) -> list[dict]:
        """Get all assignments for a match"""
        return await self.db["assignments"].find({"matchId": match_id}).to_list(length=None)

    async def get_assignments_by_referee(self, referee_id: str) -> list[dict]:
        """Get all assignments for a referee"""
        return await self.db["assignments"].find({"referee.userId": referee_id}).to_list(length=None)

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
        
        created_assignment = await self.db["assignments"].find_one(
            {"_id": insert_response.inserted_id}, session=session
        )
        
        logger.info(
            "Assignment created",
            extra={
                "assignment_id": str(insert_response.inserted_id),
                "match_id": match_id,
                "referee_id": referee.userId,
                "status": status,
            },
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

        updated_assignment = await self.db["assignments"].find_one(
            {"_id": assignment_id}, session=session
        )
        
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
        return match
