"""Unit tests for AssignmentService"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from bson import ObjectId

from services.assignment_service import AssignmentService
from models.assignments import Status, Referee
from exceptions import (
    ResourceNotFoundException,
    ValidationException,
    DatabaseOperationException,
    AuthorizationException
)


@pytest.fixture
def mock_db():
    """Mock MongoDB database"""
    db = MagicMock()

    mock_assignments_collection = MagicMock()
    mock_assignments_collection.find_one = AsyncMock()
    mock_assignments_collection.insert_one = AsyncMock()
    mock_assignments_collection.update_one = AsyncMock()
    mock_assignments_collection.delete_one = AsyncMock()

    mock_assignments_find = MagicMock()
    mock_assignments_find.to_list = AsyncMock()
    mock_assignments_collection.find = MagicMock(return_value=mock_assignments_find)

    mock_users_collection = MagicMock()
    mock_users_collection.find_one = AsyncMock()

    mock_matches_collection = MagicMock()
    mock_matches_collection.find_one = AsyncMock()
    mock_matches_collection.update_one = AsyncMock()

    db._assignments_collection = mock_assignments_collection
    db._assignments_find = mock_assignments_find
    db._users_collection = mock_users_collection
    db._matches_collection = mock_matches_collection

    db.__getitem__ = MagicMock(side_effect=lambda name: {
        'assignments': mock_assignments_collection,
        'users': mock_users_collection,
        'matches': mock_matches_collection
    }.get(name))

    return db


@pytest.fixture
def assignment_service(mock_db):
    """AssignmentService instance with mocked database"""
    return AssignmentService(mock_db)


class TestGetAssignmentById:
    """Test getting assignment by ID"""

    @pytest.mark.asyncio
    async def test_get_assignment_success(self, assignment_service, mock_db):
        """Test successful assignment retrieval"""
        test_assignment = {
            "_id": "assign-123",
            "matchId": "match-456",
            "referee": {"userId": "ref-789"},
            "status": "ASSIGNED"
        }

        mock_db._assignments_collection.find_one = AsyncMock(return_value=test_assignment)

        result = await assignment_service.get_assignment_by_id("assign-123")

        assert result == test_assignment
        mock_db._assignments_collection.find_one.assert_called_once_with({"_id": "assign-123"})

    @pytest.mark.asyncio
    async def test_get_assignment_not_found(self, assignment_service, mock_db):
        """Test when assignment doesn't exist"""
        mock_db._assignments_collection.find_one = AsyncMock(return_value=None)

        result = await assignment_service.get_assignment_by_id("invalid-id")

        assert result is None


class TestGetAssignmentsByMatch:
    """Test getting assignments by match"""

    @pytest.mark.asyncio
    async def test_get_assignments_success(self, assignment_service, mock_db):
        """Test successful retrieval of match assignments"""
        test_assignments = [
            {"_id": "assign-1", "matchId": "match-123", "status": "ASSIGNED"},
            {"_id": "assign-2", "matchId": "match-123", "status": "REQUESTED"}
        ]

        mock_db._assignments_find.to_list = AsyncMock(return_value=test_assignments)

        result = await assignment_service.get_assignments_by_match("match-123")

        assert len(result) == 2
        assert result == test_assignments
        mock_db._assignments_collection.find.assert_called_once_with({"matchId": "match-123"})

    @pytest.mark.asyncio
    async def test_get_assignments_empty(self, assignment_service, mock_db):
        """Test when no assignments exist for match"""
        mock_db._assignments_find.to_list = AsyncMock(return_value=[])

        result = await assignment_service.get_assignments_by_match("match-123")

        assert result == []


class TestGetAssignmentsByReferee:
    """Test getting assignments by referee"""

    @pytest.mark.asyncio
    async def test_get_referee_assignments(self, assignment_service, mock_db):
        """Test successful retrieval of referee assignments"""
        test_assignments = [
            {"_id": "assign-1", "referee": {"userId": "ref-123"}},
            {"_id": "assign-2", "referee": {"userId": "ref-123"}}
        ]

        mock_db._assignments_find.to_list = AsyncMock(return_value=test_assignments)

        result = await assignment_service.get_assignments_by_referee("ref-123")

        assert len(result) == 2
        mock_db._assignments_collection.find.assert_called_once_with({"referee.userId": "ref-123"})


