"""
Meta Ads Library scraper for extracting ad links.
"""

import asyncio
import re
import csv
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from playwright.async_api import async_playwright, Browser, Page
from loguru import logger

from src.config import Config
from src.automation.browser import ensure_browsers_installed


class MetaAdsLibraryScraper:
    """
    Scraper for Meta (Facebook) Ads Library.
    Extracts ad destination URLs from search results.
    """
    
    BASE_URL = "https://www.facebook.com/ads/library/"
    
    def __init__(self, config: Config, stop_check: callable = None):
        """
        Initialize Meta Ads Library scraper.
        
        Args:
            config: Application configuration
            stop_check: Optional callable that returns True if stop requested
        """
        self.config = config
        self.meta_config = config.sources.meta_ads_library
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self._stop_check = stop_check or (lambda: False)
        self._playwright = None
    
    async def initialize(self):
        """Initialize browser for scraping."""
        logger.info("Initializing Meta Ads Library scraper...")
        
        # Ensure browsers are installed (especially for PyInstaller builds)
        if not ensure_browsers_installed():
            raise RuntimeError(
                "Playwright browsers not installed. Please run: playwright install chromium"
            )
        
        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(
            headless=self.config.automation.headless
        )
        
        context = await self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        
        self.page = await context.new_page()
        logger.success("✅ Meta Ads Library scraper initialized")
    
    async def scrape_ads(self, keywords: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Scrape ads from Meta Ads Library.
        
        Args:
            keywords: List of keywords to search (uses config if None)
            
        Returns:
            List of ad data dictionaries
        """
        if not self.meta_config.enabled:
            logger.warning("Meta Ads Library scraping is disabled in config")
            return []
        
        keywords = keywords or self.meta_config.search_keywords
        all_ads = []
        
        for keyword in keywords:
            # Check if stop requested
            if self._stop_check():
                logger.info("Stop requested - aborting Meta Ads scraping")
                break
                
            logger.info(f"Scraping ads for keyword: {keyword}")
            ads = await self._scrape_keyword(keyword)
            all_ads.extend(ads)
            
            # Check stop before delay
            if self._stop_check():
                logger.info("Stop requested - aborting Meta Ads scraping")
                break
            
            # Add delay between keyword searches
            await asyncio.sleep(3)
        
        # Remove duplicates based on destination URL
        unique_ads = self._deduplicate_ads(all_ads)
        
        # Save to training.csv (only if we got any ads)
        if unique_ads and not self._stop_check():
            self._save_to_csv(unique_ads)
        
        if not self._stop_check():
            logger.success(f"✅ Scraped {len(unique_ads)} unique ads from Meta Ads Library")
        return unique_ads
    
    async def _scrape_keyword(self, keyword: str) -> List[Dict[str, Any]]:
        """
        Scrape ads for a specific keyword.
        
        Args:
            keyword: Search keyword
            
        Returns:
            List of ad data
        """
        ads = []
        
        try:
            # Build search URL
            search_url = (
                f"{self.BASE_URL}?active_status=active&"
                f"ad_type=all&country=US&q={keyword.replace(' ', '+')}&"
                f"search_type=keyword_unordered"
            )
            
            logger.info(f"Loading Meta Ads Library for keyword: {keyword}")
            logger.debug(f"URL: {search_url}")
            
            # Don't wait for networkidle - Meta's page is very dynamic
            await self.page.goto(search_url, wait_until="domcontentloaded", timeout=45000)
            
            # Wait for ads to appear
            logger.debug("Waiting for ads to load...")
            await asyncio.sleep(5)
            
            # Look for action buttons on ads
            try:
                # Wait for any action button to appear
                await self.page.wait_for_selector('a:has-text("Sign up"), a:has-text("Learn more"), a:has-text("Shop now")', timeout=10000)
                logger.debug("Found action buttons on ads")
            except:
                logger.warning("No action buttons found - page may not have loaded properly")
            
            # Scroll to load more ads
            await self._scroll_page(scrolls=2)
            
            # Extract URLs directly from action buttons
            ads = await self._extract_urls_from_action_buttons(keyword)
            
            if not ads:
                logger.warning(f"No ads extracted for keyword '{keyword}'")
            
        except Exception as e:
            logger.error(f"Error scraping keyword '{keyword}': {e}")
        
        return ads
    
    async def _scroll_page(self, scrolls: int = 2):
        """Scroll page to load more ads."""
        for i in range(scrolls):
            await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(3)
            logger.debug(f"Scrolled {i+1}/{scrolls} times")
    
    async def _extract_urls_from_action_buttons(self, keyword: str) -> List[Dict[str, Any]]:
        """
        Extract destination URLs from action buttons (Sign Up, Learn More, Shop Now, etc.).
        
        Args:
            keyword: Search keyword
            
        Returns:
            List of ad data
        """
        ads = []
        seen_urls = set()
        
        try:
            # Common action button text patterns
            action_patterns = [
                "Sign up", "Sign Up", "SIGN UP",
                "Learn more", "Learn More", "LEARN MORE",
                "Shop now", "Shop Now", "SHOP NOW",
                "Order now", "Order Now", "ORDER NOW",
                "Get started", "Get Started", "GET STARTED",
                "Visit profile", "Visit Profile",
                "Book now", "Book Now",
                "Download", "DOWNLOAD",
                "Apply now", "Apply Now",
                "Get offer", "Get Offer",
                "Join now", "Join Now",
                "Subscribe", "SUBSCRIBE"
            ]
            
            logger.info(f"Searching for action buttons on ad cards...")
            
            # Find all links that match action patterns
            for pattern in action_patterns:
                try:
                    buttons = await self.page.query_selector_all(f'a:has-text("{pattern}")')
                    logger.debug(f"Found {len(buttons)} '{pattern}' buttons")
                    
                    for button in buttons:
                        try:
                            href = await button.get_attribute("href")
                            if not href:
                                continue
                            
                            # Extract actual URL if it's a Facebook redirect
                            if "l.facebook.com" in href or "l.instagram.com" in href:
                                actual_url = self._extract_url_from_redirect(href)
                                if actual_url:
                                    href = actual_url
                            
                            # Validate and deduplicate
                            if href and self._is_valid_ad_url(href) and href not in seen_urls:
                                seen_urls.add(href)
                                ad_data = {
                                    "url": href,
                                    "title": f"{keyword} - {pattern}",
                                    "description": "",
                                    "keyword": keyword,
                                    "source": "meta",
                                    "scraped_at": datetime.utcnow().isoformat()
                                }
                                ads.append(ad_data)
                                logger.success(f"✅ Found ad URL: {href}")
                                
                                # Stop if we have enough
                                if len(ads) >= self.meta_config.ad_limit:
                                    return ads
                                    
                        except Exception as e:
                            logger.debug(f"Error extracting from button: {e}")
                            continue
                            
                except Exception as e:
                    logger.debug(f"Error finding '{pattern}' buttons: {e}")
                    continue
            
            logger.info(f"Extracted {len(ads)} unique ad URLs from action buttons")
            
        except Exception as e:
            logger.error(f"Error extracting URLs from action buttons: {e}")
        
        return ads
    
    
    async def _extract_ads_from_page(self, keyword: str) -> List[Dict[str, Any]]:
        """
        Extract ad information from the current page.
        
        Args:
            keyword: Search keyword used
            
        Returns:
            List of ad data dictionaries
        """
        ads = []
        
        try:
            # Wait for ad cards to load
            await asyncio.sleep(3)
            
            # Try multiple strategies to find ad destination URLs
            
            # Strategy 1: Look for "See Ad" or "Go to website" buttons/links
            see_ad_buttons = await self.page.query_selector_all('a[href*="l.facebook.com"], a[href*="l.instagram.com"]')
            logger.debug(f"Found {len(see_ad_buttons)} potential ad redirect links")
            
            for button in see_ad_buttons[:self.meta_config.ad_limit]:
                try:
                    href = await button.get_attribute("href")
                    if href and ("l.facebook.com" in href or "l.instagram.com" in href):
                        # Extract the actual destination URL from Facebook's redirect
                        actual_url = self._extract_url_from_redirect(href)
                        if actual_url and self._is_valid_ad_url(actual_url):
                            ad_data = {
                                "url": actual_url,
                                "title": keyword,
                                "description": "",
                                "keyword": keyword,
                                "source": "meta",
                                "scraped_at": datetime.utcnow().isoformat()
                            }
                            ads.append(ad_data)
                            logger.debug(f"Found ad URL: {actual_url}")
                except Exception as e:
                    logger.debug(f"Error extracting from button: {e}")
            
            # Strategy 2: Look for external links in ad content
            if len(ads) < 5:
                external_links = await self.page.query_selector_all('a[href^="http"]')
                for link in external_links:
                    try:
                        href = await link.get_attribute("href")
                        if href and self._is_valid_ad_url(href) and not any(ad["url"] == href for ad in ads):
                            # Check if this link is near ad content
                            text = await link.text_content() or ""
                            if any(word in text.lower() for word in ["learn", "shop", "sign up", "get", "join", "visit"]):
                                ad_data = {
                                    "url": href,
                                    "title": text[:200] if text else keyword,
                                    "description": "",
                                    "keyword": keyword,
                                    "source": "meta",
                                    "scraped_at": datetime.utcnow().isoformat()
                                }
                                ads.append(ad_data)
                                logger.debug(f"Found external ad URL: {href}")
                                
                                if len(ads) >= self.meta_config.ad_limit:
                                    break
                    except Exception as e:
                        logger.debug(f"Error extracting external link: {e}")
            
        except Exception as e:
            logger.error(f"Error extracting ads from page: {e}")
        
        return ads[:self.meta_config.ad_limit]
    
    def _extract_url_from_redirect(self, redirect_url: str) -> Optional[str]:
        """
        Extract actual destination URL from Facebook's redirect URL.
        
        Args:
            redirect_url: Facebook redirect URL (l.facebook.com or l.instagram.com)
            
        Returns:
            Actual destination URL or None
        """
        try:
            from urllib.parse import urlparse, parse_qs
            
            # Parse the redirect URL
            parsed = urlparse(redirect_url)
            
            # Look for 'u' parameter (common in Facebook redirects)
            if parsed.query:
                params = parse_qs(parsed.query)
                if 'u' in params:
                    return params['u'][0]
                # Sometimes it's in 'url' parameter
                if 'url' in params:
                    return params['url'][0]
            
            return None
        except Exception as e:
            logger.debug(f"Error extracting URL from redirect: {e}")
            return None
    
    async def _click_ads_and_extract_urls(self, keyword: str) -> List[Dict[str, Any]]:
        """
        Click on ads to reveal destination URLs.
        
        Args:
            keyword: Search keyword
            
        Returns:
            List of ad data
        """
        ads = []
        
        try:
            # Try to find and click "See more" or expand buttons
            expand_buttons = await self.page.query_selector_all('[aria-label*="See more"], [aria-label*="Show more"]')
            
            for i, button in enumerate(expand_buttons[:5]):  # Limit to first 5 ads
                try:
                    # Click to expand ad content
                    await button.click()
                    await asyncio.sleep(1)
                    
                    # Look for external links after expansion
                    parent = await button.query_selector('xpath=ancestor::div[contains(@class, "x1yztbdb")]')
                    if parent:
                        links = await parent.query_selector_all('a[href^="http"]')
                        for link in links:
                            href = await link.get_attribute("href")
                            if href and self._is_valid_ad_url(href):
                                actual_url = self._extract_url_from_redirect(href) if "l.facebook" in href else href
                                if actual_url:
                                    ad_data = {
                                        "url": actual_url,
                                        "title": keyword,
                                        "description": "",
                                        "keyword": keyword,
                                        "source": "meta",
                                        "scraped_at": datetime.utcnow().isoformat()
                                    }
                                    ads.append(ad_data)
                                    logger.debug(f"Extracted URL from expanded ad: {actual_url}")
                                    break
                except Exception as e:
                    logger.debug(f"Error clicking ad {i}: {e}")
                    continue
                
                if len(ads) >= self.meta_config.ad_limit:
                    break
                    
        except Exception as e:
            logger.debug(f"Error in click and extract: {e}")
        
        return ads
    
    def _is_valid_ad_url(self, url: str) -> bool:
        """
        Check if URL is a valid ad destination (not Facebook internal).
        
        Args:
            url: URL to check
            
        Returns:
            True if valid ad URL
        """
        if not url or not url.startswith("http"):
            return False
        
        # Exclude Facebook/Meta internal URLs and common non-ad links
        exclude_domains = [
            "facebook.com",
            "fb.com", 
            "instagram.com",
            "messenger.com",
            "meta.com",
            "fbcdn.net",
            "youtube.com",
            "youtu.be",
            "twitter.com",
            "linkedin.com",
            "tiktok.com"
        ]
        
        # Exclude specific paths that are never ads
        exclude_paths = [
            "/terms",
            "/privacy",
            "/help",
            "/about",
            "/legal",
            "/support",
            "/ads-transparency"
        ]
        
        url_lower = url.lower()
        
        # Check excluded domains
        for domain in exclude_domains:
            if domain in url_lower:
                return False
        
        # Check excluded paths
        for path in exclude_paths:
            if path in url_lower:
                return False
        
        # Must have a valid domain structure
        if url.count('.') < 1:
            return False
        
        return True
    
    def _deduplicate_ads(self, ads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Remove duplicate ads based on URL.
        
        Args:
            ads: List of ad data
            
        Returns:
            List of unique ads
        """
        seen_urls = set()
        unique_ads = []
        
        for ad in ads:
            url = ad.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_ads.append(ad)
        
        return unique_ads
    
    def _save_to_csv(self, ads: List[Dict[str, Any]]):
        """Save scraped ads to training.csv"""
        try:
            csv_path = Path("data/training.csv")
            
            # Check if file exists and has data
            file_exists = csv_path.exists() and csv_path.stat().st_size > 0
            
            with open(csv_path, 'a', newline='', encoding='utf-8') as f:
                fieldnames = ['url', 'title', 'description', 'keyword', 'source', 'scraped_at']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                
                # Write header only if file is new/empty
                if not file_exists:
                    writer.writeheader()
                
                # Write ads
                for ad in ads:
                    writer.writerow({
                        'url': ad.get('url', ''),
                        'title': ad.get('title', ''),
                        'description': ad.get('description', ''),
                        'keyword': ad.get('keyword', ''),
                        'source': ad.get('source', 'meta'),
                        'scraped_at': ad.get('scraped_at', datetime.utcnow().isoformat())
                    })
            
            logger.success(f"✅ Saved {len(ads)} ads to training.csv")
        except Exception as e:
            logger.error(f"Failed to save ads to CSV: {e}")
    
    async def close(self):
        """Close browser and clean up."""
        try:
            if self.browser:
                await self.browser.close()
                self.browser = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
            logger.info("Meta Ads Library scraper closed")
        except Exception as e:
            logger.error(f"Error closing scraper: {e}")


class MetaAdsAPIClient:
    """
    Alternative implementation using Meta Graph API.
    Requires proper API access token and permissions.
    """
    
    BASE_API_URL = "https://graph.facebook.com/v18.0"
    
    def __init__(self, access_token: str):
        """
        Initialize Meta API client.
        
        Args:
            access_token: Meta API access token
        """
        self.access_token = access_token
        logger.info("Meta Ads API client initialized")
    
    async def search_ads(self, keywords: List[str]) -> List[Dict[str, Any]]:
        """
        Search for ads using Meta Graph API.
        
        Note: This requires proper API setup and permissions.
        The Ad Library API has specific requirements and rate limits.
        
        Args:
            keywords: Search keywords
            
        Returns:
            List of ad data
        """
        # Placeholder for API implementation
        logger.warning("Meta Graph API implementation requires proper setup")
        logger.info("Using browser scraping method instead")
        return []

