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
        self._stop_agent = False  # Stop the entire agent
        self._stop_task = False   # Stop the current task only
        self._current_task: Optional[Dict[str, Any]] = None
        self._current_task_id: Optional[str] = None
        
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
        url = task.get("url")
        keywords = task.get("params", {}).get("keywords", [])
        
        self._emit_log(f"📥 Received task: {task_type} (ID: {task_id})")
        self._current_task = task
        self._current_task_id = task_id
        self.stats["total_tasks"] += 1
        
        # Reset task stop flag for new task
        self._stop_task = False
        
        try:
            self._set_status(AgentStatus.RUNNING)
            
            # Notify platform task has started
            if self._ws_client:
                await self._ws_client.send_task_started(
                    task_id=task_id,
                    task_type=task_type,
                    url=url,
                    keywords=keywords if task_type == "scrape" else None
                )
                await self._send_log("info", f"Starting {task_type} task...", task_id)
            
            if task_type == "signup":
                result = await self._execute_signup_task(task)
            elif task_type == "scrape":
                result = await self._execute_scrape_task(task)
            else:
                result = {"success": False, "error": f"Unknown task type: {task_type}"}
            
            # Report result to platform
            if self._ws_client:
                success = result.get("success", False)
                error = result.get("error")
                await self._ws_client.send_task_result(
                    task_id=task_id,
                    result=result,
                    success=success,
                    error=error
                )
            
            if result.get("success"):
                self.stats["successful"] += 1
                self._emit_log(f"✅ Task completed successfully")
                await self._send_log("success", "Task completed successfully", task_id)
            else:
                self.stats["failed"] += 1
                error_msg = result.get('error', 'Unknown error')
                self._emit_log(f"❌ Task failed: {error_msg}")
                await self._send_log("error", f"Task failed: {error_msg}", task_id)
            
            self._emit_stats()
            
        except Exception as e:
            logger.error(f"Task execution error: {e}", exc_info=True)
            self.stats["failed"] += 1
            self._emit_log(f"❌ Task error: {e}")
            await self._send_log("error", f"Task error: {str(e)}", task_id)
            
            if self._ws_client:
                await self._ws_client.send_task_result(
                    task_id=task_id,
                    result={"success": False, "error": str(e)},
                    success=False,
                    error=str(e)
                )
        
        finally:
            self._current_task = None
            self._current_task_id = None
            self._stop_task = False  # Reset task stop flag
            if not self._stop_agent:
                self._set_status(AgentStatus.CONNECTED)
    
    async def _send_log(self, level: str, message: str, task_id: str = None):
        """Send log to platform via WebSocket."""
        if self._ws_client:
            try:
                await self._ws_client.send_log(level, message, task_id=task_id)
            except Exception as e:
                logger.debug(f"Failed to send log to platform: {e}")
    
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
        
        task_id = task.get("task_id")
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
        await self._send_log("info", f"Processing URL: {url}", task_id)
        
        # Check stop before starting
        if self._stop_task:
            await self._send_log("warning", "Task stopped before starting", task_id)
            return {"success": False, "error": "Stopped by user", "url": url, "stopped": True}
        
        await self._send_log("info", "Initializing browser...", task_id)
        
        # Initialize browser if needed
        if self._browser is None:
            self._browser = BrowserAutomation(self._build_legacy_config())
            await self._browser.initialize()
        
        try:
            # Check stop after browser init
            if self._stop_task:
                await self._send_log("warning", "Task stopped by user", task_id)
                await self._close_browser()
                return {"success": False, "error": "Stopped by user", "url": url, "stopped": True}
            
            # Navigate to page
            await self._send_log("info", "Loading page...", task_id)
            
            success = await self._browser.navigate(url)
            if not success:
                await self._send_log("error", "Failed to load page", task_id)
                return {"success": False, "error": "Failed to load page"}
            
            # Check stop after navigation
            if self._stop_task:
                await self._send_log("warning", "Task stopped by user", task_id)
                await self._close_browser()
                return {"success": False, "error": "Stopped by user", "url": url, "stopped": True}
            
            await self._send_log("info", "Detecting page structure...", task_id)
            
            # Detect platform
            platform = await self._browser.detect_platform()
            self._emit_log(f"🔍 Platform detected: {platform}")
            await self._send_log("info", f"Platform detected: {platform}", task_id)
            
            # Check stop after platform detection
            if self._stop_task:
                await self._send_log("warning", "Task stopped by user", task_id)
                await self._close_browser()
                return {"success": False, "error": "Stopped by user", "url": url, "stopped": True}
            
            await self._send_log("info", "Analyzing form fields...", task_id)
            
            # Create AI agent
            agent = AIAgentOrchestrator(
                page=self._browser.page,
                credentials=credentials,
                llm_provider=self.config.llm.provider,
                llm_config={
                    "api_key": self.config.llm.api_key,
                    "model": self.config.llm.model
                },
                stop_check=lambda: self._stop_task
            )
            
            # Check stop before AI analysis
            if self._stop_task:
                await self._send_log("warning", "Task stopped by user", task_id)
                await self._close_browser()
                return {"success": False, "error": "Stopped by user", "url": url, "stopped": True}
            
            await self._send_log("info", "AI analyzing form...", task_id)
            
            # Execute signup
            result = await agent.execute_signup()
            
            # Check if stopped during execution
            if self._stop_task:
                await self._send_log("warning", "Task stopped by user", task_id)
                await self._close_browser()
                result["stopped"] = True
                if not result.get("error"):
                    result["error"] = "Stopped by user"
                return result
            
            await self._send_log("info", "Finalizing...", task_id)
            
            # Add metadata
            result["url"] = url
            result["platform"] = platform
            result["timestamp"] = datetime.utcnow().isoformat()
            
            if result.get("success"):
                await self._send_progress(task_id, 100, "Complete")
                await self._send_log("success", "Form submitted successfully!", task_id)
            
            # Close browser after successful completion
            await self._close_browser()
            
            return result
            
        except Exception as e:
            logger.error(f"Signup error: {e}", exc_info=True)
            await self._send_log("error", f"Signup error: {str(e)}", task_id)
            await self._close_browser()
            return {"success": False, "error": str(e), "url": url}
    
    async def _close_browser(self):
        """Close the browser instance."""
        if self._browser:
            try:
                await self._browser.close()
                self._browser = None
                logger.info("Browser closed")
            except Exception as e:
                logger.debug(f"Error closing browser: {e}")
    
    async def _send_progress(self, task_id: str, progress: int, current_step: str = None):
        """Send progress update to platform."""
        if self._ws_client:
            try:
                await self._ws_client.send_task_progress(
                    task_id=task_id,
                    progress=progress,
                    status="running",
                    current_step=current_step
                )
            except Exception as e:
                logger.debug(f"Failed to send progress: {e}")
    
    async def _execute_scrape_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a scraping task (Meta Ads Library, etc.)
        
        Args:
            task: Task data containing scrape parameters
            
        Returns:
            Result dictionary with scraped URLs
        """
        task_id = task.get("task_id")
        source = task.get("source", "meta_ads")
        params = task.get("params", {})
        
        self._emit_log(f"🔍 Starting scrape: {source}")
        await self._send_log("info", f"Starting scrape from {source}", task_id)
        
        # Check stop before starting
        if self._stop_task:
            await self._send_log("warning", "Task stopped before starting", task_id)
            return {"success": False, "error": "Stopped by user", "stopped": True}
        
        await self._send_log("info", "Initializing scraper...", task_id)
        
        try:
            if source in ["meta", "meta_ads"]:
                from src.scrapers.meta_ads import MetaAdsLibraryScraper
                
                # Build config and set ad limit
                config = self._build_legacy_config()
                limit = params.get("limit", 50)
                config.sources.meta_ads_library.ad_limit = limit
                config.sources.meta_ads_library.enabled = True
                
                # Check stop before browser init
                if self._stop_task:
                    await self._send_log("warning", "Task stopped by user", task_id)
                    return {"success": False, "error": "Stopped by user", "stopped": True}
                
                await self._send_log("info", "Starting browser for Meta Ads Library...", task_id)
                
                scraper = MetaAdsLibraryScraper(config, stop_check=lambda: self._stop_task)
                await scraper.initialize()
                
                # Check stop after browser init
                if self._stop_task:
                    await scraper.close()
                    await self._send_log("warning", "Task stopped by user", task_id)
                    return {"success": False, "error": "Stopped by user", "stopped": True}
                
                keywords = params.get("keywords", ["marketing"])
                self._emit_log(f"🔎 Searching keywords: {', '.join(keywords)}")
                await self._send_log("info", f"Searching keywords: {', '.join(keywords)}", task_id)
                
                ads = await scraper.scrape_ads(keywords=keywords)
                await scraper.close()
                
                # Check if stopped during scraping
                if self._stop_task:
                    await self._send_log("warning", "Task stopped by user", task_id)
                    return {"success": False, "error": "Stopped by user", "ads": ads, "count": len(ads), "stopped": True}
                
                await self._send_progress(task_id, 80, f"Found {len(ads)} ads...")
                self._emit_log(f"📊 Found {len(ads)} unique ads")
                await self._send_log("success", f"Found {len(ads)} unique ads", task_id)
                
                # Send scraped links to platform via API
                if ads and self._ws_client:
                    links_data = [
                        {
                            "url": ad.get("url"),
                            "title": ad.get("title"),
                            "advertiserName": ad.get("advertiser_name"),
                            "source": "meta_ads",
                            "searchKeyword": ad.get("keyword"),
                            "metadata": {
                                "scraped_at": ad.get("scraped_at"),
                                "description": ad.get("description")
                            }
                        }
                        for ad in ads if ad.get("url")
                    ]
                    
                    await self._send_progress(task_id, 90, "Sending links to platform...")
                    await self._send_log("info", f"Sending {len(links_data)} links to platform...", task_id)
                    
                    # Send links back via WebSocket
                    await self._ws_client.send_scraped_links(links_data, task_id=task_id)
                    self._emit_log(f"📤 Sent {len(links_data)} links to platform")
                    await self._send_log("success", f"Sent {len(links_data)} links to platform", task_id)
                
                await self._send_progress(task_id, 100, "Complete")
                
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
                await self._send_log("error", f"Unknown scrape source: {source}", task_id)
                return {"success": False, "error": f"Unknown scrape source: {source}"}
                
        except Exception as e:
            logger.error(f"Scrape error: {e}", exc_info=True)
            await self._send_log("error", f"Scrape error: {str(e)}", task_id)
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
        - stop_task: Stop specific task
        - cancel_task: Cancel specific task
        - restart: Restart the agent
        """
        cmd_type = params.get("type", command) if isinstance(params, dict) else command
        task_id = params.get("taskId") if isinstance(params, dict) else None
        
        logger.warning(f"📥 Received command: {cmd_type}, task_id: {task_id}")
        self._emit_log(f"📥 Received command: {cmd_type}")
        
        if cmd_type == "pause":
            self._set_status(AgentStatus.PAUSED)
            
        elif cmd_type == "resume":
            self._set_status(AgentStatus.CONNECTED)
            
        elif cmd_type in ["stop", "stop_task"]:
            logger.warning("🛑 STOP COMMAND RECEIVED - Setting task stop flag")
            self._stop_task = True
            self._emit_log("🛑 Stop requested - stopping current task...")
            # Send immediate feedback to UI
            await self._send_log("warning", "🛑 Stop command received - stopping task...", task_id)
            
        elif cmd_type == "cancel_task":
            logger.warning("❌ CANCEL COMMAND RECEIVED - Setting task stop flag")
            self._stop_task = True
            self._emit_log("❌ Cancel requested - stopping immediately...")
            # Send immediate feedback to UI
            await self._send_log("warning", "❌ Cancel command received - stopping immediately...", task_id)
            
        elif cmd_type == "restart":
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
        self._stop_agent = False
        self._stop_task = False
        
        self._emit_log("🚀 Starting InboxHunter Agent...")
        
        # Connect to platform
        connected = await self.connect_to_platform()
        
        if not connected:
            self._emit_log("⚠️ Running in offline mode")
            return
        
        # Main loop - keep connection alive and process tasks
        try:
            while not self._stop_agent:
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
        self._stop_agent = True
        self._stop_task = True  # Also stop any running task
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

