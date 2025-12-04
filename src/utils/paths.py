"""
Path utilities for handling bundled executable paths.
Handles both development and PyInstaller bundled modes.
"""

import sys
import os
from pathlib import Path
from typing import Optional


def is_bundled() -> bool:
    """Check if running as a PyInstaller bundle."""
    return getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')


def get_base_path() -> Path:
    """
    Get the base path for the application.
    
    Returns:
        - When bundled: The temporary extraction directory (_MEIPASS)
        - When development: The project root directory
    """
    if is_bundled():
        return Path(sys._MEIPASS)
    else:
        # Development mode - go up from src/utils to project root
        return Path(__file__).parent.parent.parent


def get_resource_path(relative_path: str) -> Path:
    """
    Get the absolute path to a resource file.
    
    Args:
        relative_path: Path relative to project root (e.g., "config/config.yaml")
        
    Returns:
        Absolute path to the resource
    """
    return get_base_path() / relative_path


def get_playwright_browsers_path() -> Optional[Path]:
    """
    Get the path to Playwright browsers.
    
    Returns:
        Path to browsers directory, or None if not found
    """
    if is_bundled():
        # When bundled, browsers are in the extracted directory
        bundled_path = get_base_path() / "browsers"
        if bundled_path.exists():
            return bundled_path
    
    # Check environment variable
    env_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if env_path and Path(env_path).exists():
        return Path(env_path)
    
    # Check common locations
    possible_paths = [
        Path.home() / ".cache" / "ms-playwright",  # Linux
        Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright",  # Windows
        Path.home() / "Library" / "Caches" / "ms-playwright",  # macOS
    ]
    
    for path in possible_paths:
        if path.exists():
            return path
    
    return None


def setup_bundled_environment():
    """
    Setup environment variables for bundled mode.
    Call this at application startup.
    """
    if is_bundled():
        base = get_base_path()
        
        # Set Playwright browsers path
        browsers_path = base / "browsers"
        if browsers_path.exists():
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_path)
        
        # Add base path to Python path for imports
        if str(base) not in sys.path:
            sys.path.insert(0, str(base))


def get_data_directory() -> Path:
    """
    Get the data directory for user data (database, logs, etc.).
    This should be in a writable location outside the bundle.
    
    Returns:
        Path to data directory
    """
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
    
    data_dir = Path(base) / "ReverseOutreachBot" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_logs_directory() -> Path:
    """Get the logs directory."""
    logs_dir = get_data_directory().parent / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir

