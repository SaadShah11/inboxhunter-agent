"""
Auto-update mechanism for the InboxHunter Agent.
Checks for updates from platform and applies them.
"""

import asyncio
import hashlib
import os
import sys
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, Callable
import httpx
from loguru import logger

from .config import get_data_dir


class AgentUpdater:
    """
    Handles automatic updates for the agent.
    
    Update flow:
    1. Check platform for new version
    2. Download update if available
    3. Verify checksum
    4. Apply update and restart
    """
    
    VERSION = "2.0.0"  # Current agent version
    
    def __init__(
        self,
        api_url: str = "https://api.inboxhunter.io",
        on_update_available: Optional[Callable[[str], None]] = None,
        on_update_progress: Optional[Callable[[int], None]] = None,
        on_update_complete: Optional[Callable[[], None]] = None
    ):
        """
        Initialize updater.
        
        Args:
            api_url: Platform API URL
            on_update_available: Callback when update is available (version string)
            on_update_progress: Callback for download progress (0-100)
            on_update_complete: Callback when update is complete
        """
        self.api_url = api_url.rstrip('/')
        self.on_update_available = on_update_available
        self.on_update_progress = on_update_progress
        self.on_update_complete = on_update_complete
        
        self._update_info: Optional[Dict[str, Any]] = None
    
    @property
    def current_version(self) -> str:
        """Get current agent version."""
        return self.VERSION
    
    async def check_for_updates(self) -> Optional[Dict[str, Any]]:
        """
        Check platform for available updates.
        
        Returns:
            Update info dict if update available, None otherwise
        """
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{self.api_url}/agent/version",
                    params={"current_version": self.VERSION}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if data.get("update_available"):
                        self._update_info = data
                        new_version = data.get("latest_version")
                        
                        logger.info(f"Update available: {self.VERSION} → {new_version}")
                        
                        if self.on_update_available:
                            self.on_update_available(new_version)
                        
                        return data
                    else:
                        logger.debug("No updates available")
                        return None
                else:
                    logger.warning(f"Update check failed: {response.status_code}")
                    return None
                    
        except Exception as e:
            logger.error(f"Update check error: {e}")
            return None
    
    async def download_update(self) -> Optional[Path]:
        """
        Download the update package.
        
        Returns:
            Path to downloaded file, or None if failed
        """
        if not self._update_info:
            logger.error("No update info available")
            return None
        
        download_url = self._update_info.get("download_url")
        expected_checksum = self._update_info.get("checksum")
        
        if not download_url:
            logger.error("No download URL in update info")
            return None
        
        try:
            # Determine download path
            temp_dir = Path(tempfile.gettempdir()) / "inboxhunter_update"
            temp_dir.mkdir(parents=True, exist_ok=True)
            
            # Determine filename based on OS
            if sys.platform == "win32":
                filename = "InboxHunterAgent.exe"
            elif sys.platform == "darwin":
                filename = "InboxHunterAgent"
            else:
                filename = "InboxHunterAgent"
            
            download_path = temp_dir / filename
            
            logger.info(f"Downloading update from {download_url}")
            
            async with httpx.AsyncClient(timeout=300) as client:
                async with client.stream("GET", download_url) as response:
                    if response.status_code != 200:
                        logger.error(f"Download failed: {response.status_code}")
                        return None
                    
                    total_size = int(response.headers.get("content-length", 0))
                    downloaded = 0
                    
                    with open(download_path, "wb") as f:
                        async for chunk in response.aiter_bytes(chunk_size=8192):
                            f.write(chunk)
                            downloaded += len(chunk)
                            
                            if total_size > 0 and self.on_update_progress:
                                progress = int((downloaded / total_size) * 100)
                                self.on_update_progress(progress)
            
            # Verify checksum if provided
            if expected_checksum:
                actual_checksum = self._calculate_checksum(download_path)
                if actual_checksum != expected_checksum:
                    logger.error(f"Checksum mismatch: expected {expected_checksum}, got {actual_checksum}")
                    download_path.unlink()
                    return None
                logger.debug("Checksum verified")
            
            logger.info(f"Update downloaded to {download_path}")
            return download_path
            
        except Exception as e:
            logger.error(f"Download error: {e}")
            return None
    
    def _calculate_checksum(self, file_path: Path) -> str:
        """Calculate SHA256 checksum of a file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    async def apply_update(self, update_path: Path) -> bool:
        """
        Apply the downloaded update.
        
        This will:
        1. Backup current executable
        2. Replace with new version
        3. Schedule restart
        
        Args:
            update_path: Path to downloaded update file
            
        Returns:
            True if update applied successfully
        """
        try:
            current_exe = Path(sys.executable)
            
            # For frozen executables (PyInstaller)
            if getattr(sys, 'frozen', False):
                backup_path = current_exe.with_suffix('.bak')
                
                # Create backup
                if current_exe.exists():
                    shutil.copy2(current_exe, backup_path)
                    logger.debug(f"Backup created: {backup_path}")
                
                # On Windows, we can't replace running executable
                # Need to use a batch script or restart helper
                if sys.platform == "win32":
                    await self._apply_update_windows(current_exe, update_path)
                else:
                    # On Unix, we can replace the executable
                    shutil.copy2(update_path, current_exe)
                    os.chmod(current_exe, 0o755)
                
                logger.info("Update applied successfully")
                
                if self.on_update_complete:
                    self.on_update_complete()
                
                return True
            else:
                # Development mode - just log
                logger.info("Update available (dev mode, not applying)")
                return False
                
        except Exception as e:
            logger.error(f"Update apply error: {e}")
            return False
    
    async def _apply_update_windows(self, current_exe: Path, update_path: Path):
        """
        Apply update on Windows using a batch script.
        The script waits for the current process to exit, then replaces the exe.
        """
        batch_path = current_exe.parent / "update.bat"
        
        batch_content = f'''@echo off
echo Waiting for agent to close...
timeout /t 2 /nobreak >nul
:waitloop
tasklist /fi "imagename eq {current_exe.name}" | find /i "{current_exe.name}" >nul
if not errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto waitloop
)
echo Applying update...
copy /y "{update_path}" "{current_exe}"
echo Update complete. Restarting...
start "" "{current_exe}"
del "%~f0"
'''
        
        with open(batch_path, 'w') as f:
            f.write(batch_content)
        
        # Start the batch script
        os.startfile(batch_path)
    
    async def update_and_restart(self) -> bool:
        """
        Full update cycle: check, download, apply, restart.
        
        Returns:
            True if update was applied (app will restart)
        """
        # Check for updates
        update_info = await self.check_for_updates()
        if not update_info:
            return False
        
        # Download
        update_path = await self.download_update()
        if not update_path:
            return False
        
        # Apply
        success = await self.apply_update(update_path)
        if not success:
            return False
        
        # Restart the application
        logger.info("Restarting application...")
        
        if sys.platform == "win32":
            # On Windows, the batch script handles restart
            pass
        else:
            # On Unix, restart the process
            os.execv(sys.executable, [sys.executable] + sys.argv)
        
        return True


async def check_for_updates_background(interval_hours: int = 6):
    """
    Background task to periodically check for updates.
    
    Args:
        interval_hours: Hours between update checks
    """
    updater = AgentUpdater()
    
    while True:
        try:
            await updater.check_for_updates()
        except Exception as e:
            logger.error(f"Background update check error: {e}")
        
        await asyncio.sleep(interval_hours * 3600)