class TestValidateStatusTransition:
    """Test status transition validation"""

    @pytest.mark.asyncio
    async def test_ref_admin_valid_transitions(self, assignment_service):
        """Test valid transitions for REF_ADMIN"""
        # Test requested -> assigned
        result = await assignment_service.validate_assignment_status_transition(
            Status.requested, Status.assigned, is_ref_admin=True
        )
        assert result is True

        # Test assigned -> unavailable
        result = await assignment_service.validate_assignment_status_transition(
            Status.assigned, Status.unavailable, is_ref_admin=True
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_referee_valid_transitions(self, assignment_service):
        """Test valid transitions for REFEREE"""
        # Test unavailable -> requested
        result = await assignment_service.validate_assignment_status_transition(
            Status.unavailable, Status.requested, is_ref_admin=False
        )
        assert result is True

        # Test assigned -> accepted
        result = await assignment_service.validate_assignment_status_transition(
            Status.assigned, Status.accepted, is_ref_admin=False
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_invalid_transition(self, assignment_service):
        """Test invalid status transition"""
        with pytest.raises(ValidationException) as exc_info:
            await assignment_service.validate_assignment_status_transition(
                Status.accepted, Status.requested, is_ref_admin=False
            )

        assert "Invalid status transition" in str(exc_info.value)


class TestCreateRefereeObject:
    """Test referee object creation from user data"""

    @pytest.mark.asyncio
    async def test_create_referee_success(self, assignment_service, mock_db):
        """Test successful referee object creation"""
        test_user = {
            "_id": "user-123",
            "firstName": "John",
            "lastName": "Doe",
            "roles": ["REFEREE"],
            "referee": {
                "club": {
                    "clubId": "club-456",
                    "clubName": "Test Club",
                    "logoUrl": "http://logo.url"
                },
                "points": 100,
                "level": "S2"
            }
        }

        mock_db._users_collection.find_one = AsyncMock(return_value=test_user)

        result = await assignment_service.create_referee_object("user-123")

        assert isinstance(result, Referee)
        assert result.userId == "user-123"
        assert result.firstName == "John"
        assert result.lastName == "Doe"
        assert result.clubId == "club-456"
        assert result.points == 100
        assert result.level == "S2"

    @pytest.mark.asyncio
    async def test_create_referee_user_not_found(self, assignment_service, mock_db):
        """Test when user doesn't exist"""
        mock_db._users_collection.find_one = AsyncMock(return_value=None)

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await assignment_service.create_referee_object("invalid-id")

        assert "User with ID 'invalid-id' not found" in str(exc_info.value)
        assert exc_info.value.details.get("reason") == "Referee not found or not a referee"

    @pytest.mark.asyncio
    async def test_create_referee_not_referee_role(self, assignment_service, mock_db):
        """Test when user doesn't have REFEREE role"""
        test_user = {
            "_id": "user-123",
            "firstName": "John",
            "lastName": "Doe",
            "roles": ["USER"]
        }

        mock_db._users_collection.find_one = AsyncMock(return_value=test_user)

        with pytest.raises(ResourceNotFoundException):
            await assignment_service.create_referee_object("user-123")


class TestSetRefereeInMatch:
    """Test updating match with referee assignment"""

    @pytest.mark.asyncio
    async def test_set_referee_position_1(self, assignment_service, mock_db):
        """Test setting referee in position 1"""
        referee_data = {
            "userId": "ref-123",
            "firstName": "John",
            "lastName": "Doe",
            "clubId": "club-456",
            "clubName": "Test Club",
            "logoUrl": "http://logo.url"
        }

        await assignment_service.set_referee_in_match("match-123", referee_data, 1)

        mock_db._matches_collection.update_one.assert_called_once()
        call_args = mock_db._matches_collection.update_one.call_args[0]
        assert call_args[0] == {"_id": "match-123"}
        assert "referee1" in call_args[1]["$set"]

    @pytest.mark.asyncio
    async def test_set_referee_position_2(self, assignment_service, mock_db):
        """Test setting referee in position 2"""
        referee_data = {
            "userId": "ref-456",
            "firstName": "Jane",
            "lastName": "Smith",
            "clubId": None,
            "clubName": None,
            "logoUrl": None
        }

        await assignment_service.set_referee_in_match("match-123", referee_data, 2)

        call_args = mock_db._matches_collection.update_one.call_args[0]
        assert "referee2" in call_args[1]["$set"]


class TestRemoveRefereeFromMatch:
    """Test removing referee from match"""

    @pytest.mark.asyncio
    async def test_remove_referee(self, assignment_service, mock_db):
        """Test removing referee from match"""
        await assignment_service.remove_referee_from_match("match-123", 1)

        mock_db._matches_collection.update_one.assert_called_once()
        call_args = mock_db._matches_collection.update_one.call_args[0]
        assert call_args[0] == {"_id": "match-123"}
        assert call_args[1]["$set"]["referee1"] is None


class TestCreateAssignment:
    """Test assignment creation"""

    @pytest.mark.asyncio
    async def test_create_assignment_success(self, assignment_service, mock_db):
        """Test successful assignment creation"""
        referee = Referee(
            userId="ref-123",
            firstName="John",
            lastName="Doe",
            clubId="club-456",
            clubName="Test Club",
            logoUrl=None,
            points=100,
            level="S2"
        )

        mock_insert_result = MagicMock()
        mock_insert_result.inserted_id = "assign-new"
        mock_db._assignments_collection.insert_one = AsyncMock(return_value=mock_insert_result)

        created_assignment = {
            "_id": "assign-new",
            "matchId": "match-123",
            "referee": referee.model_dump(),
            "status": "REQUESTED"
        }
        mock_db._assignments_collection.find_one = AsyncMock(return_value=created_assignment)

        result = await assignment_service.create_assignment(
            match_id="match-123",
            referee=referee,
            status=Status.requested,
            position=None,
            updated_by="admin-123",
            updated_by_name="Admin User"
        )

        assert result["_id"] == "assign-new"
        assert result["matchId"] == "match-123"
        assert result["status"] == "REQUESTED"
        mock_db._assignments_collection.insert_one.assert_called_once()


class TestUpdateAssignment:
    """Test assignment updates"""

    @pytest.mark.asyncio
    async def test_update_assignment_success(self, assignment_service, mock_db):
        """Test successful assignment update"""
        update_data = {"status": "ACCEPTED"}

        mock_result = MagicMock()
        mock_result.modified_count = 1
        mock_db._assignments_collection.update_one = AsyncMock(return_value=mock_result)

        updated_assignment = {
            "_id": "assign-123",
            "status": "ACCEPTED"
        }
        mock_db._assignments_collection.find_one = AsyncMock(return_value=updated_assignment)

        result = await assignment_service.update_assignment(
            "assign-123",
            update_data,
            updated_by="ref-456",
            updated_by_name="John Referee"
        )

        assert result["status"] == "ACCEPTED"
        # Should be called twice: once for update, once for status history
        assert mock_db._assignments_collection.update_one.call_count == 2

    @pytest.mark.asyncio
    async def test_update_assignment_no_changes(self, assignment_service, mock_db):
        """Test when no changes are made"""
        mock_result = MagicMock()
        mock_result.modified_count = 0
        mock_db._assignments_collection.update_one = AsyncMock(return_value=mock_result)

        result = await assignment_service.update_assignment(
            "assign-123",
            {"status": "REQUESTED"}
        )

        assert result is None


class TestDeleteAssignment:
    """Test assignment deletion"""

    @pytest.mark.asyncio
    async def test_delete_assignment_success(self, assignment_service, mock_db):
        """Test successful deletion"""
        mock_result = MagicMock()
        mock_result.deleted_count = 1
        mock_db._assignments_collection.delete_one = AsyncMock(return_value=mock_result)

        result = await assignment_service.delete_assignment("assign-123")

        assert result is True
        mock_db._assignments_collection.delete_one.assert_called_once_with(
            {"_id": "assign-123"}, 
            session=None
        )

    @pytest.mark.asyncio
    async def test_delete_assignment_not_found(self, assignment_service, mock_db):
        """Test deletion when assignment doesn't exist"""
        mock_result = MagicMock()
        mock_result.deleted_count = 0
        mock_db._assignments_collection.delete_one = AsyncMock(return_value=mock_result)

        result = await assignment_service.delete_assignment("invalid-id")

        assert result is False


class TestCheckAssignmentExists:
    """Test checking if assignment exists"""

    @pytest.mark.asyncio
    async def test_assignment_exists(self, assignment_service, mock_db):
        """Test when assignment exists"""
        mock_db._assignments_collection.find_one = AsyncMock(
            return_value={"_id": "assign-123"}
        )

        result = await assignment_service.check_assignment_exists("match-123", "ref-456")

        assert result is True
        mock_db._assignments_collection.find_one.assert_called_once_with({
            "matchId": "match-123",
            "referee.userId": "ref-456"
        })

    @pytest.mark.asyncio
    async def test_assignment_does_not_exist(self, assignment_service, mock_db):
        """Test when assignment doesn't exist"""
        mock_db._assignments_collection.find_one = AsyncMock(return_value=None)

        result = await assignment_service.check_assignment_exists("match-123", "ref-456")

        assert result is False


class TestGetMatch:
    """Test getting match by ID"""

    @pytest.mark.asyncio
    async def test_get_match_success(self, assignment_service, mock_db):
        """Test successful match retrieval"""
        test_match = {
            "_id": "match-123",
            "home": {"fullName": "Team A"},
            "away": {"fullName": "Team B"}
        }

        mock_db._matches_collection.find_one = AsyncMock(return_value=test_match)

        result = await assignment_service.get_match("match-123")

        assert result == test_match

    @pytest.mark.asyncio
    async def test_get_match_not_found(self, assignment_service, mock_db):
        """Test when match doesn't exist"""
        mock_db._matches_collection.find_one = AsyncMock(return_value=None)

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await assignment_service.get_match("invalid-id")

        assert "Match" in str(exc_info.value)
        assert "invalid-id" in str(exc_info.value)


class TestAddStatusHistory:
    """Test adding status history entries"""

    @pytest.mark.asyncio
    async def test_add_status_history(self, assignment_service, mock_db):
        """Test adding status history entry"""
        await assignment_service.add_status_history(
            assignment_id="assign-123",
            new_status=Status.accepted,
            updated_by="ref-456",
            updated_by_name="John Referee"
        )

        mock_db._assignments_collection.update_one.assert_called_once()
        call_args = mock_db._assignments_collection.update_one.call_args[0]
        assert call_args[0] == {"_id": "assign-123"}
        assert "$push" in call_args[1]
        assert "statusHistory" in call_args[1]["$push"]