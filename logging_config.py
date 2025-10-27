
"""
Logging Configuration for BISHL Backend

Configures loguru for structured logging with:
- Console output with colors (DEBUG level if DEBUG_LEVEL > 0)
- Error log file with rotation
- Debug log file (only if DEBUG_LEVEL > 0)
"""

import os
import sys

from loguru import logger

DEBUG_LEVEL = int(os.environ.get('DEBUG_LEVEL', 0))

# Remove default handler
logger.remove()

# Add console handler with formatting
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="DEBUG" if DEBUG_LEVEL > 0 else "INFO",
    colorize=True
)

# Create logs directory if it doesn't exist
os.makedirs("logs", exist_ok=True)

# Add file handler for errors
logger.add(
    "logs/errors.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    level="ERROR",
    rotation="10 MB",
    retention="30 days",
    compression="zip"
)

# Add file handler for all logs (if debug mode)
if DEBUG_LEVEL > 0:
    logger.add(
        "logs/debug.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG",
        rotation="50 MB",
        retention="7 days",
        compression="zip"
    )

# Export configured logger
__all__ = ['logger']
