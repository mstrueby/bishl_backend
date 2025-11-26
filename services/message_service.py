
"""
Message Service - Direct database operations for messages
Replaces HTTP calls to internal message API endpoints
"""
from datetime import datetime

from bson import ObjectId

from config import settings
from exceptions import DatabaseOperationException, ResourceNotFoundException
from logging_config import logger
from mail_service import send_email
from services.performance_monitor import monitor_query


class MessageService:
    """Service for message-related operations without HTTP overhead"""

    def __init__(self, mongodb):
        self.db = mongodb

    @monitor_query("send_referee_notification")
    async def send_referee_notification(
        self,
        referee_id: str,
        match: dict,
        content: str,
        sender_id: str,
        sender_name: str,
        footer: str | None = None
    ) -> dict:
        """
        Send notification to referee directly in database.
        Replaces: POST /messages/

        Args:
            referee_id: User ID of referee
            match: Match document
            content: Message content
            sender_id: User ID of sender
            sender_name: Full name of sender
            footer: Optional footer text

        Returns:
            Created message document

        Raises:
            ResourceNotFoundException: If referee not found
            DatabaseOperationException: If message creation fails
        """
        logger.info(
            "Sending referee notification",
            extra={"referee_id": referee_id, "sender_id": sender_id}
        )

        # Get referee user
        referee = await self.db["users"].find_one({"_id": referee_id})
        if not referee:
            raise ResourceNotFoundException(
                resource_type="User",
                resource_id=referee_id
            )

        # Format match text
        match_text = self.format_match_notification(match)

        # Build full content
        full_content = f"{content}\n\n{match_text}"
        if footer:
            full_content += f"\n\n{footer}"

        # Create message document
        message = {
            "_id": str(ObjectId()),
            "sender": {
                "userId": sender_id,
                "firstName": sender_name.split()[0] if sender_name else "",
                "lastName": " ".join(sender_name.split()[1:]) if sender_name else ""
            },
            "receiver": {
                "userId": referee_id,
                "firstName": referee.get("firstName", ""),
                "lastName": referee.get("lastName", "")
            },
            "content": full_content,
            "timestamp": datetime.now().replace(microsecond=0),
            "read": False
        }

        # Insert message
        try:
            await self.db["messages"].insert_one(message)
        except Exception as e:
            raise DatabaseOperationException(
                operation="insert_message",
                collection="messages",
                details={"error": str(e), "referee_id": referee_id}
            ) from e

        # Send email notification
        await self._send_email_notification(referee, full_content)

        return message

    def format_match_notification(self, match: dict) -> str:
        """
        Format match details for notification message.

        Args:
            match: Match document

        Returns:
            Formatted match text
        """
        weekdays_german = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
        start_date = match.get("startDate")

        if start_date:
            weekday_abbr = weekdays_german[start_date.weekday()]
            date_str = start_date.strftime("%d.%m.%Y")
            time_str = start_date.strftime("%H:%M")
        else:
            weekday_abbr = "TBD"
            date_str = "TBD"
            time_str = "TBD"

        tournament_name = match.get("tournament", {}).get("name", "Unknown Tournament")
        home_name = match.get("home", {}).get("fullName", "Unknown Team")
        away_name = match.get("away", {}).get("fullName", "Unknown Team")
        venue_name = match.get("venue", {}).get("name", "Unknown Venue")

        return (
            f"{tournament_name}\n"
            f"{home_name} - {away_name}\n"
            f"{weekday_abbr}, {date_str}, {time_str} Uhr\n"
            f"{venue_name}"
        )

    async def _send_email_notification(self, referee: dict, content: str) -> None:
        """
        Send email notification to referee.

        Args:
            referee: Referee user document
            content: Email content
        """
        referee_email = referee.get("email")

        if not referee_email:
            logger.warning(
                "Referee has no email address",
                extra={"referee_id": referee.get("_id")}
            )
            return

        try:
            if settings.ENVIRONMENT == "production":
                email_subject = "BISHL - Schiedsrichter-Information"
                email_content = f"<p>{content.replace('\n', '<br>')}</p>"

                await send_email(
                    subject=email_subject,
                    recipients=[referee_email],
                    body=email_content
                )

                logger.info(
                    "Email sent to referee",
                    extra={"referee_id": referee.get("_id"), "email": referee_email}
                )
            else:
                logger.info(
                    f"Non-production mode ({settings.ENVIRONMENT}): Skipping email to {referee_email}"
                )
        except Exception as e:
            logger.error(
                "Failed to send email to referee",
                extra={"referee_id": referee.get("_id"), "error": str(e)}
            )
