"""Unit tests for MessageService"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from exceptions import ResourceNotFoundException
from services.message_service import MessageService


@pytest.fixture
def mock_db():
    """Mock MongoDB database"""
    db = MagicMock()

    mock_users_collection = MagicMock()
    mock_users_collection.find_one = AsyncMock()

    mock_messages_collection = MagicMock()
    mock_messages_collection.insert_one = AsyncMock()

    db._users_collection = mock_users_collection
    db._messages_collection = mock_messages_collection

    db.__getitem__ = MagicMock(
        side_effect=lambda name: {
            "users": mock_users_collection,
            "messages": mock_messages_collection,
        }.get(name)
    )

    return db


@pytest.fixture
def message_service(mock_db):
    """MessageService instance with mocked database"""
    return MessageService(mock_db)


class TestSendRefereeNotification:
    """Test referee notification sending"""

    @pytest.mark.asyncio
    async def test_send_notification_success(self, message_service, mock_db):
        """Test successful notification send"""
        test_referee = {
            "_id": "referee-123",
            "firstName": "John",
            "lastName": "Doe",
            "email": "john@example.com",
        }

        test_match = {
            "tournament": {"name": "Test League"},
            "home": {"fullName": "Team A"},
            "away": {"fullName": "Team B"},
            "startDate": datetime(2024, 1, 15, 18, 0),
            "venue": {"name": "Test Arena"},
        }

        mock_db._users_collection.find_one = AsyncMock(return_value=test_referee)

        with patch("services.message_service.send_email", new_callable=AsyncMock) as mock_email:
            result = await message_service.send_referee_notification(
                referee_id="referee-123",
                match=test_match,
                content="You have been assigned",
                sender_id="sender-123",
                sender_name="Admin User",
            )

        assert result["receiver"]["userId"] == "referee-123"
        assert result["receiver"]["firstName"] == "John"
        assert result["sender"]["userId"] == "sender-123"
        assert "You have been assigned" in result["content"]
        assert result["read"] is False

        mock_db._messages_collection.insert_one.assert_called_once()
        mock_email.assert_called_once()
        call_args = mock_email.call_args[1]
        assert call_args["recipients"] == ["john@example.com"]
        assert "You have been assigned" in call_args["body"]

    @pytest.mark.asyncio
    async def test_send_notification_referee_not_found(self, message_service, mock_db):
        """Test error when referee not found"""
        mock_db._users_collection.find_one = AsyncMock(return_value=None)

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await message_service.send_referee_notification(
                referee_id="invalid-id",
                match={},
                content="Test",
                sender_id="sender-123",
                sender_name="Admin",
            )

        assert "User" in str(exc_info.value)
        assert "invalid-id" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_send_notification_with_footer(self, message_service, mock_db):
        """Test notification with footer"""
        test_referee = {
            "_id": "referee-123",
            "firstName": "John",
            "lastName": "Doe",
            "email": "john@example.com",
        }

        test_match = {
            "tournament": {"name": "Test League"},
            "home": {"fullName": "Team A"},
            "away": {"fullName": "Team B"},
            "startDate": datetime(2024, 1, 15, 18, 0),
            "venue": {"name": "Test Arena"},
        }

        mock_db._users_collection.find_one = AsyncMock(return_value=test_referee)

        with patch("services.message_service.send_email", new_callable=AsyncMock):
            result = await message_service.send_referee_notification(
                referee_id="referee-123",
                match=test_match,
                content="You have been assigned",
                sender_id="sender-123",
                sender_name="Admin User",
                footer="Please confirm",
            )

        assert "Please confirm" in result["content"]

    @pytest.mark.asyncio
    async def test_send_notification_no_email_skips_send(self, message_service, mock_db):
        """Test email is skipped when referee has no email address"""
        test_referee = {
            "_id": "referee-123",
            "firstName": "John",
            "lastName": "Doe",
        }

        mock_db._users_collection.find_one = AsyncMock(return_value=test_referee)

        with patch("services.message_service.send_email", new_callable=AsyncMock) as mock_email:
            await message_service.send_referee_notification(
                referee_id="referee-123",
                match={},
                content="Test",
                sender_id="sender-123",
                sender_name="Admin",
            )

        mock_email.assert_not_called()


class TestFormatMatchNotification:
    """Test match notification formatting"""

    def test_format_match_with_all_data(self, message_service):
        """Test formatting with complete match data"""
        match = {
            "tournament": {"name": "Test League"},
            "home": {"fullName": "Team A"},
            "away": {"fullName": "Team B"},
            "startDate": datetime(2024, 1, 15, 18, 30),  # Monday
            "venue": {"name": "Test Arena"},
        }

        result = message_service.format_match_notification(match)

        assert "Test League" in result
        assert "Team A - Team B" in result
        assert "Mo, 15.01.2024, 18:30 Uhr" in result
        assert "Test Arena" in result

    def test_format_match_without_date(self, message_service):
        """Test formatting when date is missing"""
        match = {
            "tournament": {"name": "Test League"},
            "home": {"fullName": "Team A"},
            "away": {"fullName": "Team B"},
            "startDate": None,
            "venue": {"name": "Test Arena"},
        }

        result = message_service.format_match_notification(match)

        assert "TBD" in result
        assert "Test League" in result


class TestEmailNotification:
    """Test email notification via send_referee_notification"""

    @pytest.mark.asyncio
    async def test_email_sent_when_mail_enabled(self, message_service, mock_db):
        """Test email is sent when MAIL_ENABLED is True (default)"""
        referee = {
            "_id": "referee-123",
            "firstName": "John",
            "lastName": "Doe",
            "email": "john@example.com",
        }
        mock_db._users_collection.find_one = AsyncMock(return_value=referee)

        with patch(
            "services.message_service.send_email", new_callable=AsyncMock
        ) as mock_send_email:
            await message_service.send_referee_notification(
                referee_id="referee-123",
                match={},
                content="Test content",
                sender_id="sender-123",
                sender_name="Admin",
            )

            mock_send_email.assert_called_once()
            call_args = mock_send_email.call_args[1]
            assert call_args["recipients"] == ["john@example.com"]
            assert "Test content" in call_args["body"]

    @pytest.mark.asyncio
    async def test_email_skipped_when_no_email(self, message_service, mock_db):
        """Test email is skipped when referee has no email address"""
        referee = {"_id": "referee-123", "firstName": "John", "lastName": "Doe"}
        mock_db._users_collection.find_one = AsyncMock(return_value=referee)

        with patch(
            "services.message_service.send_email", new_callable=AsyncMock
        ) as mock_send_email:
            await message_service.send_referee_notification(
                referee_id="referee-123",
                match={},
                content="Test content",
                sender_id="sender-123",
                sender_name="Admin",
            )

            mock_send_email.assert_not_called()
