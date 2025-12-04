"""
System tray application for InboxHunter Agent.
Provides minimal UI through system tray icon and menu.
"""

import asyncio
import threading
import webbrowser
from typing import Optional, Callable
from pathlib import Path
from loguru import logger

try:
    import pystray
    from PIL import Image
    PYSTRAY_AVAILABLE = True
except ImportError:
    PYSTRAY_AVAILABLE = False
    logger.warning("pystray or PIL not installed, system tray not available")


class SystemTrayApp:
    """
    System tray application for the InboxHunter Agent.
    
    Features:
    - Status indicator (icon color)
    - Quick actions menu
    - Open dashboard link
    - Start/Stop agent
    - Quit application
    """
    
    # Dashboard URL
    DASHBOARD_URL = "https://app.inboxhunter.io"
    
    def __init__(
        self,
        on_start: Optional[Callable[[], None]] = None,
        on_stop: Optional[Callable[[], None]] = None,
        on_quit: Optional[Callable[[], None]] = None
    ):
        """
        Initialize system tray app.
        
        Args:
            on_start: Callback when user clicks Start
            on_stop: Callback when user clicks Stop
            on_quit: Callback when user clicks Quit
        """
        self.on_start = on_start
        self.on_stop = on_stop
        self.on_quit = on_quit
        
        self._icon: Optional[pystray.Icon] = None
        self._status = "idle"
        self._stats = {"successful": 0, "failed": 0}
        
        # Load icons
        self._icons = {}
        self._load_icons()
    
    def _load_icons(self):
        """Load status icons for tray."""
        if not PYSTRAY_AVAILABLE:
            return
        
        # Icon paths
        resources_dir = Path(__file__).parent.parent.parent / "resources"
        
        # Try to load custom icons, fall back to generated ones
        icon_files = {
            "idle": resources_dir / "icon_idle.png",
            "connected": resources_dir / "icon_connected.png",
            "running": resources_dir / "icon_running.png",
            "error": resources_dir / "icon_error.png"
        }
        
        for status, icon_path in icon_files.items():
            if icon_path.exists():
                try:
                    self._icons[status] = Image.open(icon_path)
                    continue
                except Exception:
                    pass
            
            # Generate simple colored icon
            self._icons[status] = self._generate_icon(status)
    
    def _generate_icon(self, status: str) -> Image.Image:
        """
        Generate a simple colored icon.
        
        Args:
            status: Status for color selection
            
        Returns:
            PIL Image
        """
        colors = {
            "idle": (128, 128, 128),      # Gray
            "connected": (0, 200, 100),    # Green
            "running": (0, 150, 255),      # Blue
            "error": (255, 100, 100),      # Red
            "offline": (200, 100, 0)       # Orange
        }
        
        color = colors.get(status, colors["idle"])
        
        # Create 64x64 icon
        size = 64
        image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        
        # Draw a filled circle
        from PIL import ImageDraw
        draw = ImageDraw.Draw(image)
        padding = 4
        draw.ellipse(
            [padding, padding, size - padding, size - padding],
            fill=color + (255,),
            outline=(255, 255, 255, 200),
            width=2
        )
        
        return image
    
    def _create_menu(self) -> pystray.Menu:
        """Create the tray menu."""
        return pystray.Menu(
            pystray.MenuItem(
                f"Status: {self._status.title()}",
                None,
                enabled=False
            ),
            pystray.MenuItem(
                f"✅ {self._stats['successful']} | ❌ {self._stats['failed']}",
                None,
                enabled=False
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "🌐 Open Dashboard",
                self._open_dashboard
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "▶ Start",
                self._handle_start,
                visible=self._status in ["idle", "connected", "error"]
            ),
            pystray.MenuItem(
                "⏹ Stop",
                self._handle_stop,
                visible=self._status == "running"
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "⚙️ Settings",
                self._open_settings
            ),
            pystray.MenuItem(
                "📋 View Logs",
                self._open_logs
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "❌ Quit",
                self._handle_quit
            )
        )
    
    def _open_dashboard(self, icon=None, item=None):
        """Open dashboard in browser."""
        webbrowser.open(self.DASHBOARD_URL)
    
    def _open_settings(self, icon=None, item=None):
        """Open settings page in browser."""
        webbrowser.open(f"{self.DASHBOARD_URL}/settings")
    
    def _open_logs(self, icon=None, item=None):
        """Open logs directory."""
        from src.core.config import get_data_dir
        import subprocess
        import sys
        
        logs_dir = get_data_dir() / "logs"
        logs_dir.mkdir(exist_ok=True)
        
        if sys.platform == "win32":
            subprocess.run(["explorer", str(logs_dir)])
        elif sys.platform == "darwin":
            subprocess.run(["open", str(logs_dir)])
        else:
            subprocess.run(["xdg-open", str(logs_dir)])
    
    def _handle_start(self, icon=None, item=None):
        """Handle Start menu click."""
        if self.on_start:
            # Run in thread to not block tray
            threading.Thread(target=self.on_start, daemon=True).start()
    
    def _handle_stop(self, icon=None, item=None):
        """Handle Stop menu click."""
        if self.on_stop:
            threading.Thread(target=self.on_stop, daemon=True).start()
    
    def _handle_quit(self, icon=None, item=None):
        """Handle Quit menu click."""
        logger.info("Quit requested from tray")
        
        if self._icon:
            self._icon.stop()
        
        if self.on_quit:
            self.on_quit()
    
    def update_status(self, status: str):
        """
        Update tray icon status.
        
        Args:
            status: New status (idle, connected, running, error)
        """
        self._status = status
        
        if self._icon:
            # Update icon
            if status in self._icons:
                self._icon.icon = self._icons[status]
            
            # Update menu
            self._icon.menu = self._create_menu()
            
            # Update tooltip
            self._icon.title = f"InboxHunter Agent - {status.title()}"
    
    def update_stats(self, stats: dict):
        """
        Update statistics display.
        
        Args:
            stats: Dictionary with successful and failed counts
        """
        self._stats = {
            "successful": stats.get("successful", 0),
            "failed": stats.get("failed", 0)
        }
        
        if self._icon:
            self._icon.menu = self._create_menu()
    
    def show_notification(self, title: str, message: str):
        """
        Show a system notification.
        
        Args:
            title: Notification title
            message: Notification message
        """
        if self._icon:
            try:
                self._icon.notify(message, title)
            except Exception as e:
                logger.debug(f"Notification error: {e}")
    
    def run(self):
        """Run the system tray application (blocking)."""
        if not PYSTRAY_AVAILABLE:
            logger.error("pystray not available, cannot run system tray")
            return
        
        # Create icon
        self._icon = pystray.Icon(
            name="InboxHunter",
            icon=self._icons.get("idle", self._generate_icon("idle")),
            title="InboxHunter Agent - Idle",
            menu=self._create_menu()
        )
        
        logger.info("Starting system tray...")
        
        # Run (blocking)
        self._icon.run()
    
    def run_detached(self):
        """Run system tray in background thread."""
        if not PYSTRAY_AVAILABLE:
            logger.error("pystray not available")
            return
        
        thread = threading.Thread(target=self.run, daemon=True)
        thread.start()
        return thread
    
    def stop(self):
        """Stop the system tray."""
        if self._icon:
            self._icon.stop()


