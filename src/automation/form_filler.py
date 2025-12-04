"""
Intelligent form filler with automatic field detection and completion.
"""

import asyncio
import re
from typing import Optional, Dict, List, Tuple
from loguru import logger

from playwright.async_api import Page, ElementHandle
from src.config import Config
from src.utils.helpers import random_delay, format_phone_number


class FormFiller:
    """
    Intelligent form filler that detects and fills opt-in forms.
    Handles various field types and naming conventions.
    """
    
    def __init__(self, page: Page, config: Config):
        """
        Initialize form filler.
        
        Args:
            page: Playwright page object
            config: Application configuration
        """
        self.page = page
        self.config = config
        self.form_detection = config.form_detection
        self.automation_config = config.automation
        self.credentials = config.credentials
    
    async def find_and_fill_form(self) -> Tuple[bool, Dict[str, str]]:
        """
        Find and fill the opt-in form on the page.
        
        Returns:
            Tuple of (success, fields_filled)
        """
        logger.info("Searching for opt-in form...")
        
        fields_filled = {}
        
        try:
            # Wait a bit for page to fully load
            await asyncio.sleep(random_delay(
                *self.automation_config.delays.before_form_fill
            ))
            
            # Find and fill email field
            email_field = await self._find_email_field()
            if email_field:
                success = await self._fill_field(email_field, self.credentials.email)
                if success:
                    fields_filled["email"] = self.credentials.email
                    logger.success("✅ Email field filled")
            else:
                logger.error("❌ Email field not found")
                return False, fields_filled
            
            # Find and fill first name field
            name_field = await self._find_first_name_field()
            if name_field:
                success = await self._fill_field(name_field, self.credentials.first_name)
                if success:
                    fields_filled["first_name"] = self.credentials.first_name
                    logger.success("✅ First name field filled")
            else:
                logger.warning("⚠️ First name field not found (optional)")
            
            # Find and fill phone field
            phone_field = await self._find_phone_field()
            if phone_field:
                # Format phone based on field type
                formatted_phone = await self._format_phone_for_field(phone_field)
                success = await self._fill_field(phone_field, formatted_phone)
                if success:
                    fields_filled["phone"] = formatted_phone
                    logger.success("✅ Phone field filled")
            else:
                logger.warning("⚠️ Phone field not found (optional)")
            
            # Look for other common fields
            await self._fill_optional_fields(fields_filled)
            
            logger.success(f"✅ Form filled successfully. Fields: {list(fields_filled.keys())}")
            return True, fields_filled
            
        except Exception as e:
            logger.error(f"Error filling form: {e}")
            return False, fields_filled
    
    async def _find_email_field(self) -> Optional[ElementHandle]:
        """Find the email input field."""
        patterns = self.form_detection.email_field_patterns
        
        # Try multiple strategies in order of reliability
        selectors = [
            # Type attribute (most reliable)
            'input[type="email"]',
            # Common names and IDs
            'input[name="email"]',
            'input[id="email"]',
            'input[name="Email"]',
            'input[id="Email"]',
            # Partial matches (case insensitive)
            'input[name*="email" i]',
            'input[id*="email" i]',
            'input[placeholder*="email" i]',
            'input[aria-label*="email" i]',
            # Text inputs that might be email (fallback)
            'input[type="text"][placeholder*="email" i]',
            'input[type="text"][name*="email" i]',
        ]
        
        # Add custom patterns from config
        for pattern in patterns:
            selectors.extend([
                f'input[name*="{pattern}" i]',
                f'input[id*="{pattern}" i]',
                f'input[placeholder*="{pattern}" i]',
                f'input[aria-label*="{pattern}" i]',
            ])
        
        # Also check for any text input in a form (last resort)
        selectors.append('form input[type="text"]')
        selectors.append('form input:not([type])')
        
        return await self._try_selectors(selectors)
    
    async def _find_first_name_field(self) -> Optional[ElementHandle]:
        """Find the first name input field."""
        patterns = self.form_detection.first_name_field_patterns
        
        selectors = []
        for pattern in patterns:
            selectors.extend([
                f'input[name*="{pattern}" i]',
                f'input[id*="{pattern}" i]',
                f'input[placeholder*="{pattern}" i]',
            ])
        
        # Also try generic text inputs near email
        selectors.append('input[type="text"]')
        
        return await self._try_selectors(selectors)
    
    async def _find_phone_field(self) -> Optional[ElementHandle]:
        """Find the phone input field."""
        patterns = self.form_detection.phone_field_patterns
        
        selectors = [
            'input[type="tel"]',
        ]
        
        for pattern in patterns:
            selectors.extend([
                f'input[name*="{pattern}" i]',
                f'input[id*="{pattern}" i]',
                f'input[placeholder*="{pattern}" i]',
            ])
        
        return await self._try_selectors(selectors)
    
    async def _try_selectors(self, selectors: List[str]) -> Optional[ElementHandle]:
        """
        Try multiple selectors and return the first matching visible element.
        
        Args:
            selectors: List of CSS selectors to try
            
        Returns:
            ElementHandle or None
        """
        for selector in selectors:
            try:
                elements = await self.page.query_selector_all(selector)
                for element in elements:
                    # Check if element is visible and enabled
                    is_visible = await element.is_visible()
                    is_enabled = await element.is_enabled()
                    
                    if is_visible and is_enabled:
                        # Check if it's not already filled
                        value = await element.get_attribute("value")
                        if not value or value.strip() == "":
                            # Additional check: make sure it's not hidden or disabled
                            is_hidden = await element.is_hidden()
                            if not is_hidden:
                                logger.debug(f"Found element with selector: {selector}")
                                return element
            except Exception as e:
                logger.debug(f"Error trying selector '{selector}': {e}")
                continue
        
        return None
    
    async def _fill_field(self, element: ElementHandle, value: str) -> bool:
        """
        Fill a form field with human-like behavior.
        
        Args:
            element: Field element
            value: Value to fill
            
        Returns:
            True if successful
        """
        try:
            # Scroll element into view
            await element.scroll_into_view_if_needed()
            await asyncio.sleep(random_delay(
                *self.automation_config.delays.between_fields
            ))
            
            # Click to focus
            await element.click()
            await asyncio.sleep(0.3)
            
            # Clear existing value
            await element.fill("")
            await asyncio.sleep(0.2)
            
            # Type with human-like behavior
            behavior = self.automation_config.behavior
            
            for char in value:
                await element.type(char, delay=random_delay(
                    behavior.typing_delay_min,
                    behavior.typing_delay_max
                ) * 1000)
            
            # Verify value was set
            filled_value = await element.get_attribute("value")
            if filled_value == value:
                return True
            else:
                logger.warning(f"Field value mismatch: expected '{value}', got '{filled_value}'")
                return False
                
        except Exception as e:
            logger.error(f"Error filling field: {e}")
            return False
    
    async def _format_phone_for_field(self, element: ElementHandle) -> str:
        """
        Format phone number based on field requirements.
        
        Args:
            element: Phone field element
            
        Returns:
            Formatted phone number
        """
        phone = self.credentials.phone
        
        # Check placeholder for format hint
        placeholder = await element.get_attribute("placeholder")
        
        if placeholder:
            # Check for common formats
            if "(" in placeholder and ")" in placeholder:
                # Format: (123) 456-7890
                digits = format_phone_number(phone)
                if len(digits) >= 10:
                    return f"({digits[:3]}) {digits[3:6]}-{digits[6:10]}"
            elif "-" in placeholder:
                # Format: 123-456-7890
                digits = format_phone_number(phone)
                if len(digits) >= 10:
                    return f"{digits[:3]}-{digits[3:6]}-{digits[6:10]}"
            elif "." in placeholder:
                # Format: 123.456.7890
                digits = format_phone_number(phone)
                if len(digits) >= 10:
                    return f"{digits[:3]}.{digits[3:6]}.{digits[6:10]}"
        
        # Default: return as-is or digits only
        input_type = await element.get_attribute("type")
        if input_type == "tel":
            return format_phone_number(phone)
        
        return phone
    
    async def _fill_optional_fields(self, fields_filled: Dict[str, str]):
        """Fill other optional fields if present."""
        try:
            # Last name field
            last_name_selectors = [
                'input[name*="lastname" i]',
                'input[name*="last_name" i]',
                'input[id*="lastname" i]',
            ]
            last_name_field = await self._try_selectors(last_name_selectors)
            if last_name_field:
                await self._fill_field(last_name_field, "Doe")
                fields_filled["last_name"] = "Doe"
                logger.debug("Last name field filled")
            
            # Company field
            company_selectors = [
                'input[name*="company" i]',
                'input[id*="company" i]',
            ]
            company_field = await self._try_selectors(company_selectors)
            if company_field:
                await self._fill_field(company_field, "Independent")
                fields_filled["company"] = "Independent"
                logger.debug("Company field filled")
            
            # Checkboxes (Terms, Privacy, etc.)
            await self._handle_checkboxes(fields_filled)
            
        except Exception as e:
            logger.debug(f"Error filling optional fields: {e}")
    
    async def _handle_checkboxes(self, fields_filled: Dict[str, str]):
        """Handle checkboxes like terms and conditions."""
        try:
            # Find all visible checkboxes
            checkboxes = await self.page.query_selector_all('input[type="checkbox"]')
            
            for checkbox in checkboxes:
                is_visible = await checkbox.is_visible()
                if not is_visible:
                    continue
                
                # Check if it's required or related to terms
                is_required = await checkbox.get_attribute("required")
                name = await checkbox.get_attribute("name") or ""
                id_attr = await checkbox.get_attribute("id") or ""
                
                # Check terms/privacy related checkboxes
                terms_keywords = ["terms", "privacy", "policy", "agree", "consent"]
                is_terms = any(keyword in name.lower() or keyword in id_attr.lower() 
                              for keyword in terms_keywords)
                
                if is_required or is_terms:
                    is_checked = await checkbox.is_checked()
                    if not is_checked:
                        await checkbox.click()
                        await asyncio.sleep(0.3)
                        fields_filled[f"checkbox_{name or id_attr}"] = "checked"
                        logger.debug(f"Checked required checkbox: {name or id_attr}")
                        
        except Exception as e:
            logger.debug(f"Error handling checkboxes: {e}")
    
    async def find_and_click_submit(self) -> bool:
        """
        Find and click the submit button.
        
        Returns:
            True if successful
        """
        logger.info("Searching for submit button...")
        
        try:
            # Wait before submitting
            await asyncio.sleep(random_delay(
                *self.automation_config.delays.before_submit
            ))
            
            # Try various submit button selectors
            patterns = self.form_detection.submit_button_patterns
            
            selectors = [
                # Standard submit buttons
                'button[type="submit"]',
                'input[type="submit"]',
                # Common button text patterns (case insensitive)
                'button:has-text("Submit")',
                'button:has-text("Sign up")',
                'button:has-text("Sign Up")',
                'button:has-text("Get Started")',
                'button:has-text("Join")',
                'button:has-text("Continue")',
                'button:has-text("Next")',
                # Form buttons (any button in a form)
                'form button',
                'form input[type="button"]',
                # Links styled as buttons
                'a[role="button"]',
            ]
            
            # Add pattern-based selectors from config
            for pattern in patterns:
                pattern_lower = pattern.lower()
                pattern_title = pattern.title()
                pattern_upper = pattern.upper()
                
                selectors.extend([
                    f'button:has-text("{pattern}")',
                    f'button:has-text("{pattern_lower}")',
                    f'button:has-text("{pattern_title}")',
                    f'button:has-text("{pattern_upper}")',
                    f'input[value*="{pattern}" i]',
                    f'button[id*="{pattern}" i]',
                    f'button[class*="{pattern}" i]',
                    f'button[aria-label*="{pattern}" i]',
                    f'a[class*="btn"]:has-text("{pattern}")',
                ])
            
            # Try each selector
            for selector in selectors:
                try:
                    # Use timeout to avoid hanging
                    elements = await self.page.query_selector_all(selector)
                    
                    for element in elements:
                        is_visible = await element.is_visible()
                        is_enabled = await element.is_enabled()
                        
                        if is_visible and is_enabled:
                            # Found submit button
                            logger.debug(f"Found submit button with selector: {selector}")
                            await element.scroll_into_view_if_needed()
                            await asyncio.sleep(0.5)
                            
                            # Click the button
                            await element.click()
                            logger.success("✅ Submit button clicked")
                            
                            # Wait for submission
                            await asyncio.sleep(random_delay(
                                *self.automation_config.delays.after_submit
                            ))
                            
                            return True
                except Exception as e:
                    logger.debug(f"Error trying selector '{selector}': {e}")
                    continue
            
            logger.error("❌ Submit button not found")
            return False
            
        except Exception as e:
            logger.error(f"Error clicking submit: {e}")
            return False
    
    async def verify_submission(self) -> bool:
        """
        Verify that form was successfully submitted.
        Looks for success messages or redirects.
        
        Returns:
            True if submission appears successful
        """
        try:
            await asyncio.sleep(2)
            
            # Check for common success indicators
            success_keywords = [
                "thank you",
                "success",
                "submitted",
                "check your email",
                "confirmation",
                "registered",
                "signed up"
            ]
            
            page_content = await self.page.content()
            page_text = await self.page.text_content("body") or ""
            
            # Check page content for success messages
            for keyword in success_keywords:
                if keyword in page_text.lower():
                    logger.success(f"✅ Success indicator found: '{keyword}'")
                    return True
            
            # Check if URL changed (redirect to thank you page)
            current_url = self.page.url
            if any(keyword in current_url.lower() for keyword in ["thank", "success", "confirm"]):
                logger.success("✅ Redirected to success page")
                return True
            
            # Check if form is no longer visible (hidden after submission)
            email_field = await self._find_email_field()
            if not email_field:
                logger.success("✅ Form no longer visible (likely submitted)")
                return True
            
            logger.warning("⚠️ Could not verify submission success")
            return False
            
        except Exception as e:
            logger.error(f"Error verifying submission: {e}")
            return False

