"""
Logging configuration using Loguru.
"""

import sys
from pathlib import Path
from loguru import logger

from src.config import get_config


def setup_logger():
    """Configure the logger with file and console output."""
    # Remove default handler
    logger.remove()
    
    # Load config
    config = get_config()
    log_config = config.logging
    
    # Create logs directory
    log_dir = Path(log_config.directory)
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Add console handler with colors
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=config.app.log_level,
        colorize=True
    )
    
    # Add file handler with rotation
    log_file = log_dir / log_config.file_name.replace("{date}", "{time:YYYY-MM-DD}")
    logger.add(
        str(log_file),
        format=log_config.format,
        level=config.app.log_level,
        rotation=log_config.rotation,
        retention=log_config.retention,
        compression="zip"
    )
    
    logger.info("Logger initialized")
    return logger

