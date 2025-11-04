
"""Unit tests for MessageService"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from services.message_service import MessageService
from exceptions import ResourceNotFoundException, DatabaseOperationException


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
    
    db.__getitem__ = MagicMock(side_effect=lambda name: {
        'users': mock_users_collection,
        'messages': mock_messages_collection
    }.get(name))
    
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
            "email": "john@example.com"
        }
        
        test_match = {
            "tournament": {"name": "Test League"},
            "home": {"fullName": "Team A"},
            "away": {"fullName": "Team B"},
            "startDate": datetime(2024, 1, 15, 18, 0),
            "venue": {"name": "Test Arena"}
        }
        
        mock_db._users_collection.find_one = AsyncMock(return_value=test_referee)
        
        with patch.object(message_service, '_send_email_notification', new_callable=AsyncMock) as mock_email:
            result = await message_service.send_referee_notification(
                referee_id="referee-123",
                match=test_match,
                content="You have been assigned",
                sender_id="sender-123",
                sender_name="Admin User"
            )
        
        # Verify message was created
        assert result["receiver"]["userId"] == "referee-123"
        assert result["receiver"]["firstName"] == "John"
        assert result["sender"]["userId"] == "sender-123"
        assert "You have been assigned" in result["content"]
        assert result["read"] is False
        
        # Verify insert was called
        mock_db._messages_collection.insert_one.assert_called_once()
        
        # Verify email was attempted
        mock_email.assert_called_once()
    
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
                sender_name="Admin"
            )
        
        assert exc_info.value.resource_type == "User"
        assert exc_info.value.resource_id == "invalid-id"
    
    @pytest.mark.asyncio
    async def test_send_notification_with_footer(self, message_service, mock_db):
        """Test notification with footer"""
        test_referee = {
            "_id": "referee-123",
            "firstName": "John",
            "lastName": "Doe",
            "email": "john@example.com"
        }
        
        test_match = {
            "tournament": {"name": "Test League"},
            "home": {"fullName": "Team A"},
            "away": {"fullName": "Team B"},
            "startDate": datetime(2024, 1, 15, 18, 0),
            "venue": {"name": "Test Arena"}
        }
        
        mock_db._users_collection.find_one = AsyncMock(return_value=test_referee)
        
        with patch.object(message_service, '_send_email_notification', new_callable=AsyncMock):
            result = await message_service.send_referee_notification(
                referee_id="referee-123",
                match=test_match,
                content="You have been assigned",
                sender_id="sender-123",
                sender_name="Admin User",
                footer="Please confirm"
            )
        
        assert "Please confirm" in result["content"]


class TestFormatMatchNotification:
    """Test match notification formatting"""
    
    def test_format_match_with_all_data(self, message_service):
        """Test formatting with complete match data"""
        match = {
            "tournament": {"name": "Test League"},
            "home": {"fullName": "Team A"},
            "away": {"fullName": "Team B"},
            "startDate": datetime(2024, 1, 15, 18, 30),  # Monday
            "venue": {"name": "Test Arena"}
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
            "venue": {"name": "Test Arena"}
        }
        
        result = message_service.format_match_notification(match)
        
        assert "TBD" in result
        assert "Test League" in result


class TestEmailNotification:
    """Test email notification helper"""
    
    @pytest.mark.asyncio
    async def test_email_sent_in_production(self, message_service):
        """Test email is sent in production environment"""
        referee = {
            "_id": "referee-123",
            "email": "john@example.com"
        }
        
        with patch('services.message_service.settings') as mock_settings:
            with patch('services.message_service.send_email', new_callable=AsyncMock) as mock_send_email:
                mock_settings.ENVIRONMENT = "production"
                
                await message_service._send_email_notification(referee, "Test content")
                
                mock_send_email.assert_called_once()
                call_args = mock_send_email.call_args[1]
                assert call_args["recipients"] == ["john@example.com"]
                assert "Test content" in call_args["body"]
    
    @pytest.mark.asyncio
    async def test_email_skipped_in_dev(self, message_service):
        """Test email is skipped in development"""
        referee = {
            "_id": "referee-123",
            "email": "john@example.com"
        }
        
        with patch('services.message_service.settings') as mock_settings:
            with patch('services.message_service.send_email', new_callable=AsyncMock) as mock_send_email:
                mock_settings.ENVIRONMENT = "development"
                
                await message_service._send_email_notification(referee, "Test content")
                
                mock_send_email.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_email_skipped_when_no_email(self, message_service):
        """Test handling when referee has no email"""
        referee = {
            "_id": "referee-123"
            # No email field
        }
        
        with patch('services.message_service.send_email', new_callable=AsyncMock) as mock_send_email:
            await message_service._send_email_notification(referee, "Test content")
            
            mock_send_email.assert_not_called()
