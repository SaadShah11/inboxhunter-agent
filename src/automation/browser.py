"""
Advanced browser automation with state-of-the-art stealth features.
Implements user agent rotation, fingerprint randomization, and anti-detection bypasses.
"""

import asyncio
import random
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright
from loguru import logger

from src.config import Config
from src.utils.helpers import random_delay
from src.utils.stealth import (
    get_session_profile, 
    get_stealth_scripts, 
    get_context_options,
    reset_session_profile,
    BrowserProfile
)


class BrowserAutomation:
    """
    Browser automation with state-of-the-art stealth features.
    Designed to bypass reCAPTCHA v3, ClickFunnels, GoHighLevel, and Cloudflare detection.
    
    Features:
    - User agent rotation with modern browser versions
    - Consistent fingerprint generation
    - WebGL/Canvas fingerprint spoofing
    - Timezone/Locale matching
    - Headless detection bypass
    """
    
    def __init__(self, config: Config):
        """
        Initialize browser automation.
        
        Args:
            config: Application configuration
        """
        self.config = config
        self.automation_config = config.automation
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.profile: Optional[BrowserProfile] = None
        
    async def initialize(self):
        """Initialize Playwright and browser with advanced stealth."""
        logger.info("🚀 Initializing browser automation with advanced stealth...")
        
        # Generate consistent browser profile for this session
        self.profile = get_session_profile()
        logger.info(f"📱 Browser Profile: {self.profile.user_agent[:60]}...")
        logger.info(f"🌍 Timezone: {self.profile.timezone} | Screen: {self.profile.screen_resolution}")
        
        self.playwright = await async_playwright().start()
        
        # Browser launch options with enhanced stealth
        launch_options = {
            "headless": self.automation_config.headless,
            "args": [
                # Core anti-detection
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-site-isolation-trials",
                
                # Fingerprint consistency
                f"--window-size={self.profile.screen_resolution[0]},{self.profile.screen_resolution[1]}",
                "--start-maximized",
                
                # Performance & stability
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-accelerated-2d-canvas",
                "--disable-gpu",
                
                # Additional stealth
                "--disable-features=TranslateUI",
                "--disable-features=BlinkGenPropertyTrees",
                "--disable-ipc-flooding-protection",
                "--disable-renderer-backgrounding",
                "--enable-features=NetworkService,NetworkServiceInProcess",
                "--force-color-profile=srgb",
                
                # Reduce resource usage
                "--disable-background-networking",
                "--disable-default-apps",
                "--disable-extensions",
                "--disable-sync",
                "--metrics-recording-only",
                "--mute-audio",
                "--no-first-run",
            ]
        }
        
        # Launch browser based on config
        if self.automation_config.browser == "chromium":
            self.browser = await self.playwright.chromium.launch(**launch_options)
        elif self.automation_config.browser == "firefox":
            self.browser = await self.playwright.firefox.launch(**launch_options)
        elif self.automation_config.browser == "webkit":
            self.browser = await self.playwright.webkit.launch(**launch_options)
        else:
            raise ValueError(f"Unsupported browser: {self.automation_config.browser}")
        
        # Create context with stealth settings
        context_options = await self._get_stealth_context_options()
        self.context = await self.browser.new_context(**context_options)
        
        # Apply comprehensive stealth scripts
        await self._apply_stealth_scripts()
        
        # Create page
        self.page = await self.context.new_page()
        
        # Set up page event handlers
        await self._setup_page_handlers()
        
        logger.success("✅ Browser initialized with state-of-the-art stealth features")
    
    async def _get_stealth_context_options(self) -> Dict[str, Any]:
        """Get browser context options with advanced stealth features."""
        # Build proxy config if enabled
        proxy_config = None
        if self.config.proxy.enabled:
            proxy_config = {
                "server": self.config.proxy.url,
                "username": self.config.proxy.username,
                "password": self.config.proxy.password
            }
        
        # Use the stealth module to get consistent, randomized options
        options = get_context_options(self.profile, proxy_config)
        
        # Override viewport if specified in config and different from profile
        if self.automation_config.user_agent != "auto":
            options["user_agent"] = self.automation_config.user_agent
        
        return options
    
    async def _apply_stealth_scripts(self):
        """Apply comprehensive JavaScript patches to evade detection."""
        if not self.automation_config.stealth.enabled:
            logger.warning("⚠️ Stealth mode is disabled - bot may be detected!")
            return
        
        # Get comprehensive stealth scripts from the stealth module
        stealth_script = get_stealth_scripts(self.profile)
        
        # Apply all stealth scripts before any page load
        await self.context.add_init_script(stealth_script)
        
        logger.debug("✅ Comprehensive stealth patches applied (webdriver, plugins, WebGL, screen, etc.)")
    
    async def _setup_page_handlers(self):
        """Set up page event handlers."""
        # Log console messages
        self.page.on("console", lambda msg: logger.debug(f"Browser console: {msg.text}"))
        
        # Log page errors
        self.page.on("pageerror", lambda err: logger.error(f"Page error: {err}"))
        
        # Handle dialogs
        self.page.on("dialog", lambda dialog: asyncio.create_task(dialog.accept()))
    
    async def navigate(self, url: str, wait_until: str = "domcontentloaded") -> bool:
        """
        Navigate to a URL with realistic behavior.
        
        Args:
            url: URL to navigate to
            wait_until: Wait condition ('load', 'domcontentloaded', 'networkidle')
            
        Returns:
            True if navigation successful, False otherwise
        """
        try:
            logger.info(f"Navigating to: {url}")
            
            # Add small random delay before navigation
            await asyncio.sleep(random.uniform(0.5, 1.5))
            
            # Use domcontentloaded instead of networkidle for faster, more reliable loading
            response = await self.page.goto(
                url,
                wait_until=wait_until,
                timeout=45000  # Increased timeout for slow pages
            )
            
            # Wait a bit for dynamic content to load
            await asyncio.sleep(2)
            
            if response and response.ok:
                logger.success(f"✅ Successfully loaded: {url}")
                
                # Simulate human-like page viewing
                await self._simulate_page_viewing()
                
                return True
            else:
                logger.warning(f"Page loaded with status: {response.status if response else 'No response'}")
                # Even if status is not 200, page might still be usable
                await self._simulate_page_viewing()
                return True
                
        except Exception as e:
            logger.error(f"Navigation error: {e}")
            return False
    
    async def _simulate_page_viewing(self):
        """Simulate human viewing the page."""
        # Random scroll
        scroll_amount = random.randint(100, 500)
        await self.page.evaluate(f"window.scrollBy(0, {scroll_amount})")
        await asyncio.sleep(random.uniform(0.5, 1.5))
        
        # Random mouse movement
        if self.automation_config.behavior.mouse_movements:
            for _ in range(random.randint(1, 3)):
                x = random.randint(100, 1000)
                y = random.randint(100, 800)
                await self.page.mouse.move(x, y)
                await asyncio.sleep(random.uniform(0.1, 0.3))
    
    async def human_type(self, selector: str, text: str, clear_first: bool = True) -> bool:
        """
        Type text with human-like behavior.
        
        Args:
            selector: Element selector
            text: Text to type
            clear_first: Whether to clear the field first
            
        Returns:
            True if successful, False otherwise
        """
        try:
            element = await self.page.wait_for_selector(
                selector,
                timeout=self.automation_config.timeouts.element_wait * 1000
            )
            
            if not element:
                logger.error(f"Element not found: {selector}")
                return False
            
            # Click to focus
            await element.click()
            await asyncio.sleep(random.uniform(0.2, 0.5))
            
            # Clear if needed
            if clear_first:
                await element.fill("")
                await asyncio.sleep(random.uniform(0.1, 0.3))
            
            # Type with human-like delays
            behavior_config = self.automation_config.behavior
            
            for i, char in enumerate(text):
                # Check if we should make a typo
                if behavior_config.typing_mistakes and random.random() < behavior_config.mistake_probability:
                    # Type wrong character
                    from src.utils.helpers import get_adjacent_key
                    wrong_char = get_adjacent_key(char)
                    await element.type(wrong_char, delay=random.uniform(
                        behavior_config.typing_delay_min * 1000,
                        behavior_config.typing_delay_max * 1000
                    ))
                    await asyncio.sleep(random.uniform(0.1, 0.3))
                    
                    # Backspace to correct
                    await self.page.keyboard.press("Backspace")
                    await asyncio.sleep(random.uniform(0.1, 0.2))
                
                # Type correct character
                delay = random.uniform(
                    behavior_config.typing_delay_min * 1000,
                    behavior_config.typing_delay_max * 1000
                )
                await element.type(char, delay=delay)
                
                # Occasional longer pause (thinking)
                if i > 0 and i % random.randint(5, 10) == 0:
                    await asyncio.sleep(random.uniform(0.3, 0.8))
            
            logger.debug(f"Typed text into {selector}")
            return True
            
        except Exception as e:
            logger.error(f"Error typing into {selector}: {e}")
            return False
    
    async def human_click(self, selector: str) -> bool:
        """
        Click an element with human-like behavior.
        
        Args:
            selector: Element selector
            
        Returns:
            True if successful, False otherwise
        """
        try:
            element = await self.page.wait_for_selector(
                selector,
                timeout=self.automation_config.timeouts.element_wait * 1000
            )
            
            if not element:
                logger.error(f"Element not found: {selector}")
                return False
            
            # Move mouse to element
            box = await element.bounding_box()
            if box:
                # Click at random position within element
                x = box["x"] + random.uniform(box["width"] * 0.3, box["width"] * 0.7)
                y = box["y"] + random.uniform(box["height"] * 0.3, box["height"] * 0.7)
                
                await self.page.mouse.move(x, y)
                await asyncio.sleep(random.uniform(0.1, 0.3))
            
            # Click
            await element.click()
            await asyncio.sleep(random.uniform(0.3, 0.7))
            
            logger.debug(f"Clicked {selector}")
            return True
            
        except Exception as e:
            logger.error(f"Error clicking {selector}: {e}")
            return False
    
    async def detect_platform(self) -> Optional[str]:
        """
        Detect the funnel platform (ClickFunnels, GoHighLevel, etc.).
        
        Returns:
            Platform name or None if unknown
        """
        try:
            content = await self.page.content()
            url = self.page.url
            
            # ClickFunnels detection
            if "clickfunnels" in url.lower() or "clickfunnels" in content.lower():
                return "ClickFunnels"
            
            # GoHighLevel detection
            if "gohighlevel" in url.lower() or "ghl" in url.lower():
                return "GoHighLevel"
            if "msgsndr.com" in url.lower() or "leadconnectorhq.com" in url.lower():
                return "GoHighLevel"
            
            # Kartra detection
            if "kartra" in url.lower() or "kartra" in content.lower():
                return "Kartra"
            
            # Leadpages detection
            if "leadpages" in url.lower() or "leadpages" in content.lower():
                return "Leadpages"
            
            # Unbounce detection
            if "unbounce" in url.lower() or "unbounce" in content.lower():
                return "Unbounce"
            
            return "Unknown"
            
        except Exception as e:
            logger.error(f"Error detecting platform: {e}")
            return None
    
    async def take_screenshot(self, name: str = "screenshot") -> Optional[str]:
        """
        Take a screenshot of the current page.
        
        Args:
            name: Screenshot name
            
        Returns:
            Path to screenshot file or None if failed
        """
        try:
            screenshots_dir = Path("data/screenshots")
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{name}_{timestamp}.png"
            filepath = screenshots_dir / filename
            
            await self.page.screenshot(path=str(filepath), full_page=True)
            logger.info(f"Screenshot saved: {filepath}")
            
            return str(filepath)
            
        except Exception as e:
            logger.error(f"Error taking screenshot: {e}")
            return None
    
    async def get_page_content(self) -> Optional[str]:
        """Get current page HTML content."""
        try:
            return await self.page.content()
        except Exception as e:
            logger.error(f"Error getting page content: {e}")
            return None
    
    async def close(self):
        """Close browser and clean up resources."""
        try:
            if self.page:
                await self.page.close()
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            
            logger.info("Browser closed")
            
        except Exception as e:
            logger.error(f"Error closing browser: {e}")

