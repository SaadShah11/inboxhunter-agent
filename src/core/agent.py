"""
Main InboxHunter Agent class.
Coordinates browser automation, platform communication, and task execution.
"""

import asyncio
import time
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime
from enum import Enum
from loguru import logger

from .config import AgentConfig, get_agent_config


class AgentStatus(str, Enum):
    """Agent status states."""
    IDLE = "idle"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    ERROR = "error"
    OFFLINE = "offline"


class InboxHunterAgent:
    """
    Main agent class that:
    - Connects to platform via WebSocket
    - Receives and executes tasks
    - Reports results back to platform
    - Manages browser automation
    """
    
    def __init__(self, config: Optional[AgentConfig] = None):
        """Initialize the agent."""
        self.config = config or get_agent_config()
        self.status = AgentStatus.IDLE
        self._stop_requested = False
        self._current_task: Optional[Dict[str, Any]] = None
        
        # Components (lazy initialized)
        self._ws_client = None
        self._browser = None
        self._orchestrator = None
        
        # Stats
        self.stats = {
            "total_tasks": 0,
            "successful": 0,
            "failed": 0,
            "current_session_start": None
        }
        
        # Callbacks for UI updates
        self._status_callbacks: List[Callable[[AgentStatus], None]] = []
        self._log_callbacks: List[Callable[[str], None]] = []
        self._stats_callbacks: List[Callable[[Dict], None]] = []
        
        logger.info("InboxHunter Agent initialized")
    
    def on_status_change(self, callback: Callable[[AgentStatus], None]):
        """Register callback for status changes."""
        self._status_callbacks.append(callback)
    
    def on_log(self, callback: Callable[[str], None]):
        """Register callback for log messages."""
        self._log_callbacks.append(callback)
    
    def on_stats_update(self, callback: Callable[[Dict], None]):
        """Register callback for stats updates."""
        self._stats_callbacks.append(callback)
    
    def _set_status(self, status: AgentStatus):
        """Update status and notify callbacks."""
        self.status = status
        for callback in self._status_callbacks:
            try:
                callback(status)
            except Exception as e:
                logger.error(f"Status callback error: {e}")
    
    def _emit_log(self, message: str):
        """Emit log message to callbacks."""
        logger.info(message)
        for callback in self._log_callbacks:
            try:
                callback(message)
            except Exception as e:
                logger.error(f"Log callback error: {e}")
    
    def _emit_stats(self):
        """Emit stats update to callbacks."""
        for callback in self._stats_callbacks:
            try:
                callback(self.stats.copy())
            except Exception as e:
                logger.error(f"Stats callback error: {e}")
    
    async def connect_to_platform(self) -> bool:
        """
        Connect to the InboxHunter platform via WebSocket.
        
        Returns:
            True if connected successfully
        """
        from src.api.websocket import PlatformWebSocket
        
        self._set_status(AgentStatus.CONNECTING)
        self._emit_log("Connecting to InboxHunter platform...")
        
        try:
            self._ws_client = PlatformWebSocket(
                url=self.config.platform.ws_url,
                agent_id=self.config.agent_id,
                agent_token=self.config.agent_token,
                on_task=self._handle_task,
                on_config_update=self._handle_config_update,
                on_command=self._handle_command
            )
            
            connected = await self._ws_client.connect()
            
            if connected:
                self._set_status(AgentStatus.CONNECTED)
                self._emit_log("✅ Connected to platform")
                return True
            else:
                self._set_status(AgentStatus.OFFLINE)
                self._emit_log("❌ Failed to connect to platform")
                return False
                
        except Exception as e:
            logger.error(f"Connection error: {e}")
            self._set_status(AgentStatus.ERROR)
            self._emit_log(f"❌ Connection error: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from platform."""
        if self._ws_client:
            await self._ws_client.disconnect()
            self._ws_client = None
        self._set_status(AgentStatus.OFFLINE)
        self._emit_log("Disconnected from platform")
    
    async def _handle_task(self, task: Dict[str, Any]):
        """
        Handle incoming task from platform.
        
        Args:
            task: Task data from platform
        """
        task_id = task.get("task_id")
        task_type = task.get("type", "signup")
        
        self._emit_log(f"📥 Received task: {task_type} (ID: {task_id})")
        self._current_task = task
        self.stats["total_tasks"] += 1
        
        try:
            self._set_status(AgentStatus.RUNNING)
            
            if task_type == "signup":
                result = await self._execute_signup_task(task)
            elif task_type == "scrape":
                result = await self._execute_scrape_task(task)
            else:
                result = {"success": False, "error": f"Unknown task type: {task_type}"}
            
            # Report result to platform
            if self._ws_client:
                await self._ws_client.send_task_result(task_id, result)
            
            if result.get("success"):
                self.stats["successful"] += 1
                self._emit_log(f"✅ Task completed successfully")
            else:
                self.stats["failed"] += 1
                self._emit_log(f"❌ Task failed: {result.get('error', 'Unknown error')}")
            
            self._emit_stats()
            
        except Exception as e:
            logger.error(f"Task execution error: {e}", exc_info=True)
            self.stats["failed"] += 1
            self._emit_log(f"❌ Task error: {e}")
            
            if self._ws_client:
                await self._ws_client.send_task_result(task_id, {
                    "success": False,
                    "error": str(e)
                })
        
        finally:
            self._current_task = None
            if not self._stop_requested:
                self._set_status(AgentStatus.CONNECTED)
    
    async def _execute_signup_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a signup task.
        
        Args:
            task: Task data containing URL and credentials
            
        Returns:
            Result dictionary
        """
        from src.automation.browser import BrowserAutomation
        from src.automation.agent_orchestrator import AIAgentOrchestrator
        
        url = task.get("url")
        credentials = task.get("credentials", {})
        
        # Use task credentials or fall back to config
        if not credentials:
            credentials = {
                "email": self.config.credentials.email,
                "first_name": self.config.credentials.first_name,
                "last_name": self.config.credentials.last_name,
                "full_name": self.config.credentials.full_name,
                "phone": {
                    "country_code": self.config.credentials.phone_country_code,
                    "number": self.config.credentials.phone_number,
                    "full": self.config.credentials.phone_full
                }
            }
        
        self._emit_log(f"🌐 Processing: {url}")
        
        # Initialize browser if needed
        if self._browser is None:
            self._browser = BrowserAutomation(self._build_legacy_config())
            await self._browser.initialize()
        
        try:
            # Navigate to page
            success = await self._browser.navigate(url)
            if not success:
                return {"success": False, "error": "Failed to load page"}
            
            # Detect platform
            platform = await self._browser.detect_platform()
            self._emit_log(f"🔍 Platform detected: {platform}")
            
            # Create AI agent
            agent = AIAgentOrchestrator(
                page=self._browser.page,
                credentials=credentials,
                llm_provider=self.config.llm.provider,
                llm_config={
                    "api_key": self.config.llm.api_key,
                    "model": self.config.llm.model
                },
                stop_check=lambda: self._stop_requested
            )
            
            # Execute signup
            result = await agent.execute_signup()
            
            # Add metadata
            result["url"] = url
            result["platform"] = platform
            result["timestamp"] = datetime.utcnow().isoformat()
            
            return result
            
        except Exception as e:
            logger.error(f"Signup error: {e}", exc_info=True)
            return {"success": False, "error": str(e), "url": url}
    
    async def _execute_scrape_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a scraping task (Meta Ads Library, etc.)
        
        Args:
            task: Task data containing scrape parameters
            
        Returns:
            Result dictionary with scraped URLs
        """
        source = task.get("source", "meta")
        params = task.get("params", {})
        
        self._emit_log(f"🔍 Starting scrape: {source}")
        
        try:
            if source == "meta":
                from src.scrapers.meta_ads import MetaAdsLibraryScraper
                
                scraper = MetaAdsLibraryScraper(self._build_legacy_config())
                await scraper.initialize()
                
                keywords = params.get("keywords", ["marketing"])
                limit = params.get("limit", 50)
                
                ads = await scraper.scrape_ads(keywords=keywords, limit=limit)
                await scraper.close()
                
                return {
                    "success": True,
                    "ads": ads,
                    "count": len(ads)
                }
            
            elif source == "csv":
                from src.scrapers.csv_parser import CSVDataParser
                
                csv_path = params.get("path", "./data/training.csv")
                parser = CSVDataParser(self._build_legacy_config())
                ads = parser.parse(csv_path)
                
                return {
                    "success": True,
                    "ads": ads,
                    "count": len(ads)
                }
            
            else:
                return {"success": False, "error": f"Unknown scrape source: {source}"}
                
        except Exception as e:
            logger.error(f"Scrape error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    async def _handle_config_update(self, config_data: Dict[str, Any]):
        """Handle config update from platform."""
        self._emit_log("📥 Received config update from platform")
        self.config.update_from_platform(config_data)
    
    async def _handle_command(self, command: str, params: Dict[str, Any]):
        """
        Handle command from platform.
        
        Commands:
        - pause: Pause task execution
        - resume: Resume task execution
        - stop: Stop current task
        - restart: Restart the agent
        """
        self._emit_log(f"📥 Received command: {command}")
        
        if command == "pause":
            self._set_status(AgentStatus.PAUSED)
            
        elif command == "resume":
            self._set_status(AgentStatus.CONNECTED)
            
        elif command == "stop":
            self._stop_requested = True
            self._set_status(AgentStatus.STOPPING)
            
        elif command == "restart":
            await self.restart()
    
    def _build_legacy_config(self):
        """Build legacy Config object for compatibility with existing automation code."""
        from src.config import Config, CredentialsConfig as LegacyCredentials
        from src.config import PhoneConfig, LLMConfig as LegacyLLM
        from src.config import CaptchaConfig as LegacyCaptcha
        from src.config import AutomationConfig as LegacyAutomation
        from src.config import ViewportConfig, StealthConfig, BehaviorConfig
        from src.config import TimeoutsConfig, DelaysConfig
        from src.config import SourcesConfig, MetaAdsConfig, CSVDataConfig
        from src.config import DatabaseConfig, LoggingConfig, ProxyConfig
        from src.config import FormDetectionConfig, ErrorHandlingConfig, AppConfig
        from src.config import RateLimitingConfig
        
        return Config(
            app=AppConfig(
                name="InboxHunter Agent",
                version="2.0.0",
                debug=self.config.log_level == "DEBUG"
            ),
            credentials=LegacyCredentials(
                first_name=self.config.credentials.first_name,
                last_name=self.config.credentials.last_name,
                full_name=self.config.credentials.full_name,
                email=self.config.credentials.email,
                phone=PhoneConfig(
                    country_code=self.config.credentials.phone_country_code,
                    number=self.config.credentials.phone_number,
                    full=self.config.credentials.phone_full
                )
            ),
            captcha=LegacyCaptcha(
                service=self.config.captcha.service,
                api_keys={"twocaptcha": self.config.captcha.api_key},
                timeout=self.config.captcha.timeout
            ),
            llm=LegacyLLM(
                enabled=self.config.llm.enabled,
                provider=self.config.llm.provider,
                api_key=self.config.llm.api_key,
                model=self.config.llm.model
            ),
            sources=SourcesConfig(
                meta_ads_library=MetaAdsConfig(enabled=False),
                csv_data=CSVDataConfig(enabled=False)
            ),
            automation=LegacyAutomation(
                browser=self.config.automation.browser,
                headless=self.config.automation.headless,
                viewport=ViewportConfig(
                    width=self.config.automation.viewport_width,
                    height=self.config.automation.viewport_height
                ),
                stealth=StealthConfig(enabled=self.config.automation.stealth_enabled),
                behavior=BehaviorConfig(
                    typing_delay_min=self.config.automation.typing_delay_min,
                    typing_delay_max=self.config.automation.typing_delay_max
                )
            ),
            rate_limiting=RateLimitingConfig(),
            database=DatabaseConfig(),
            logging=LoggingConfig(),
            proxy=ProxyConfig(),
            form_detection=FormDetectionConfig(),
            error_handling=ErrorHandlingConfig()
        )
    
    async def run(self):
        """
        Main agent run loop.
        Connects to platform and processes tasks.
        """
        self.stats["current_session_start"] = datetime.utcnow().isoformat()
        self._stop_requested = False
        
        self._emit_log("🚀 Starting InboxHunter Agent...")
        
        # Connect to platform
        connected = await self.connect_to_platform()
        
        if not connected:
            self._emit_log("⚠️ Running in offline mode")
            return
        
        # Main loop - keep connection alive and process tasks
        try:
            while not self._stop_requested:
                if self._ws_client:
                    await self._ws_client.process_messages()
                await asyncio.sleep(0.1)
                
        except asyncio.CancelledError:
            self._emit_log("Agent loop cancelled")
        except Exception as e:
            logger.error(f"Agent loop error: {e}", exc_info=True)
            self._set_status(AgentStatus.ERROR)
        finally:
            await self.cleanup()
    
    async def stop(self):
        """Stop the agent gracefully."""
        self._emit_log("🛑 Stopping agent...")
        self._stop_requested = True
        self._set_status(AgentStatus.STOPPING)
        
        # Wait for current task to complete
        if self._current_task:
            self._emit_log("Waiting for current task to complete...")
            for _ in range(30):  # Wait up to 30 seconds
                if self._current_task is None:
                    break
                await asyncio.sleep(1)
    
    async def restart(self):
        """Restart the agent."""
        self._emit_log("🔄 Restarting agent...")
        await self.stop()
        await self.cleanup()
        await asyncio.sleep(2)
        await self.run()
    
    async def cleanup(self):
        """Clean up resources."""
        self._emit_log("🧹 Cleaning up...")
        
        if self._browser:
            await self._browser.close()
            self._browser = None
        
        if self._ws_client:
            await self._ws_client.disconnect()
            self._ws_client = None
        
        self._set_status(AgentStatus.IDLE)
        self._emit_log("✅ Cleanup complete")
    
    def is_running(self) -> bool:
        """Check if agent is currently running."""
        return self.status in [AgentStatus.CONNECTED, AgentStatus.RUNNING]
    
    def get_status(self) -> Dict[str, Any]:
        """Get current agent status."""
        return {
            "status": self.status.value,
            "agent_id": self.config.agent_id,
            "current_task": self._current_task.get("task_id") if self._current_task else None,
            "stats": self.stats,
            "connected": self._ws_client is not None and self._ws_client.is_connected
        }