class ConsoleFallback:
    """
    Fallback UI for systems without system tray support.
    Provides console-based interface.
    """
    
    def __init__(
        self,
        on_start: Optional[Callable[[], None]] = None,
        on_stop: Optional[Callable[[], None]] = None,
        on_quit: Optional[Callable[[], None]] = None
    ):
        self.on_start = on_start
        self.on_stop = on_stop
        self.on_quit = on_quit
        self._running = True
        self._status = "idle"
    
    def update_status(self, status: str):
        self._status = status
        print(f"\r[Status: {status}] ", end="", flush=True)
    
    def update_stats(self, stats: dict):
        s = stats.get("successful", 0)
        f = stats.get("failed", 0)
        print(f"[✅ {s} | ❌ {f}]", end="", flush=True)
    
    def show_notification(self, title: str, message: str):
        print(f"\n📢 {title}: {message}")
    
    def run(self):
        """Run console interface."""
        print("\n" + "=" * 50)
        print("InboxHunter Agent - Console Mode")
        print("=" * 50)
        print("Commands: [s]tart, s[t]op, [q]uit")
        print("=" * 50 + "\n")
        
        while self._running:
            try:
                cmd = input(f"[{self._status}] > ").strip().lower()
                
                if cmd in ["s", "start"]:
                    if self.on_start:
                        self.on_start()
                elif cmd in ["t", "stop"]:
                    if self.on_stop:
                        self.on_stop()
                elif cmd in ["q", "quit", "exit"]:
                    self._running = False
                    if self.on_quit:
                        self.on_quit()
                else:
                    print("Unknown command. Use: start, stop, quit")
                    
            except (KeyboardInterrupt, EOFError):
                print("\nExiting...")
                self._running = False
                if self.on_quit:
                    self.on_quit()
    
    def run_detached(self):
        thread = threading.Thread(target=self.run, daemon=True)
        thread.start()
        return thread
    
    def stop(self):
        self._running = False


def get_ui_app(**kwargs):
    """
    Get appropriate UI app based on system support.
    
    Returns SystemTrayApp if available, otherwise ConsoleFallback.
    """
    if PYSTRAY_AVAILABLE:
        return SystemTrayApp(**kwargs)
    else:
        logger.warning("System tray not available, using console fallback")
        return ConsoleFallback(**kwargs)

