"""
Main bot orchestrator that coordinates all components.
"""

import asyncio
import time
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from loguru import logger

from src.config import Config, get_config
from src.database import DatabaseOperations, SignUp
from src.automation import BrowserAutomation, FormFiller
from src.automation.llm_analyzer import LLMPageAnalyzer
from src.automation.agent_orchestrator import AIAgentOrchestrator
from src.scrapers import MetaAdsLibraryScraper, ExtensionDataParser, CSVDataParser
from src.captcha import CaptchaSolver
from src.utils.helpers import random_delay


class ReverseOutreachBot:
    """
    Main orchestrator for the Reverse Outreach automation bot.
    Coordinates scraping, form filling, CAPTCHA solving, and tracking.
    """
    
    def __init__(self, config: Optional[Config] = None, stop_check: callable = None):
        """
        Initialize the bot.
        
        Args:
            config: Configuration object (loads from file if None)
            stop_check: Optional callable that returns True if stop requested
        """
        self.config = config or get_config()
        self.db = DatabaseOperations(self.config.database.url)
        self._stop_check = stop_check or (lambda: False)
        
        # Initialize components
        self.browser: Optional[BrowserAutomation] = None
        self.captcha_solver: Optional[CaptchaSolver] = None
        
        # Statistics
        self.stats = {
            "total_attempts": 0,
            "successful_signups": 0,
            "failed_attempts": 0,
            "duplicates_skipped": 0,
            "captchas_solved": 0,
            "errors": []
        }
        
        logger.info("🤖 Reverse Outreach Bot initialized")
    
    async def run(self, source: Optional[str] = None, max_signups: Optional[int] = None):
        """
        Main bot execution loop.
        
        Args:
            source: Specific source to process ('meta', 'extensions', or None for enabled sources)
            max_signups: Maximum number of sign-ups to process (None for unlimited)
        """
        logger.info("🚀 Starting Reverse Outreach Bot...")
        logger.info(f"Source: {source or 'enabled sources'}, Max signups: {max_signups or 'unlimited'}")
        
        start_time = time.time()
        
        try:
            # Initialize browser
            self.browser = BrowserAutomation(self.config)
            await self.browser.initialize()
            
            # Initialize CAPTCHA solver
            self._initialize_captcha_solver()
            
            # Get ads from sources
            ads = await self._get_ads(source)
            
            if not ads:
                logger.warning("⚠️ No ads found from sources")
                return
            
            logger.info(f"📋 Found {len(ads)} ads to process")
            
            # Process each ad
            processed = 0
            consecutive_failures = 0
            
            for i, ad in enumerate(ads, 1):
                # Check if we've reached max signups
                if max_signups and processed >= max_signups:
                    logger.info(f"✅ Reached maximum sign-ups limit: {max_signups}")
                    break
                
                # Check consecutive failures
                if consecutive_failures >= self.config.rate_limiting.max_consecutive_failures:
                    logger.error(f"❌ Too many consecutive failures ({consecutive_failures})")
                    logger.info(f"Cooling down for {self.config.rate_limiting.cooldown_after_failures}s...")
                    await asyncio.sleep(self.config.rate_limiting.cooldown_after_failures)
                    consecutive_failures = 0
                
                # Check rate limiting
                await self._check_rate_limits()
                
                logger.info(f"\n{'='*60}")
                logger.info(f"Processing ad {i}/{len(ads)}")
                logger.info(f"URL: {ad.get('url', 'N/A')}")
                logger.info(f"Source: {ad.get('source', 'N/A')}")
                logger.info(f"{'='*60}")
                
                # Process the ad
                success = await self._process_ad(ad)
                
                if success:
                    processed += 1
                    consecutive_failures = 0
                    logger.success(f"✅ Successfully signed up ({processed} total)")
                else:
                    consecutive_failures += 1
                    logger.warning(f"⚠️ Failed to sign up ({consecutive_failures} consecutive failures)")
                
                # Delay between sign-ups
                if i < len(ads):
                    delay = random_delay(
                        *self.config.rate_limiting.delay_between_signups
                    )
                    logger.info(f"⏳ Waiting {delay:.1f}s before next ad...")
            
            # Print summary
            elapsed_time = time.time() - start_time
            self._print_summary(elapsed_time)
            
        except KeyboardInterrupt:
            logger.warning("⚠️ Bot stopped by user")
        except Exception as e:
            logger.error(f"❌ Fatal error: {e}", exc_info=True)
        finally:
            # Cleanup
            await self._cleanup()
    
    async def _get_ads(self, source: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get ads from configured sources.
        
        Args:
            source: Specific source to use or None for enabled sources
            
        Returns:
            List of ad data dictionaries
        """
        all_ads = []
        
        # Meta Ads Library (primary source for MVP)
        if (source is None or source == "meta") and self.config.sources.meta_ads_library.enabled:
            logger.info("📡 Scraping Meta Ads Library...")
            try:
                scraper = MetaAdsLibraryScraper(self.config)
                await scraper.initialize()
                meta_ads = await scraper.scrape_ads()
                all_ads.extend(meta_ads)
                await scraper.close()
                logger.success(f"✅ Found {len(meta_ads)} ads from Meta Ads Library")
            except Exception as e:
                logger.error(f"❌ Error scraping Meta Ads Library: {e}")
        
        # Training CSV (if enabled or explicitly requested)
        if (source is None or source == "csv") and self.config.sources.csv_data.enabled:
            logger.info("📂 Loading ads from training.csv...")
            try:
                parser = CSVDataParser(self.config)
                csv_ads = parser.parse()
                all_ads.extend(csv_ads)
                logger.success(f"✅ Found {len(csv_ads)} ads from training.csv")
            except Exception as e:
                logger.error(f"❌ Error parsing CSV data: {e}")
        
        # Browser extensions (only if explicitly requested or enabled)
        if source == "extensions":
            logger.info("📂 Parsing browser extension data...")
            try:
                parser = ExtensionDataParser(self.config)
                extension_ads = parser.parse_all()
                all_ads.extend(extension_ads)
            except Exception as e:
                logger.error(f"❌ Error parsing extension data: {e}")
        
        # Filter out already processed URLs
        new_ads = []
        for ad in all_ads:
            if not self.db.is_url_processed(ad.get("url", "")):
                new_ads.append(ad)
            else:
                self.stats["duplicates_skipped"] += 1
                logger.debug(f"Skipping duplicate: {ad.get('url', '')}")
        
        logger.info(f"📋 {len(new_ads)} new ads, {self.stats['duplicates_skipped']} duplicates skipped")
        
        return new_ads
    
    async def _process_ad(self, ad: Dict[str, Any]) -> bool:
        """
        Process a single ad (navigate, fill form, submit).
        
        Args:
            ad: Ad data dictionary
            
        Returns:
            True if successful, False otherwise
        """
        # Check stop at start
        if self._stop_check():
            logger.info("⏹ Stop requested - skipping ad processing")
            return False
        
        self.stats["total_attempts"] += 1
        process_start = time.time()
        
        ad_url = ad.get("url", "")
        ad_source = ad.get("source", "unknown")
        
        signup_data = {
            "ad_url": ad_url,
            "ad_source": ad_source,
            "ad_title": ad.get("title", ""),
            "ad_description": ad.get("description", ""),
            "status": "failed",
            "attempts_count": 1
        }
        
        try:
            # Check stop before navigation
            if self._stop_check():
                logger.info("⏹ Stop requested - aborting")
                return False
            
            # Navigate to landing page
            logger.info(f"🌐 Navigating to landing page...")
            navigation_success = await self.browser.navigate(ad_url)
            
            if not navigation_success:
                await self._record_error(ad_url, ad_source, "navigation_failed", "Failed to load page")
                return False
            
            # Check stop after navigation
            if self._stop_check():
                logger.info("⏹ Stop requested - aborting after navigation")
                return False
            
            signup_data["landing_url"] = self.browser.page.url
            
            # Detect platform
            platform = await self.browser.detect_platform()
            signup_data["detected_platform"] = platform
            logger.info(f"🔍 Detected platform: {platform}")
            
            # Check for CAPTCHA
            page_content = await self.browser.get_page_content()
            captcha_info = await self._handle_captcha(page_content, self.browser.page.url)
            
            if captcha_info:
                signup_data["captcha_encountered"] = True
                signup_data["captcha_type"] = captcha_info.get("captcha_type", "")
                signup_data["captcha_solved"] = captcha_info.get("solved", False)
                
                if not captcha_info.get("solved", False):
                    await self._record_error(ad_url, ad_source, "captcha_failed", "Failed to solve CAPTCHA")
                    return False
            
            # Use AI Agent with continuous reasoning loop
            logger.info("🤖 Starting AI Agent with continuous reasoning loop...")
            
            # Check if LLM is enabled
            use_llm = self.config.llm.enabled if hasattr(self.config, 'llm') else False
            llm_provider = self.config.llm.provider if use_llm else "none"
            llm_config = {
                'api_key': self.config.llm.api_key if use_llm else None,
                'model': self.config.llm.model if use_llm else 'gpt-4o'
            } if use_llm else {}
            
            # Prepare phone data (support both old and new format)
            phone_data = self.config.credentials.phone
            if isinstance(phone_data, str):
                # Old format: single string
                phone_creds = {
                    'full': phone_data,
                    'country_code': phone_data[:2] if phone_data.startswith('+') else '+1',
                    'number': phone_data[2:] if phone_data.startswith('+') else phone_data
                }
            else:
                # New format: PhoneConfig object
                phone_creds = {
                    'full': phone_data.full,
                    'country_code': phone_data.country_code,
                    'number': phone_data.number
                }
            
            # Create AI Agent with CAPTCHA API key
            captcha_api_key = None
            if self.captcha_solver:
                captcha_api_key = self.config.captcha.api_keys.get('twocaptcha') or self.config.captcha.api_keys.get('2captcha')
            
            agent = AIAgentOrchestrator(
                page=self.browser.page,
                credentials={
                    'email': self.config.credentials.email,
                    'first_name': self.config.credentials.first_name,
                    'last_name': self.config.credentials.last_name,
                    'full_name': self.config.credentials.full_name or f"{self.config.credentials.first_name} {self.config.credentials.last_name}".strip(),
                    'phone': phone_creds,
                    '_captcha_api_key': captcha_api_key  # Pass CAPTCHA API key
                },
                llm_provider=llm_provider,
                llm_config=llm_config,
                stop_check=self._stop_check  # Pass stop check callback
            )
            
            # Execute agent reasoning loop
            agent_result = await agent.execute_signup()
            
            if not agent_result["success"]:
                await self._record_error(ad_url, ad_source, "agent_failed", 
                                        f"AI Agent failed. Errors: {agent_result['errors']}")
                screenshot = await self.browser.take_screenshot("agent_error")
                return False
            
            # Convert list to JSON string for database
            import json
            signup_data["form_fields_filled"] = json.dumps(agent_result["fields_filled"])
            # Note: agent_steps and agent_actions stored in logs, not DB (would need schema update)
            
            # Wait for potential redirect/confirmation
            await asyncio.sleep(3)
            
            # Check if we were redirected (sign of success)
            final_url = self.browser.page.url
            if final_url != signup_data["landing_url"]:
                logger.info(f"Redirected to: {final_url}")
                signup_data["status"] = "success"
            else:
                # Look for success indicators on same page
                page_content = await self.browser.page.text_content("body") or ""
                if any(word in page_content.lower() for word in ["thank", "success", "confirm", "submitted"]):
                    signup_data["status"] = "success"
                else:
                    signup_data["status"] = "pending"
            
            signup_data["processing_time"] = time.time() - process_start
            
            # Save to database
            self.db.add_signup(signup_data)
            
            self.stats["successful_signups"] += 1
            if captcha_info and captcha_info.get("solved"):
                self.stats["captchas_solved"] += 1
            
            logger.success(f"✅ Sign-up successful!")
            return True
                
        except Exception as e:
            logger.error(f"Error processing ad: {e}", exc_info=True)
            await self._record_error(ad_url, ad_source, "processing_error", str(e))
            
            # Take error screenshot
            if self.config.error_handling.screenshot_on_error:
                try:
                    await self.browser.take_screenshot("processing_error")
                except:
                    pass
            
            self.stats["failed_attempts"] += 1
            return False
    
    async def _handle_captcha(self, page_content: str, page_url: str) -> Optional[Dict[str, Any]]:
        """
        Detect and solve CAPTCHA if present.
        
        Args:
            page_content: HTML content of the page
            page_url: Current page URL
            
        Returns:
            Dictionary with CAPTCHA info or None if no CAPTCHA
        """
        if not self.captcha_solver:
            return None
        
        logger.info("🔍 Checking for CAPTCHA...")
        
        captcha_info = self.captcha_solver.detect_captcha_type(page_content)
        
        if not captcha_info:
            logger.info("✓ No CAPTCHA detected")
            return None
        
        captcha_type = captcha_info.get("captcha_type", "")
        sitekey = captcha_info.get("sitekey", "")
        
        logger.warning(f"⚠️ CAPTCHA detected: {captcha_type}")
        logger.info(f"Site key: {sitekey}")
        
        # Solve CAPTCHA
        logger.info("🔓 Solving CAPTCHA...")
        
        token = None
        if captcha_type == "recaptcha_v2":
            token = self.captcha_solver.solve_recaptcha_v2(sitekey, page_url)
        elif captcha_type == "recaptcha_v3":
            token = self.captcha_solver.solve_recaptcha_v3(sitekey, page_url)
        elif captcha_type == "hcaptcha":
            token = self.captcha_solver.solve_hcaptcha(sitekey, page_url)
        
        if token:
            # Inject token into page
            await self._inject_captcha_token(captcha_type, token)
            captcha_info["solved"] = True
            captcha_info["token"] = token
            logger.success("✅ CAPTCHA solved successfully")
        else:
            captcha_info["solved"] = False
            logger.error("❌ Failed to solve CAPTCHA")
        
        return captcha_info
    
    async def _inject_captcha_token(self, captcha_type: str, token: str):
        """
        Inject CAPTCHA solution token into the page.
        
        Args:
            captcha_type: Type of CAPTCHA
            token: Solution token
        """
        try:
            if "recaptcha" in captcha_type:
                # Inject into reCAPTCHA response field
                await self.browser.page.evaluate(f"""
                    document.getElementById('g-recaptcha-response').innerHTML = '{token}';
                    if (typeof grecaptcha !== 'undefined') {{
                        grecaptcha.getResponse = function() {{ return '{token}'; }};
                    }}
                """)
            elif captcha_type == "hcaptcha":
                # Inject into hCaptcha response field
                await self.browser.page.evaluate(f"""
                    document.querySelector('[name="h-captcha-response"]').value = '{token}';
                """)
            
            logger.debug("CAPTCHA token injected")
            
        except Exception as e:
            logger.warning(f"Could not inject CAPTCHA token: {e}")
    
    def _initialize_captcha_solver(self):
        """Initialize CAPTCHA solver with configured service."""
        captcha_config = self.config.captcha
        service = captcha_config.service
        
        # Try multiple key names (twocaptcha, 2captcha)
        api_key = (captcha_config.api_keys.get('twocaptcha') or 
                  captcha_config.api_keys.get('2captcha') or
                  captcha_config.api_keys.get(service.replace("captcha", "").strip()))
        
        if not api_key or api_key.startswith("YOUR_"):
            logger.warning("⚠️ CAPTCHA solver not configured (no valid API key)")
            logger.info("   Set 'twocaptcha' API key in config.yaml to enable CAPTCHA solving")
            self.captcha_solver = None
            return
        
        self.captcha_solver = CaptchaSolver(
            service=service,
            api_key=api_key,
            timeout=captcha_config.timeout,
            retry_attempts=captcha_config.retry_attempts
        )
        
        # Check balance
        balance = self.captcha_solver.get_balance()
        if balance:
            logger.info(f"💰 CAPTCHA service balance: ${balance:.2f}")
    
    async def _check_rate_limits(self):
        """Check and enforce rate limits."""
        stats = self.db.get_today_stats()
        
        if not stats:
            return
        
        rate_config = self.config.rate_limiting
        
        # Check hourly limit
        # (Simplified - in production, track per-hour separately)
        if stats.successful_signups >= rate_config.max_signups_per_day:
            logger.warning("⚠️ Daily sign-up limit reached")
            raise Exception("Daily sign-up limit reached")
    
    async def _record_error(self, ad_url: str, ad_source: str, error_type: str, message: str):
        """Record an error to the database."""
        error_data = {
            "ad_url": ad_url,
            "ad_source": ad_source,
            "error_type": error_type,
            "error_message": message,
            "page_url": self.browser.page.url if self.browser and self.browser.page else ad_url
        }
        
        self.db.add_error(error_data)
        self.stats["errors"].append(error_type)
    
    def _print_summary(self, elapsed_time: float):
        """Print execution summary."""
        logger.info("\n" + "="*60)
        logger.info("📊 EXECUTION SUMMARY")
        logger.info("="*60)
        logger.info(f"⏱️  Total time: {elapsed_time:.1f}s ({elapsed_time/60:.1f}m)")
        logger.info(f"📋 Total attempts: {self.stats['total_attempts']}")
        logger.info(f"✅ Successful sign-ups: {self.stats['successful_signups']}")
        logger.info(f"❌ Failed attempts: {self.stats['failed_attempts']}")
        logger.info(f"⏭️  Duplicates skipped: {self.stats['duplicates_skipped']}")
        logger.info(f"🔓 CAPTCHAs solved: {self.stats['captchas_solved']}")
        
        if self.stats['total_attempts'] > 0:
            success_rate = (self.stats['successful_signups'] / self.stats['total_attempts']) * 100
            logger.info(f"📈 Success rate: {success_rate:.1f}%")
        
        if self.stats['errors']:
            from collections import Counter
            error_counts = Counter(self.stats['errors'])
            logger.info("\n🔴 Errors breakdown:")
            for error, count in error_counts.most_common():
                logger.info(f"   {error}: {count}")
        
        logger.info("="*60)
    
    async def _cleanup(self):
        """Cleanup resources."""
        logger.info("🧹 Cleaning up...")
        
        if self.browser:
            await self.browser.close()
        
        logger.info("👋 Bot stopped")

