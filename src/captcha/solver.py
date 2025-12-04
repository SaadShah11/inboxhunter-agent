"""
CAPTCHA solving service integration supporting 2Captcha, Anti-Captcha, and Cloudflare Turnstile.
Implements async solving and modern CAPTCHA types.
"""

import asyncio
import time
import re
from typing import Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor
from loguru import logger

try:
    from twocaptcha import TwoCaptcha
    TWOCAPTCHA_AVAILABLE = True
except ImportError:
    TWOCAPTCHA_AVAILABLE = False
    logger.warning("2Captcha library not available")

try:
    from anticaptchaofficial.recaptchav3proxyless import *
    ANTICAPTCHA_AVAILABLE = True
except ImportError:
    ANTICAPTCHA_AVAILABLE = False
    logger.warning("Anti-Captcha library not available")

# Thread pool for running sync CAPTCHA solving in async context
_executor = ThreadPoolExecutor(max_workers=3)


class CaptchaSolver:
    """
    Unified interface for CAPTCHA solving services.
    Supports 2Captcha and Anti-Captcha for reCAPTCHA v2, v3, hCaptcha, etc.
    """
    
    def __init__(self, service: str, api_key: str, timeout: int = 120, retry_attempts: int = 3):
        """
        Initialize CAPTCHA solver.
        
        Args:
            service: Service name ('2captcha' or 'anticaptcha')
            api_key: API key for the service
            timeout: Maximum time to wait for solution (seconds)
            retry_attempts: Number of retry attempts on failure
        """
        self.service = service.lower()
        self.api_key = api_key
        self.timeout = timeout
        self.retry_attempts = retry_attempts
        
        # Initialize the appropriate solver
        if self.service == "2captcha" and TWOCAPTCHA_AVAILABLE:
            self.solver = TwoCaptcha(api_key)
            logger.info("2Captcha solver initialized")
        elif self.service == "anticaptcha" and ANTICAPTCHA_AVAILABLE:
            self.solver = None  # Will be created per-request based on CAPTCHA type
            logger.info("Anti-Captcha solver initialized")
        else:
            logger.error(f"CAPTCHA service '{service}' not available or not supported")
            self.solver = None
    
    def solve_recaptcha_v2(
        self,
        sitekey: str,
        page_url: str,
        invisible: bool = False
    ) -> Optional[str]:
        """
        Solve reCAPTCHA v2.
        
        Args:
            sitekey: reCAPTCHA site key
            page_url: URL of the page with CAPTCHA
            invisible: Whether the CAPTCHA is invisible
            
        Returns:
            CAPTCHA solution token or None if failed
        """
        logger.info(f"Solving reCAPTCHA v2 (invisible={invisible}) for {page_url}")
        
        for attempt in range(self.retry_attempts):
            try:
                if self.service == "2captcha":
                    result = self.solver.recaptcha(
                        sitekey=sitekey,
                        url=page_url,
                        invisible=1 if invisible else 0
                    )
                    token = result.get('code')
                    logger.success(f"✅ reCAPTCHA v2 solved successfully")
                    return token
                    
                elif self.service == "anticaptcha":
                    from anticaptchaofficial.recaptchav2proxyless import recaptchaV2Proxyless
                    solver = recaptchaV2Proxyless()
                    solver.set_key(self.api_key)
                    solver.set_website_url(page_url)
                    solver.set_website_key(sitekey)
                    if invisible:
                        solver.set_is_invisible(1)
                    
                    token = solver.solve_and_return_solution()
                    if token != 0:
                        logger.success(f"✅ reCAPTCHA v2 solved successfully")
                        return token
                    else:
                        logger.error(f"Anti-Captcha error: {solver.error_code}")
                        
            except Exception as e:
                logger.error(f"Attempt {attempt + 1}/{self.retry_attempts} failed: {e}")
                if attempt < self.retry_attempts - 1:
                    time.sleep(5)
        
        logger.error("❌ Failed to solve reCAPTCHA v2")
        return None
    
    def solve_recaptcha_v3(
        self,
        sitekey: str,
        page_url: str,
        action: str = "submit",
        min_score: float = 0.3
    ) -> Optional[str]:
        """
        Solve reCAPTCHA v3.
        
        Args:
            sitekey: reCAPTCHA site key
            page_url: URL of the page with CAPTCHA
            action: reCAPTCHA action (usually 'submit' or 'verify')
            min_score: Minimum score required (0.1 to 0.9)
            
        Returns:
            CAPTCHA solution token or None if failed
        """
        logger.info(f"Solving reCAPTCHA v3 for {page_url} (action={action}, min_score={min_score})")
        
        for attempt in range(self.retry_attempts):
            try:
                if self.service == "2captcha":
                    result = self.solver.recaptcha(
                        sitekey=sitekey,
                        url=page_url,
                        version='v3',
                        action=action,
                        score=min_score
                    )
                    token = result.get('code')
                    logger.success(f"✅ reCAPTCHA v3 solved successfully")
                    return token
                    
                elif self.service == "anticaptcha":
                    from anticaptchaofficial.recaptchav3proxyless import recaptchaV3Proxyless
                    solver = recaptchaV3Proxyless()
                    solver.set_key(self.api_key)
                    solver.set_website_url(page_url)
                    solver.set_website_key(sitekey)
                    solver.set_page_action(action)
                    solver.set_min_score(min_score)
                    
                    token = solver.solve_and_return_solution()
                    if token != 0:
                        logger.success(f"✅ reCAPTCHA v3 solved successfully")
                        return token
                    else:
                        logger.error(f"Anti-Captcha error: {solver.error_code}")
                        
            except Exception as e:
                logger.error(f"Attempt {attempt + 1}/{self.retry_attempts} failed: {e}")
                if attempt < self.retry_attempts - 1:
                    time.sleep(5)
        
        logger.error("❌ Failed to solve reCAPTCHA v3")
        return None
    
    def solve_hcaptcha(
        self,
        sitekey: str,
        page_url: str
    ) -> Optional[str]:
        """
        Solve hCaptcha.
        
        Args:
            sitekey: hCaptcha site key
            page_url: URL of the page with CAPTCHA
            
        Returns:
            CAPTCHA solution token or None if failed
        """
        logger.info(f"Solving hCaptcha for {page_url}")
        
        for attempt in range(self.retry_attempts):
            try:
                if self.service == "2captcha":
                    result = self.solver.hcaptcha(
                        sitekey=sitekey,
                        url=page_url
                    )
                    token = result.get('code')
                    logger.success(f"✅ hCaptcha solved successfully")
                    return token
                    
                elif self.service == "anticaptcha":
                    from anticaptchaofficial.hcaptchaproxyless import hCaptchaProxyless
                    solver = hCaptchaProxyless()
                    solver.set_key(self.api_key)
                    solver.set_website_url(page_url)
                    solver.set_website_key(sitekey)
                    
                    token = solver.solve_and_return_solution()
                    if token != 0:
                        logger.success(f"✅ hCaptcha solved successfully")
                        return token
                    else:
                        logger.error(f"Anti-Captcha error: {solver.error_code}")
                        
            except Exception as e:
                logger.error(f"Attempt {attempt + 1}/{self.retry_attempts} failed: {e}")
                if attempt < self.retry_attempts - 1:
                    time.sleep(5)
        
        logger.error("❌ Failed to solve hCaptcha")
        return None
    
    def detect_captcha_type(self, page_content: str) -> Optional[Dict[str, Any]]:
        """
        Detect CAPTCHA type and extract relevant information from page content.
        
        Args:
            page_content: HTML content of the page
            
        Returns:
            Dictionary with captcha_type and sitekey, or None if no CAPTCHA detected
        """
        import re
        
        # Check for reCAPTCHA v2
        recaptcha_v2_pattern = r'grecaptcha\.render\([^)]*["\']sitekey["\']\s*:\s*["\']([^"\']+)["\']'
        recaptcha_v2_match = re.search(recaptcha_v2_pattern, page_content)
        if recaptcha_v2_match:
            return {
                "captcha_type": "recaptcha_v2",
                "sitekey": recaptcha_v2_match.group(1)
            }
        
        # Check for reCAPTCHA v3
        recaptcha_v3_pattern = r'grecaptcha\.execute\(["\']([^"\']+)["\']'
        recaptcha_v3_match = re.search(recaptcha_v3_pattern, page_content)
        if recaptcha_v3_match:
            return {
                "captcha_type": "recaptcha_v3",
                "sitekey": recaptcha_v3_match.group(1)
            }
        
        # Check for reCAPTCHA in data attribute
        data_sitekey_pattern = r'data-sitekey=["\']([^"\']+)["\']'
        data_sitekey_match = re.search(data_sitekey_pattern, page_content)
        if data_sitekey_match and 'recaptcha' in page_content.lower():
            # Try to determine if it's v2 or v3
            if 'grecaptcha.execute' in page_content:
                captcha_type = "recaptcha_v3"
            else:
                captcha_type = "recaptcha_v2"
            
            return {
                "captcha_type": captcha_type,
                "sitekey": data_sitekey_match.group(1)
            }
        
        # Check for hCaptcha
        hcaptcha_pattern = r'hcaptcha\.com.*?data-sitekey=["\']([^"\']+)["\']'
        hcaptcha_match = re.search(hcaptcha_pattern, page_content, re.DOTALL)
        if hcaptcha_match:
            return {
                "captcha_type": "hcaptcha",
                "sitekey": hcaptcha_match.group(1)
            }
        
        # Check for hCaptcha in script
        if 'hcaptcha' in page_content.lower():
            hcaptcha_key_pattern = r'["\']sitekey["\']\s*:\s*["\']([^"\']+)["\']'
            hcaptcha_key_match = re.search(hcaptcha_key_pattern, page_content)
            if hcaptcha_key_match:
                return {
                    "captcha_type": "hcaptcha",
                    "sitekey": hcaptcha_key_match.group(1)
                }
        
        logger.debug("No CAPTCHA detected in page content")
        return None
    
    def get_balance(self) -> Optional[float]:
        """
        Get account balance from the CAPTCHA service.
        
        Returns:
            Account balance or None if failed
        """
        try:
            if self.service == "2captcha":
                balance = self.solver.balance()
                logger.info(f"2Captcha balance: ${balance}")
                return float(balance)
                
            elif self.service == "anticaptcha":
                from anticaptchaofficial.recaptchav3proxyless import recaptchaV3Proxyless
                solver = recaptchaV3Proxyless()
                solver.set_key(self.api_key)
                balance = solver.get_balance()
                logger.info(f"Anti-Captcha balance: ${balance}")
                return float(balance)
                
        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            return None
    
    # ==================== ASYNC METHODS ====================
    
    async def solve_recaptcha_v2_async(
        self,
        sitekey: str,
        page_url: str,
        invisible: bool = False
    ) -> Optional[str]:
        """Async version of solve_recaptcha_v2."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            _executor,
            lambda: self.solve_recaptcha_v2(sitekey, page_url, invisible)
        )
    
    async def solve_recaptcha_v3_async(
        self,
        sitekey: str,
        page_url: str,
        action: str = "submit",
        min_score: float = 0.3
    ) -> Optional[str]:
        """Async version of solve_recaptcha_v3."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            _executor,
            lambda: self.solve_recaptcha_v3(sitekey, page_url, action, min_score)
        )
    
    async def solve_hcaptcha_async(
        self,
        sitekey: str,
        page_url: str
    ) -> Optional[str]:
        """Async version of solve_hcaptcha."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            _executor,
            lambda: self.solve_hcaptcha(sitekey, page_url)
        )
    
    def solve_turnstile(
        self,
        sitekey: str,
        page_url: str
    ) -> Optional[str]:
        """
        Solve Cloudflare Turnstile CAPTCHA.
        
        Args:
            sitekey: Turnstile site key
            page_url: URL of the page with CAPTCHA
            
        Returns:
            CAPTCHA solution token or None if failed
        """
        logger.info(f"🔒 Solving Cloudflare Turnstile for {page_url}")
        
        for attempt in range(self.retry_attempts):
            try:
                if self.service == "2captcha":
                    result = self.solver.turnstile(
                        sitekey=sitekey,
                        url=page_url
                    )
                    token = result.get('code')
                    logger.success(f"✅ Cloudflare Turnstile solved successfully")
                    return token
                    
                elif self.service == "anticaptcha":
                    # Anti-Captcha Turnstile support
                    try:
                        from anticaptchaofficial.turnstileproxyless import turnstileProxyless
                        solver = turnstileProxyless()
                        solver.set_key(self.api_key)
                        solver.set_website_url(page_url)
                        solver.set_website_key(sitekey)
                        
                        token = solver.solve_and_return_solution()
                        if token and token != 0:
                            logger.success(f"✅ Cloudflare Turnstile solved successfully")
                            return token
                        else:
                            logger.error(f"Anti-Captcha Turnstile error: {solver.error_code}")
                    except ImportError:
                        logger.error("Anti-Captcha Turnstile module not available")
                        return None
                        
            except Exception as e:
                logger.error(f"Attempt {attempt + 1}/{self.retry_attempts} failed: {e}")
                if attempt < self.retry_attempts - 1:
                    time.sleep(5)
        
        logger.error("❌ Failed to solve Cloudflare Turnstile")
        return None
    
    async def solve_turnstile_async(
        self,
        sitekey: str,
        page_url: str
    ) -> Optional[str]:
        """Async version of solve_turnstile."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            _executor,
            lambda: self.solve_turnstile(sitekey, page_url)
        )
    
    def detect_captcha_type_enhanced(self, page_content: str) -> Optional[Dict[str, Any]]:
        """
        Enhanced CAPTCHA detection including Cloudflare Turnstile.
        
        Args:
            page_content: HTML content of the page
            
        Returns:
            Dictionary with captcha_type and sitekey, or None if no CAPTCHA detected
        """
        # First try the original detection
        result = self.detect_captcha_type(page_content)
        if result:
            return result
        
        # Check for Cloudflare Turnstile
        turnstile_patterns = [
            r'cf-turnstile.*?data-sitekey=["\']([^"\']+)["\']',
            r'challenges\.cloudflare\.com/turnstile.*?sitekey["\']?\s*[:=]\s*["\']([^"\']+)["\']',
            r'turnstile\.render\([^)]*["\']sitekey["\']\s*:\s*["\']([^"\']+)["\']',
            r'data-sitekey=["\']([^"\']+)["\'].*?turnstile',
        ]
        
        for pattern in turnstile_patterns:
            match = re.search(pattern, page_content, re.IGNORECASE | re.DOTALL)
            if match:
                return {
                    "captcha_type": "turnstile",
                    "sitekey": match.group(1)
                }
        
        # Check for Turnstile script inclusion
        if 'challenges.cloudflare.com/turnstile' in page_content:
            # Try to find sitekey with a broader search
            sitekey_match = re.search(r'data-sitekey=["\']([0-9a-zA-Z_-]+)["\']', page_content)
            if sitekey_match:
                return {
                    "captcha_type": "turnstile",
                    "sitekey": sitekey_match.group(1)
                }
        
        return None
    
    async def solve_auto_async(
        self,
        page_content: str,
        page_url: str
    ) -> Optional[Dict[str, Any]]:
        """
        Automatically detect and solve any CAPTCHA type.
        
        Args:
            page_content: HTML content of the page
            page_url: Current page URL
            
        Returns:
            Dictionary with 'solved', 'token', 'captcha_type' or None if no CAPTCHA
        """
        captcha_info = self.detect_captcha_type_enhanced(page_content)
        
        if not captcha_info:
            return None
        
        captcha_type = captcha_info.get("captcha_type")
        sitekey = captcha_info.get("sitekey")
        
        logger.info(f"🔍 Auto-detected CAPTCHA: {captcha_type}")
        
        token = None
        
        if captcha_type == "recaptcha_v2":
            token = await self.solve_recaptcha_v2_async(sitekey, page_url)
        elif captcha_type == "recaptcha_v3":
            token = await self.solve_recaptcha_v3_async(sitekey, page_url)
        elif captcha_type == "hcaptcha":
            token = await self.solve_hcaptcha_async(sitekey, page_url)
        elif captcha_type == "turnstile":
            token = await self.solve_turnstile_async(sitekey, page_url)
        
        if token:
            return {
                "solved": True,
                "token": token,
                "captcha_type": captcha_type,
                "sitekey": sitekey
            }
        else:
            return {
                "solved": False,
                "token": None,
                "captcha_type": captcha_type,
                "sitekey": sitekey
            }

