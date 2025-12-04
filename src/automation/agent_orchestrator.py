"""
AI Agent Orchestrator with continuous reasoning loop.
Implements observation → reasoning → action → validation cycle.
Enhanced with screenshot-based visual analysis.
"""

import asyncio
import json
import re
import base64
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
from loguru import logger

from playwright.async_api import Page
from src.automation.llm_analyzer import LLMPageAnalyzer


class AgentAction:
    """Represents an action to be taken by the agent."""
    
    def __init__(self, action_type: str, selector: Optional[str] = None, 
                 value: Optional[str] = None, reasoning: str = ""):
        self.action_type = action_type  # fill_field, click, wait, submit, complete
        self.selector = selector
        self.value = value
        self.reasoning = reasoning
        self.timestamp = datetime.utcnow()
        self.success = None
        self.error_message = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_type": self.action_type,
            "selector": self.selector,
            "value": self.value,
            "reasoning": self.reasoning,
            "success": self.success,
            "error_message": self.error_message
        }


class AgentState:
    """Tracks the state of the agent during execution."""
    
    def __init__(self):
        self.actions_taken: List[AgentAction] = []
        self.fields_filled: Dict[str, str] = {}
        self.current_step = 1
        self.max_steps = 30  # Increased for exploration
        self.page_transitions = 0
        self.captcha_solved = False
        self.complete = False
        self.success = False
        self.conversation_history: List[Dict[str, str]] = []
        self.exploration_clicks = 0  # Track exploration attempts
        self.checkboxes_checked: List[str] = []  # Track checked checkboxes to prevent over-selection
    
    def add_action(self, action: AgentAction):
        """Record an action taken."""
        self.actions_taken.append(action)
        if action.action_type == "fill_field" and action.success:
            self.fields_filled[action.selector] = action.value
    
    def to_summary(self) -> Dict[str, Any]:
        """Get a summary of the agent's execution."""
        return {
            "total_actions": len(self.actions_taken),
            "fields_filled": self.fields_filled,
            "steps_taken": self.current_step,
            "page_transitions": self.page_transitions,
            "captcha_solved": self.captcha_solved,
            "complete": self.complete,
            "success": self.success,
            "actions": [action.to_dict() for action in self.actions_taken]
        }


class AIAgentOrchestrator:
    """
    AI-powered agent that uses continuous reasoning loop to fill forms.
    
    Architecture:
    1. Observe: Extract page state (HTML, accessibility tree)
    2. Reason: Send to LLM for analysis and next action
    3. Act: Execute the suggested action
    4. Validate: Check if action succeeded
    5. Repeat until goal achieved or max steps reached
    """
    
    def __init__(self, page: Page, credentials: Dict[str, str], 
                 llm_provider: str = "openai", llm_config: Dict[str, Any] = None,
                 stop_check: callable = None):
        """
        Initialize AI Agent.
        
        Args:
            page: Playwright page object
            credentials: User credentials (email, name, phone)
            llm_provider: LLM provider ('openai' or 'anthropic')
            llm_config: LLM configuration (API key, model)
            stop_check: Optional callable that returns True if stop requested
        """
        self.page = page
        self.credentials = credentials
        self.llm_provider = llm_provider
        self.llm_config = llm_config or {}
        self.state = AgentState()
        self._stop_check = stop_check or (lambda: False)
        
        # Vision optimization tracking
        self.last_vision_step = -1  # Track when we last used vision
        self.last_action_type = None  # Track last action type to decide if vision is needed
        
        # Rate limit tracking
        self.consecutive_rate_limits = 0  # Track consecutive rate limit failures
        
        # Vision optimization tracking
        self.last_vision_step = -1  # Track when we last used vision
        self.last_action_type = None  # Track last action type to decide if vision is needed
        
        # Rate limit tracking
        self.consecutive_rate_limits = 0  # Track consecutive rate limit failures
        
        # Initialize LLM analyzer
        self.llm_analyzer = LLMPageAnalyzer(
            page=page,
            credentials=credentials,
            llm_provider=llm_provider,
            llm_config=llm_config
        )
        
        logger.info("🤖 AI Agent initialized with continuous reasoning loop")
    
    def _should_use_vision(self, step: int, last_action_success: bool) -> bool:
        """
        Intelligently decide if vision should be used for this step.
        
        Vision is expensive (tokens), so use it only when visual context adds value:
        - First step (need to see initial state)
        - After navigation/clicks (page changed)
        - After errors (need to see what went wrong)
        - After form submission (check for success/error messages)
        - Every 5 steps as sanity check
        
        Skip vision for:
        - Sequential form fills on same page (HTML is enough)
        
        Args:
            step: Current step number
            last_action_success: Whether last action succeeded
            
        Returns:
            True if vision should be used
        """
        # Always use vision on first step
        if step == 1:
            logger.info("   🎯 Using VISION: First step")
            return True
        
        # Use vision after navigation or clicks (page likely changed)
        if self.last_action_type in ["click", "submit", "wait"]:
            logger.info(f"   🎯 Using VISION: After {self.last_action_type} (page may have changed)")
            return True
        
        # Use vision after failures (need to see what went wrong)
        if not last_action_success:
            logger.info("   🎯 Using VISION: After failure (visual debugging)")
            return True
        
        # Use vision every 5 steps as sanity check
        if step % 5 == 0:
            logger.info("   🎯 Using VISION: Periodic check (every 5 steps)")
            return True
        
        # Skip vision for sequential form fills (HTML is enough)
        if self.last_action_type == "fill_field":
            logger.info("   💰 SKIPPING VISION: Sequential form fill (HTML sufficient)")
            return False
        
        # Default: use vision
        logger.info("   🎯 Using VISION: Default")
        return True
    
    def _parse_selector(self, selector: str) -> str:
        """
        Parse and convert selectors with :contains() to Playwright text selectors.
        
        Args:
            selector: CSS selector that may contain :contains()
            
        Returns:
            Valid Playwright selector
        """
        # Check if selector contains :contains() pseudo-class
        contains_pattern = r':contains\(["\']([^"\']+)["\']\)'
        match = re.search(contains_pattern, selector)
        
        if match:
            text = match.group(1)
            # Remove the :contains() part
            base_selector = re.sub(contains_pattern, '', selector)
            
            # If there's a base selector, use it with text filter
            if base_selector and base_selector not in ['', ':']:
                # Use Playwright's text filter
                return f"{base_selector} >> text={text}"
            else:
                # Just use text selector
                return f"text={text}"
        
        return selector
    
    async def execute_signup(self) -> Dict[str, Any]:
        """
        Execute the sign-up process using continuous reasoning loop.
        
        Returns:
            Dictionary with execution results
        """
        logger.info("🚀 Starting AI Agent reasoning loop...")
        
        try:
            # Check stop before starting
            if self._stop_check():
                logger.info("⏹ Stop requested - aborting agent")
                return {"success": False, "fields_filled": [], "actions": [], "errors": ["Stop requested"]}
            
            # Initial page load wait
            await asyncio.sleep(2)
            
            # Main reasoning loop
            # Track last action success for vision optimization
            last_action_success = True
            
            while not self.state.complete and self.state.current_step <= self.state.max_steps:
                # Check stop at beginning of each step
                if self._stop_check():
                    logger.info("⏹ Stop requested - stopping agent")
                    self.state.complete = True
                    self.state.success = False
                    break
                
                # Display rate limit status
                rate_limit_status = f" | 🚦 Rate Limits: {self.consecutive_rate_limits}/3" if self.consecutive_rate_limits > 0 else ""
                
                logger.info(f"\n{'='*60}")
                logger.info(f"🔄 Agent Step {self.state.current_step}/{self.state.max_steps}{rate_limit_status}")
                logger.info(f"{'='*60}")
                
                # Step 1: OBSERVE - Smart vision usage to save tokens
                use_vision = self._should_use_vision(self.state.current_step, last_action_success)
                page_state = await self._observe_page(use_vision=use_vision)
                
                # Analyze page state for form elements and navigation opportunities
                input_count = len(page_state.get("inputs", []))
                button_count = len(page_state.get("buttons", []))
                has_form_inputs = any(inp.get("type") in ["email", "text", "tel", "select", "checkbox", "radio"] 
                                     for inp in page_state.get("inputs", []))
                
                # Look for navigation/signup buttons
                navigation_buttons = [btn for btn in page_state.get("buttons", []) 
                                     if any(keyword in btn.get("text", "").lower() 
                                           for keyword in ["sign up", "signup", "register", "join", 
                                                          "get started", "start now", "learn more",
                                                          "try", "demo", "access", "subscribe",
                                                          "download", "get", "claim", "free"])]
                
                # Only exit early if we've exhausted exploration AND found no forms
                if self.state.current_step >= 15 and len(self.state.fields_filled) == 0:
                    if not has_form_inputs and len(navigation_buttons) == 0:
                        logger.warning("⚠️ No form elements or navigation buttons found after 15 steps")
                        logger.info("   This page appears to have no signup capability")
                        self.state.complete = True
                        self.state.success = False
                        break
                
                # Step 2: REASON - Ask LLM what to do next
                next_action = await self._reason_next_action(page_state)
                
                if not next_action:
                    logger.error("❌ LLM failed to provide next action")
                    break
                
                # Check if LLM detected CAPTCHA in reasoning
                llm_detected_captcha = "captcha" in next_action.reasoning.lower() if next_action.reasoning else False
                
                # If CAPTCHA detected, attempt to solve BEFORE executing wait action
                if llm_detected_captcha and next_action.action_type == "wait":
                    logger.warning("🔒 CAPTCHA detected by LLM - attempting to solve...")
                    captcha_solved, bypass_action = await self._handle_captcha_in_agent()
                    
                    if captcha_solved:
                        logger.success("✅ CAPTCHA solved! Continuing to next step...")
                        # Mark action as successful and move on
                        next_action.success = True
                        self.state.add_action(next_action)
                        await asyncio.sleep(3)  # Wait for page to update after CAPTCHA
                        self.state.current_step += 1
                        continue
                    elif bypass_action:
                        # LLM found a skip/bypass button - create an action to click it
                        logger.info(f"💡 LLM suggests clicking bypass button: '{bypass_action.get('text')}'")
                        bypass_click = AgentAction(
                            action_type="click",
                            selector=bypass_action.get('selector'),
                            reasoning=f"LLM found bypass button: {bypass_action.get('text')}"
                        )
                        # Execute the bypass click
                        click_result = await self._execute_action(bypass_click)
                        if click_result["success"]:
                            logger.success("✅ Clicked bypass button!")
                            bypass_click.success = True
                            self.state.add_action(bypass_click)
                            await asyncio.sleep(2)
                            self.state.current_step += 1
                            continue
                        else:
                            logger.warning("⚠️ Failed to click bypass button")
                    
                    # If nothing worked, check if we're stuck
                    recent_captcha_waits = sum(1 for a in self.state.actions_taken[-3:] 
                                              if a.action_type == "wait" and "captcha" in a.reasoning.lower())
                    if recent_captcha_waits >= 3:
                        logger.error("❌ Stuck on CAPTCHA for 3 steps - giving up")
                        self.state.complete = True
                        self.state.success = False
                        break
                
                # Step 3: ACT - Execute the action
                action_result = await self._execute_action(next_action)
                
                # Step 4: VALIDATE - Check if action succeeded
                if action_result["success"]:
                    next_action.success = True
                    logger.success(f"✅ Action succeeded: {next_action.action_type}")
                else:
                    next_action.success = False
                    error_msg = action_result.get("error", "Unknown error")
                    next_action.error_message = error_msg
                    logger.warning(f"⚠️ Action failed: {error_msg}")
                    
                    # Log hints for common errors
                    if "hidden" in error_msg.lower() or "not visible" in error_msg.lower():
                        logger.info("   💡 Hint: Element is hidden. For checkboxes, fill_field should now work with state='attached'.")
                    elif "timeout" in error_msg.lower() or "not found" in error_msg.lower():
                        logger.info("   💡 Hint: Selector incorrect or element doesn't exist - try different selector.")
                
                # Record action
                self.state.add_action(next_action)
                
                # Update tracking for vision optimization
                last_action_success = next_action.success
                self.last_action_type = next_action.action_type
                
                # Check if we're done
                if next_action.action_type == "complete":
                    self.state.complete = True
                    self.state.success = True
                    logger.success("🎉 Agent completed successfully!")
                    break
                
                # Check if we're stuck (same selector failed 3+ times)
                if not next_action.success and next_action.selector:
                    failed_count = sum(1 for a in self.state.actions_taken 
                                     if a.selector == next_action.selector and not a.success)
                    if failed_count >= 3:
                        logger.warning(f"⚠️ Selector {next_action.selector} failed {failed_count} times - completing")
                        self.state.complete = True
                        # Only success if we have actual success indicators
                        self.state.success = page_state.get("has_success_indicator", False)
                        if not self.state.success:
                            logger.warning("   ❌ No success confirmation found - marking as failed")
                        break
                
                # Check if stuck in error loop (errors present + repeated clicks without filling fields)
                if page_state.get("has_error_messages"):
                    recent_clicks = [a for a in self.state.actions_taken[-6:] 
                                   if a.action_type == "click" and a.success]
                    recent_fills = [a for a in self.state.actions_taken[-6:] 
                                  if a.action_type == "fill_field" and a.success]
                    
                    # If 3+ clicks without recent fills and errors present, might be stuck
                    if len(recent_clicks) >= 3 and len(recent_fills) == 0:
                        error_texts = [e.get('text')[:100] for e in page_state.get('error_messages', [])[:2]]
                        
                        # Don't quit if error is about CAPTCHA (we're handling that)
                        if not any("captcha" in err.lower() for err in error_texts):
                            logger.warning("⚠️ Validation errors present - bot clicking without filling required fields")
                            logger.info(f"   Errors detected: {error_texts}")
                            logger.info("   Hint: Form likely requires checkbox/radio selection or field input before proceeding")
                            self.state.complete = True
                            self.state.success = False  # Failed due to validation errors
                            break
                
                # Wait before next iteration
                await asyncio.sleep(1.5)
                
                self.state.current_step += 1
            
            # Check if we hit max steps
            if self.state.current_step > self.state.max_steps:
                logger.warning(f"⚠️ Reached maximum steps limit ({self.state.max_steps} steps)")
                # Check for success indicators in final state
                final_page_state = await self._observe_page()
                if final_page_state.get("has_success_indicator"):
                    logger.success("   ✅ Success confirmation found - marking as successful")
                    self.state.success = True
                else:
                    logger.warning("   ❌ No success confirmation found - marking as failed")
                    self.state.success = False
                self.state.complete = True
            
            # Generate final summary
            summary = self.state.to_summary()
            logger.info(f"\n📊 Agent Execution Summary:")
            logger.info(f"   Actions: {summary['total_actions']}")
            logger.info(f"   Fields Filled: {len(summary['fields_filled'])}")
            logger.info(f"   Success: {summary['success']}")
            if self.consecutive_rate_limits > 0:
                logger.info(f"   Rate Limits Encountered: {self.consecutive_rate_limits} (handled successfully)")
            
            return {
                "success": self.state.success,
                "fields_filled": list(self.state.fields_filled.keys()),
                "actions": summary["actions"],
                "steps_taken": self.state.current_step,
                "errors": [a.error_message for a in self.state.actions_taken if not a.success]
            }
            
        except Exception as e:
            error_msg = str(e)
            
            # Special handling for rate limit errors
            if "rate limit" in error_msg.lower() or "quota" in error_msg.lower():
                logger.error(f"❌ Agent execution failed: OpenAI API rate limit exceeded after progressive backoff")
                logger.error(f"   💡 Suggestion: Wait a few minutes and try again, or upgrade your OpenAI API plan")
            else:
                logger.error(f"❌ Agent execution failed: {e}", exc_info=True)
            
            return {
                "success": False,
                "fields_filled": [],
                "actions": [],
                "errors": [str(e)]
            }
    
    async def _capture_screenshot(self) -> Optional[str]:
        """
        Capture screenshot and return base64 encoded string.
        
        Returns:
            Base64 encoded screenshot or None
        """
        try:
            screenshot_bytes = await self.page.screenshot(full_page=False)
            base64_image = base64.b64encode(screenshot_bytes).decode('utf-8')
            return base64_image
        except Exception as e:
            logger.error(f"Failed to capture screenshot: {e}")
            return None
    
    async def _observe_page(self, use_vision: bool = True) -> Dict[str, Any]:
        """
        Observe current page state, optionally with screenshot.
        
        Args:
            use_vision: Whether to capture screenshot (expensive in tokens)
        
        Returns:
            Dictionary with page state information including screenshot (if use_vision=True)
        """
        logger.debug(f"👁️ Observing page state (vision={use_vision})...")
        
        try:
            # Capture screenshot only if vision is needed (token optimization)
            screenshot_base64 = await self._capture_screenshot() if use_vision else None
            
            # Extract page information using existing LLM analyzer
            page_info = await self.llm_analyzer._extract_page_info()
            
            # Get current URL
            current_url = self.page.url
            
            # Get visible text
            visible_text = await self.page.evaluate("""
                () => document.body.innerText.substring(0, 2000)
            """)
            
            # Check for success indicators
            success_keywords = ["thank", "success", "confirm", "welcome", "check your email"]
            has_success_indicator = any(kw in visible_text.lower() for kw in success_keywords)
            
            # Detect error messages on the page
            error_messages = await self.page.evaluate("""
                () => {
                    const errors = [];
                    // Common error message selectors
                    const errorSelectors = [
                        '.error', '.error-message', '.field-error', '.validation-error',
                        '[class*="error"]', '[class*="invalid"]', '[role="alert"]',
                        '.help-block.text-danger', '.invalid-feedback', '.text-danger',
                        'span[style*="color: red"]', 'span[style*="color:red"]',
                        'div[style*="color: red"]', 'div[style*="color:red"]'
                    ];
                    
                    errorSelectors.forEach(selector => {
                        try {
                            const elements = document.querySelectorAll(selector);
                            elements.forEach(el => {
                                if (el.offsetParent !== null && el.textContent.trim()) {
                                    errors.push({
                                        text: el.textContent.trim(),
                                        selector: selector,
                                        visible: true
                                    });
                                }
                            });
                        } catch(e) {}
                    });
                    
                    return errors;
                }
            """)
            
            has_error_messages = len(error_messages) > 0
            
            observation = {
                "url": current_url,
                "screenshot": screenshot_base64,  # Add screenshot
                "forms": page_info.get("forms", []),
                "inputs": page_info.get("inputs", []),
                "buttons": page_info.get("buttons", []),
                "visible_text": visible_text,
                "simplified_html": page_info.get("simplifiedHtml", ""),
                "has_success_indicator": has_success_indicator,
                "has_error_messages": has_error_messages,
                "error_messages": error_messages[:5],  # Limit to first 5 errors
                "fields_already_filled": self.state.fields_filled
            }
            
            logger.debug(f"   Found {len(observation['inputs'])} inputs, {len(observation['buttons'])} buttons")
            if screenshot_base64:
                logger.debug(f"   📸 Screenshot captured ({len(screenshot_base64)} bytes)")
            
            return observation
            
        except Exception as e:
            logger.error(f"Error observing page: {e}")
            return {}
    
    async def _reason_next_action(self, page_state: Dict[str, Any]) -> Optional[AgentAction]:
        """
        Use LLM to reason about next action.
        
        Args:
            page_state: Current page state from observation
            
        Returns:
            AgentAction to execute, or None if reasoning failed
        """
        logger.debug("🧠 Reasoning about next action...")
        
        try:
            # Handle empty page state (from navigation errors)
            if not page_state or not page_state.get("inputs") and not page_state.get("buttons"):
                logger.warning("⚠️ Empty page state, waiting for page to stabilize")
                return AgentAction("wait", reasoning="Page is loading or navigating, waiting for content")
            
            # Build context for LLM
            context = self._build_reasoning_context(page_state)
            
            # Call LLM with multi-turn conversation support + screenshot
            # Smart rate limit handling: parse wait time from OpenAI, add buffer, retry
            max_rate_limit_retries = 3
            retry_attempt = 0
            
            while retry_attempt <= max_rate_limit_retries:
                try:
                    llm_response = await self.llm_analyzer._call_llm_for_next_action(
                        context=context,
                        conversation_history=self.state.conversation_history,
                        screenshot_base64=page_state.get("screenshot")  # Pass screenshot for vision
                    )
                    
                    # Success - reset rate limit counter
                    if retry_attempt > 0:
                        logger.success(f"✅ LLM call succeeded after {retry_attempt} retries")
                    self.consecutive_rate_limits = 0
                    break  # Success - exit retry loop
                    
                except Exception as e:
                    error_msg = str(e)
                    
                    # Check if it's a rate limit error
                    if "rate_limit" in error_msg.lower() or "429" in error_msg:
                        retry_attempt += 1
                        self.consecutive_rate_limits += 1
                        
                        # Stop if exceeded max retries
                        if retry_attempt > max_rate_limit_retries:
                            logger.error(f"❌ Rate limit exceeded after {max_rate_limit_retries} retries - stopping")
                            raise Exception("Rate limit exceeded - API quota exhausted after multiple retries")
                        
                        # Parse wait time from OpenAI error message
                        wait_time = None
                        parsed_time = None
                        try:
                            # Extract: "Please try again in 8.008s" or "Please try again in 3m15s"
                            if "Please try again in" in error_msg:
                                import re
                                # Use regex to extract time like "8.008s" or "3m"
                                match = re.search(r'Please try again in ([\d.]+)(m|s)', error_msg)
                                if match:
                                    value = float(match.group(1))
                                    unit = match.group(2)
                                    
                                    if unit == "m":
                                        parsed_time = value * 60  # Convert minutes to seconds
                                    else:  # unit == "s"
                                        parsed_time = value
                                    
                                    # Add 2-second safety buffer
                                    wait_time = parsed_time + 2
                                    logger.info(f"   📊 OpenAI suggests: {parsed_time:.1f}s | Using: {wait_time:.1f}s (+2s buffer)")
                        except (ValueError, AttributeError) as parse_error:
                            logger.debug(f"Could not parse wait time from error: {parse_error}")
                        
                        # Fallback to progressive backoff if parsing failed
                        if wait_time is None:
                            if retry_attempt == 1:
                                wait_time = 10
                            elif retry_attempt == 2:
                                wait_time = 30
                            else:
                                wait_time = 60
                            logger.info(f"   📊 Using fallback wait time: {wait_time}s")
                        
                        logger.warning(f"⏳ Rate limit hit (retry {retry_attempt}/{max_rate_limit_retries}) - waiting {wait_time:.1f}s...")
                        
                        # Wait before retry
                        import asyncio
                        await asyncio.sleep(wait_time)
                        
                        logger.info(f"🔄 Retrying LLM call (attempt {retry_attempt + 1})...")
                        continue  # Retry the loop
                    else:
                        # Not a rate limit error - re-raise
                        raise
            
            if not llm_response:
                return None
            
            # Update conversation history
            self.state.conversation_history.append({
                "role": "assistant",
                "content": json.dumps(llm_response)
            })
            
            # Parse LLM response into AgentAction
            action = self._parse_llm_response(llm_response)
            
            if action:
                logger.info(f"💡 LLM Decision: {action.action_type}")
                if llm_response.get("visual_observation"):
                    logger.info(f"   👁️  Visual: {llm_response.get('visual_observation')}")
                logger.info(f"   🧠 Reasoning: {action.reasoning}")
                if llm_response.get("expected_outcome"):
                    logger.info(f"   🎯 Expected: {llm_response.get('expected_outcome')}")
                if action.selector:
                    logger.info(f"   🎯 Target: {action.selector}")
            
            return action
            
        except Exception as e:
            logger.error(f"Error during reasoning: {e}")
            return None
    
    def _build_reasoning_context(self, page_state: Dict[str, Any]) -> Dict[str, Any]:
        """Build context dictionary for LLM reasoning."""
        
        # Build action history summary with errors
        action_history = []
        for action in self.state.actions_taken[-5:]:  # Last 5 actions
            action_history.append({
                "type": action.action_type,
                "selector": action.selector,
                "success": action.success,
                "error": action.error_message if not action.success else None
            })
        
        # Analyze failed selectors to provide hints
        failed_selectors = {}
        for action in self.state.actions_taken:
            if not action.success and action.selector:
                if action.selector not in failed_selectors:
                    failed_selectors[action.selector] = {
                        "count": 0,
                        "action_type": action.action_type,
                        "error": action.error_message
                    }
                failed_selectors[action.selector]["count"] += 1
        
        # Build hints for LLM based on failures
        selector_hints = []
        for selector, info in failed_selectors.items():
            if info["count"] >= 1:  # Show hints after just 1 failure
                hint = f"❌ '{selector}' FAILED {info['count']}x ({info['action_type']})\n   Error: {info['error']}\n   "
                if "hidden" in info["error"].lower() or "not visible" in info["error"].lower() or "sr-only" in info["error"].lower() or "'str' object has no attribute" in info["error"]:
                    hint += "Solution: HIDDEN CHECKBOX (sr-only/wrapped pattern detected).\n"
                    hint += "   CRITICAL: This selector keeps failing! Try a DIFFERENT checkbox or skip this field.\n"
                    hint += "   The checkbox interaction is broken for this specific element.\n"
                    hint += f"   → Try selecting a different social platform checkbox instead (Instagram, Twitter, etc.)\n"
                    hint += "   → OR mark as complete if other required fields are filled"
                elif "Value verification failed" in info["error"] and "phone" in selector.lower():
                    hint += "Solution: Phone validation failed - field rejects the value.\n"
                    hint += "   → Skip this field and continue filling other fields\n"
                    hint += "   → Form may accept submission without phone"
                elif "Could not find" in info["error"]:
                    hint += "Solution: Element not clickable. Try: parent div, label, or visible text search"
                elif "Timeout" in info["error"]:
                    hint += "Solution: Selector doesn't exist. Find correct selector from HTML/screenshot"
                selector_hints.append(hint)
        
        # Log the hints so we can debug
        if selector_hints:
            logger.warning(f"⚠️ Generated {len(selector_hints)} failure hints for LLM:")
            for hint in selector_hints:
                logger.warning(f"   {hint}")
        
        context = {
            "goal": "Sign up for the email list using provided credentials",
            "credentials": self.credentials,
            "current_step": self.state.current_step,
            "page_url": page_state.get("url", ""),
            "visible_inputs": page_state.get("inputs", []),
            "visible_buttons": page_state.get("buttons", []),
            "page_text_sample": page_state.get("visible_text", "")[:500],
            "simplified_html": page_state.get("simplified_html", ""),
            "fields_filled": list(self.state.fields_filled.keys()),
            "action_history": action_history,
            "has_success_indicator": page_state.get("has_success_indicator", False),
            "failed_selector_hints": selector_hints,  # NEW: Add failure hints
            "checkboxes_checked": self.state.checkboxes_checked  # NEW: Track checked checkboxes
        }
        
        return context
    
    def _parse_llm_response(self, llm_response: Dict[str, Any]) -> Optional[AgentAction]:
        """Parse LLM response into an AgentAction."""
        
        try:
            action_type = llm_response.get("action", "unknown")
            selector = llm_response.get("selector", "")
            value = llm_response.get("value", "")
            reasoning = llm_response.get("reasoning", "")
            
            # Map field types to actual values
            if action_type == "fill_field":
                field_type = llm_response.get("field_type", "").lower()
                
                if field_type == "email":
                    value = self.credentials.get("email", "")
                
                elif field_type in ["full_name", "fullname", "full name"]:
                    # Full name field - use first + last
                    value = self.credentials.get("full_name", "")
                
                elif field_type in ["first_name", "firstname", "first name"]:
                    value = self.credentials.get("first_name", "")
                
                elif field_type in ["last_name", "lastname", "last name"]:
                    value = self.credentials.get("last_name", "")
                
                elif field_type in ["country_code", "countrycode", "country code"]:
                    # Country code dropdown
                    phone_data = self.credentials.get("phone", {})
                    value = phone_data.get("country_code", "+1")
                
                elif field_type in ["phone", "phone_number", "phonenumber"]:
                    # Phone number field
                    phone_data = self.credentials.get("phone", {})
                    # Check if LLM specified to use only the number (for forms with separate country code dropdown)
                    if llm_response.get("use_phone_number_only", False):
                        value = phone_data.get("number", "")
                    else:
                        value = phone_data.get("full", "")
                
                elif field_type in ["phone_fallback", "phonefallback"]:
                    # Phone fallback - generate a random phone number for the default country code
                    # Used when country code selection fails and we need to match the default
                    import random
                    
                    # Try to detect country code from LLM reasoning
                    country_code = "+1"  # Default to US
                    reasoning_text = llm_response.get("reasoning", "") + llm_response.get("visual_observation", "")
                    
                    if "+92" in reasoning_text or "92" in reasoning_text or "Pakistan" in reasoning_text:
                        # Pakistan: 10 digits with valid operator prefix
                        # Valid prefixes: 300-305 (Jazz), 310-318 (Jazz), 320-323 (Warid/Jazz)
                        #                 330-336 (Ufone), 340-347 (Telenor), 355 (Warid)
                        country_code = "+92"
                        valid_prefixes = ['300', '301', '302', '303', '304', '305',
                                         '310', '311', '312', '313', '314', '315', '316', '317', '318',
                                         '320', '321', '322', '323',
                                         '330', '331', '332', '333', '334', '335', '336',
                                         '340', '341', '342', '343', '344', '345', '346', '347',
                                         '355']
                        prefix = random.choice(valid_prefixes)
                        random_number = prefix + ''.join([str(random.randint(0, 9)) for _ in range(7)])
                    elif "+91" in reasoning_text or "India" in reasoning_text:
                        # India: 10 digits starting with 6-9
                        country_code = "+91"
                        random_number = str(random.randint(6, 9)) + ''.join([str(random.randint(0, 9)) for _ in range(9)])
                    elif "+44" in reasoning_text or "UK" in reasoning_text:
                        # UK: 10 digits starting with 7
                        country_code = "+44"
                        random_number = '7' + ''.join([str(random.randint(0, 9)) for _ in range(9)])
                    elif "+61" in reasoning_text or "Australia" in reasoning_text:
                        # Australia: 9 digits starting with 4
                        country_code = "+61"
                        random_number = '4' + ''.join([str(random.randint(0, 9)) for _ in range(8)])
                    elif "+971" in reasoning_text or "UAE" in reasoning_text or "Dubai" in reasoning_text:
                        # UAE: 9 digits starting with 5
                        country_code = "+971"
                        random_number = '5' + ''.join([str(random.randint(0, 9)) for _ in range(8)])
                    else:
                        # US/Default: 10 digits, area code 2XX-9XX
                        country_code = "+1"
                        random_number = str(random.randint(2, 9)) + ''.join([str(random.randint(0, 9)) for _ in range(9)])
                    
                    value = random_number
                    logger.info(f"   📱 Generated fallback phone number for {country_code}: {random_number}")
                
                elif field_type == "name":
                    # Generic "name" - try to determine from context, default to full_name
                    value = self.credentials.get("full_name", "")
                
                elif field_type in ["business_name", "businessname", "business name", "company", "company_name"]:
                    # Business name - generate a random one
                    import random
                    business_types = ["Marketing", "Consulting", "Solutions", "Digital", "Creative", "Tech", "Media"]
                    business_names = ["Pro", "Plus", "Group", "Agency", "Services", "Studio", "Partners"]
                    value = f"{random.choice(business_types)} {random.choice(business_names)}"
                
                elif field_type in ["checkbox", "radio"]:
                    # Checkbox/radio - set to checked
                    value = "true"
                
                else:
                    # Unknown field type - use the value from LLM or generate placeholder
                    if not value:
                        # Generate a generic placeholder based on field type
                        value = f"AutoFill_{field_type}"
            
            return AgentAction(
                action_type=action_type,
                selector=selector,
                value=value,
                reasoning=reasoning
            )
            
        except Exception as e:
            logger.error(f"Error parsing LLM response: {e}")
            return None
    
    async def _execute_action(self, action: AgentAction) -> Dict[str, Any]:
        """
        Execute an action on the page.
        
        Args:
            action: AgentAction to execute
            
        Returns:
            Dictionary with execution result
        """
        logger.debug(f"⚡ Executing: {action.action_type}")
        
        try:
            if action.action_type == "fill_field":
                return await self._execute_fill_field(action)
            
            elif action.action_type == "click":
                return await self._execute_click(action)
            
            elif action.action_type == "wait":
                return await self._execute_wait(action)
            
            elif action.action_type == "complete":
                return {"success": True, "message": "Task complete"}
            
            else:
                return {"success": False, "error": f"Unknown action type: {action.action_type}"}
                
        except Exception as e:
            logger.error(f"Error executing action: {e}")
            return {"success": False, "error": str(e)}
    
    async def _execute_fill_field(self, action: AgentAction) -> Dict[str, Any]:
        """Fill a form field."""
        try:
            if not action.selector or not action.value:
                return {"success": False, "error": "Missing selector or value"}
            
            # Parse selector to handle :contains() pseudo-class
            parsed_selector = self._parse_selector(action.selector)
            
            # Wait for element (use state='attached' to include hidden elements)
            # This is important for sr-only checkboxes and hidden inputs
            element = await self.page.wait_for_selector(parsed_selector, state='attached', timeout=5000)
            
            if not element:
                return {"success": False, "error": f"Element not found: {action.selector}"}
            
            # Check if it's a select/dropdown element or checkbox
            tag_name = await element.evaluate("el => el.tagName")
            input_type = await element.evaluate("el => el.type || ''")
            
            if tag_name == "SELECT":
                # Check if visible
                is_visible = await element.is_visible()
                if not is_visible:
                    return {"success": False, "error": "Element not visible"}
                
                # Handle dropdown/select element
                try:
                    await element.select_option(value=action.value)
                    logger.success(f"✅ Selected option in dropdown: {action.selector}")
                    return {"success": True, "message": "Dropdown option selected"}
                except:
                    # Try selecting by label if value doesn't work
                    try:
                        await element.select_option(label=action.value)
                        logger.success(f"✅ Selected option by label in dropdown: {action.selector}")
                        return {"success": True, "message": "Dropdown option selected by label"}
                    except:
                        return {"success": False, "error": "Could not select dropdown option"}
            
            elif input_type in ["checkbox", "radio"]:
                # Handle checkbox/radio elements (may be hidden with sr-only)
                is_visible = await element.is_visible()
                is_checked = await element.is_checked()
                should_check = action.value.lower() in ["true", "yes", "1", "on"] if isinstance(action.value, str) else bool(action.value)
                
                # If checkbox is hidden (common pattern with sr-only), try clicking the label instead
                if not is_visible:
                    logger.info(f"   📦 Hidden checkbox detected (sr-only/wrapped pattern)...")
                    try:
                        checkbox_id = await element.get_attribute("id")
                        
                        # Strategy 1: Try to click via parent label with JavaScript (most reliable for wrapped labels)
                        try:
                            has_parent_label = await element.evaluate("""el => {
                                const label = el.closest('label');
                                return label !== null;
                            }""")
                            
                            if has_parent_label:
                                logger.info(f"      → Found wrapping <label>, clicking via JavaScript...")
                                # Click the parent label directly via JavaScript
                                await element.evaluate("el => el.closest('label').click()")
                                await asyncio.sleep(0.3)
                                
                                # Verify checkbox state
                                is_now_checked = await element.is_checked()
                                if is_now_checked == should_check:
                                    logger.success(f"✅ Hidden checkbox toggled via parent label click (JS)")
                                    # Track checked checkbox
                                    if should_check and action.selector not in self.state.checkboxes_checked:
                                        self.state.checkboxes_checked.append(action.selector)
                                    return {"success": True, "message": "Checkbox toggled via label JS click"}
                                else:
                                    logger.info(f"      → Label clicked but state is {is_now_checked}, expected {should_check}")
                        except Exception as e:
                            logger.debug(f"      Parent label JS click failed: {e}")
                        
                        # Strategy 2: Find and click separate label with for="id" attribute
                        if checkbox_id:
                            try:
                                label = await self.page.query_selector(f'label[for="{checkbox_id}"]')
                                if label:
                                    logger.info(f"      → Found separate label[for='{checkbox_id}'], clicking...")
                                    await label.click()
                                    await asyncio.sleep(0.3)
                                    
                                    is_now_checked = await element.is_checked()
                                    if is_now_checked == should_check:
                                        logger.success(f"✅ Hidden checkbox toggled via separate label click")
                                        # Track checked checkbox
                                        if should_check and action.selector not in self.state.checkboxes_checked:
                                            self.state.checkboxes_checked.append(action.selector)
                                        return {"success": True, "message": "Checkbox toggled via label[for] click"}
                            except Exception as e:
                                logger.debug(f"      Separate label click failed: {e}")
                        
                        # Strategy 3: Force with JavaScript + trigger all events (last resort)
                        logger.info(f"      → Using JavaScript force-check with full event chain")
                        await element.evaluate(f"""el => {{
                            el.checked = {str(should_check).lower()};
                            // Trigger multiple events to ensure validation
                            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            el.dispatchEvent(new Event('click', {{ bubbles: true }}));
                            // Also trigger on parent label if exists
                            const label = el.closest('label');
                            if (label) {{
                                label.dispatchEvent(new Event('click', {{ bubbles: true }}));
                            }}
                        }}""")
                        await asyncio.sleep(0.3)
                        
                        # Final verification
                        final_checked = await element.is_checked()
                        if final_checked == should_check:
                            logger.success(f"✅ Hidden checkbox force-checked successfully")
                            # Track checked checkbox
                            if should_check and action.selector not in self.state.checkboxes_checked:
                                self.state.checkboxes_checked.append(action.selector)
                            return {"success": True, "message": "Checkbox checked with JS"}
                        else:
                            logger.warning(f"      ⚠️ Checkbox value set but verification failed")
                            return {"success": True, "message": "Checkbox processed (state uncertain)"}
                            
                    except Exception as e:
                        logger.warning(f"   ❌ Failed to interact with hidden checkbox: {e}")
                        return {"success": False, "error": f"Cannot interact with hidden checkbox: {str(e)}"}
                
                # Visible checkbox - use normal methods
                if should_check and not is_checked:
                    await element.check()
                    logger.success(f"✅ Checked: {action.selector}")
                    # Track checked checkbox
                    if action.selector not in self.state.checkboxes_checked:
                        self.state.checkboxes_checked.append(action.selector)
                    return {"success": True, "message": "Checkbox/radio checked"}
                elif not should_check and is_checked:
                    await element.uncheck()
                    logger.success(f"✅ Unchecked: {action.selector}")
                    return {"success": True, "message": "Checkbox/radio unchecked"}
                else:
                    logger.success(f"✅ Checkbox already in correct state: {action.selector}")
                    # Track if already checked
                    if is_checked and action.selector not in self.state.checkboxes_checked:
                        self.state.checkboxes_checked.append(action.selector)
                    return {"success": True, "message": "Checkbox already in correct state"}
            else:
                # Handle regular input field
                # Check if visible (for non-checkbox fields)
                is_visible = await element.is_visible()
                if not is_visible:
                    return {"success": False, "error": "Element not visible"}
                
                # Convert value to string if it's not (handles phone dict)
                value_str = action.value
                if isinstance(value_str, dict):
                    # Phone number dict - use 'full' field
                    value_str = value_str.get('full', str(value_str))
                elif not isinstance(value_str, str):
                    value_str = str(value_str)
                
                # Click to focus
                await element.click()
                await asyncio.sleep(0.3)
                
                # Fill the field
                await element.fill(value_str)
                await asyncio.sleep(0.5)
                
                # Verify value was set
                filled_value = await element.input_value()
                if filled_value == value_str:
                    logger.success(f"✅ Filled field: {action.selector}")
                    return {"success": True, "message": "Field filled successfully"}
                else:
                    return {"success": False, "error": "Value verification failed"}
            
        except Exception as e:
            error_msg = str(e)
            # Provide helpful error message for invalid selectors
            if "is not a valid selector" in error_msg or "SyntaxError" in error_msg:
                logger.warning(f"⚠️ Invalid selector syntax: {action.selector}")
                return {"success": False, "error": f"Invalid CSS selector: {action.selector}"}
            return {"success": False, "error": error_msg}
    
    async def _execute_click(self, action: AgentAction) -> Dict[str, Any]:
        """Click an element with multiple fallback strategies."""
        import re
        
        try:
            if not action.selector:
                return {"success": False, "error": "Missing selector"}
            
            # Strategy 1: Try the selector as-is
            try:
                element = await self.page.wait_for_selector(action.selector, timeout=3000)
                if element and await element.is_visible():
                    await element.scroll_into_view_if_needed()
                    await element.click()
                    logger.success(f"✅ Clicked (direct selector): {action.selector}")
                    await asyncio.sleep(2)
                    return {"success": True, "message": "Element clicked"}
            except:
                pass
            
            # Strategy 2: Parse and try converted selector
            parsed_selector = self._parse_selector(action.selector)
            try:
                element = await self.page.wait_for_selector(parsed_selector, timeout=3000)
                if element and await element.is_visible():
                    await element.scroll_into_view_if_needed()
                    await element.click()
                    logger.success(f"✅ Clicked (parsed selector): {parsed_selector}")
                    await asyncio.sleep(2)
                    return {"success": True, "message": "Element clicked"}
            except:
                pass
            
            # Strategy 3: Extract text from selector and try text-based search
            if "contains" in action.selector.lower() or "text" in action.selector.lower():
                text_match = re.search(r'["\']([^"\']+)["\']', action.selector)
                if text_match:
                    search_text = text_match.group(1)
                    logger.info(f"   Trying text-based search for: '{search_text}'")
                    
                    # Try multiple tag types
                    for tag in ["button", "a", "div", "span", "input"]:
                        try:
                            # Case-insensitive partial text match
                            element = await self.page.locator(f"{tag}:has-text('{search_text}')").first.element_handle(timeout=2000)
                            if element:
                                await element.scroll_into_view_if_needed()
                                await element.click()
                                logger.success(f"✅ Clicked {tag} with text: {search_text}")
                                await asyncio.sleep(2)
                                return {"success": True, "message": f"Clicked {tag} element"}
                        except:
                            continue
            
            # Strategy 4: Try to find by button text using page.get_by_role
            if "button" in action.selector.lower():
                text_match = re.search(r'["\']([^"\']+)["\']', action.selector)
                if text_match:
                    search_text = text_match.group(1)
                    try:
                        await self.page.get_by_role("button", name=re.compile(search_text, re.IGNORECASE)).first.click(timeout=2000)
                        logger.success(f"✅ Clicked button by role: {search_text}")
                        await asyncio.sleep(2)
                        return {"success": True, "message": "Button clicked by role"}
                    except:
                        pass
            
            # Strategy 5: Handle partial/truncated class selectors (e.g., div.cursor-pointer.select-none.rou)
            if "." in action.selector and not action.selector.endswith("}") and not action.selector.endswith("]"):
                # Extract tag and first few classes
                parts = action.selector.split(".")
                if len(parts) >= 2:
                    tag = parts[0] if parts[0] else "div"
                    # Try with first 2 classes only (more specific selectors often fail if truncated)
                    simplified_classes = parts[1:3]
                    simplified_selector = f"{tag}.{'.'.join(simplified_classes)}" if simplified_classes else tag
                    
                    logger.info(f"   Trying simplified class selector: {simplified_selector}")
                    try:
                        elements = await self.page.query_selector_all(simplified_selector)
                        if elements:
                            # Find the first visible one
                            for elem in elements:
                                if await elem.is_visible():
                                    await elem.scroll_into_view_if_needed()
                                    await elem.click()
                                    logger.success(f"✅ Clicked with simplified selector: {simplified_selector}")
                                    await asyncio.sleep(2)
                                    return {"success": True, "message": "Clicked with simplified selector"}
                    except:
                        pass
            
            # Strategy 6: If it looks like a country code dropdown, try common patterns
            if "country" in action.selector.lower() or "code" in action.selector.lower() or (action.reasoning and "country" in action.reasoning.lower()):
                logger.info("   Trying common country code dropdown patterns...")
                country_patterns = [
                    "div[role='button']",  # Common for custom dropdowns
                    "button[type='button']",
                    "div.cursor-pointer",
                    "[class*='country']",
                    "[class*='phone']",
                    "div:has-text('+')",  # Look for divs with + sign
                ]
                
                for pattern in country_patterns:
                    try:
                        elements = await self.page.query_selector_all(pattern)
                        for elem in elements[:5]:  # Try first 5 matches
                            if await elem.is_visible():
                                text = await elem.text_content()
                                if text and ('+' in text or 'country' in text.lower()):
                                    await elem.scroll_into_view_if_needed()
                                    await elem.click()
                                    logger.success(f"✅ Clicked country code dropdown: {pattern}")
                                    await asyncio.sleep(2)
                                    return {"success": True, "message": "Country code dropdown clicked"}
                    except:
                        continue
            
            # All strategies failed
            return {"success": False, "error": f"Could not find clickable element: {action.selector}"}
            
        except Exception as e:
            error_msg = str(e)
            return {"success": False, "error": error_msg}
            
            if not element:
                return {"success": False, "error": f"Element not found: {action.selector}"}
            
            # Get element info for smart clicking
            tag_name = await element.evaluate("el => el.tagName")
            input_type = await element.evaluate("el => el.type || ''")
            
            # For submit inputs, try form submission
            if tag_name == "INPUT" and input_type == "submit":
                try:
                    await element.evaluate("el => el.form.submit()")
                    logger.success(f"✅ Submitted form via: {action.selector}")
                    await asyncio.sleep(2)
                    return {"success": True, "message": "Form submitted"}
                except:
                    pass
            
            # For divs/spans with onclick, trigger the handler
            if tag_name in ["DIV", "SPAN", "A"]:
                has_onclick = await element.evaluate("el => el.onclick != null || el.getAttribute('onclick') != null")
                if has_onclick:
                    try:
                        # Try to trigger onclick directly
                        await element.evaluate("el => el.onclick ? el.onclick() : el.click()")
                        logger.success(f"✅ Triggered onclick: {action.selector}")
                        await asyncio.sleep(2)
                        return {"success": True, "message": "Onclick triggered"}
                    except:
                        pass
            
            # Check if visible and enabled
            is_visible = await element.is_visible()
            is_enabled = await element.is_enabled()
            
            if not is_visible or not is_enabled:
                # Try clicking anyway for hidden submit inputs
                if input_type == "submit":
                    try:
                        await element.click(force=True)
                        logger.success(f"✅ Force-clicked hidden submit: {action.selector}")
                        await asyncio.sleep(2)
                        return {"success": True, "message": "Element force-clicked"}
                    except:
                        pass
                return {"success": False, "error": "Element not clickable"}
            
            # Scroll into view
            await element.scroll_into_view_if_needed()
            await asyncio.sleep(0.3)
            
            # Click
            await element.click()
            logger.success(f"✅ Clicked: {action.selector}")
            
            # Wait for any page changes
            await asyncio.sleep(2)
            
            return {"success": True, "message": "Element clicked"}
            
        except Exception as e:
            error_msg = str(e)
            # Provide helpful error message for invalid selectors
            if "is not a valid selector" in error_msg or "SyntaxError" in error_msg:
                logger.warning(f"⚠️ Invalid selector syntax: {action.selector}")
                return {"success": False, "error": f"Invalid CSS selector: {action.selector}"}
            return {"success": False, "error": error_msg}
    
    async def _execute_wait(self, action: AgentAction) -> Dict[str, Any]:
        """Wait for a specified duration."""
        try:
            wait_time = float(action.value) if action.value else 2.0
            logger.debug(f"⏳ Waiting {wait_time}s...")
            await asyncio.sleep(wait_time)
            return {"success": True, "message": f"Waited {wait_time}s"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _handle_captcha_in_agent(self) -> tuple[bool, Optional[Dict[str, str]]]:
        """
        Detect and solve CAPTCHA during agent execution using TWO-PHASE APPROACH:
        PHASE 1: STRICTLY search for reCAPTCHA sitekey (for 2Captcha)
        PHASE 2: ONLY if Phase 1 fails, search for skip/bypass buttons
        
        Returns:
            tuple: (solved: bool, bypass_action: Optional[Dict])
                - (True, None): CAPTCHA was solved successfully
                - (False, {...}): Sitekey not found, but skip button detected
                - (False, None): Nothing worked
        """
        try:
            # Take screenshot for LLM analysis
            screenshot_base64 = await self._capture_screenshot()
            page_html = await self.page.content()
            
            # ==================== PHASE 1: STRICT SITEKEY SEARCH ====================
            logger.info("   🔍 PHASE 1: Searching for reCAPTCHA sitekey...")
            
            sitekey = None
            if "recaptcha" in page_html.lower() or "g-recaptcha" in page_html:
                logger.info("   ✓ reCAPTCHA detected in HTML")
                
                # Strategy 1: Regex-based extraction
                import re
                sitekey_match = re.search(r'data-sitekey="([^"]+)"', page_html)
                if not sitekey_match:
                    sitekey_match = re.search(r'sitekey["\']?\s*:\s*["\']([^"\']+)', page_html)
                
                if sitekey_match:
                    sitekey = sitekey_match.group(1)
                    logger.success(f"   ✅ Found sitekey with regex: {sitekey[:30]}...")
                else:
                    # Strategy 2: LLM-based sitekey extraction (STRICT)
                    logger.info("   🤖 Using LLM to locate sitekey in HTML...")
                    sitekey = await self._llm_find_sitekey(page_html[:15000])
                    if sitekey:
                        logger.success(f"   ✅ LLM found sitekey: {sitekey[:30]}...")
            
            # If sitekey found, solve with 2Captcha
            if sitekey:
                api_key = self.credentials.get('_captcha_api_key')
                if not api_key or api_key.startswith('YOUR_'):
                    logger.warning("   ⚠️ 2Captcha not configured")
                else:
                    logger.info("   🤖 Solving with 2Captcha...")
                    token = await self._solve_recaptcha_2captcha(sitekey, self.page.url)
                    
                    if token:
                        logger.info("   💉 Injecting token...")
                        await self._inject_recaptcha_token(token)
                        logger.success("   ✅ CAPTCHA SOLVED!")
                        return (True, None)
                    else:
                        logger.warning("   ❌ 2Captcha failed")
            else:
                logger.warning("   ⚠️ No sitekey found")
            
            # ==================== PHASE 2: LOOK FOR SKIP/BYPASS ====================
            logger.info("   🔍 PHASE 2: Looking for skip/bypass options...")
            
            bypass_action = await self._llm_find_bypass_button(screenshot_base64)
            
            if bypass_action:
                logger.info(f"   ✅ Found bypass option: '{bypass_action.get('text')}'")
                logger.info(f"   📍 Selector: {bypass_action.get('selector')}")
                return (False, bypass_action)  # Return to agent to click it
            else:
                logger.warning("   ❌ No bypass option found")
                return (False, None)
            
        except Exception as e:
            logger.error(f"   ❌ Error handling CAPTCHA: {e}")
            return (False, None)
    
    async def _solve_recaptcha_2captcha(self, sitekey: str, page_url: str) -> Optional[str]:
        """Solve reCAPTCHA using 2Captcha service."""
        try:
            # Import 2Captcha
            from twocaptcha import TwoCaptcha
            
            # Get API key from credentials (passed from orchestrator)
            api_key = self.credentials.get('_captcha_api_key')
            if not api_key:
                logger.warning("   2Captcha API key not configured")
                return None
            
            solver = TwoCaptcha(api_key)
            
            logger.info("   📤 Submitting to 2Captcha...")
            logger.info("   ⏳ Waiting for solution (typically 30-60 seconds)...")
            
            # Solve reCAPTCHA v2
            result = solver.recaptcha(sitekey=sitekey, url=page_url)
            
            if result and result.get('code'):
                logger.success(f"   ✅ Received solution from 2Captcha (token: {result['code'][:30]}...)")
                return result['code']
            else:
                logger.warning("   ❌ No solution received from 2Captcha")
                return None
                
        except ImportError:
            logger.error("   ❌ 2Captcha library not installed")
            logger.info("   Install with: pip install 2captcha-python")
            return None
        except Exception as e:
            logger.error(f"   ❌ 2Captcha error: {e}")
            return None
    
    async def _inject_recaptcha_token(self, token: str):
        """Inject reCAPTCHA token into page."""
        try:
            await self.page.evaluate(f"""
                // Inject into g-recaptcha-response textarea
                var textarea = document.getElementById('g-recaptcha-response');
                if (textarea) {{
                    textarea.innerHTML = '{token}';
                    textarea.value = '{token}';
                }}
                
                // Override grecaptcha.getResponse
                if (typeof grecaptcha !== 'undefined') {{
                    grecaptcha.getResponse = function() {{ return '{token}'; }};
                }}
                
                // Trigger callback if exists
                if (typeof ___grecaptcha_cfg !== 'undefined') {{
                    var clients = ___grecaptcha_cfg.clients;
                    for (var id in clients) {{
                        if (clients[id].callback) {{
                            clients[id].callback('{token}');
                        }}
                    }}
                }}
            """)
            await asyncio.sleep(1)
        except Exception as e:
            logger.warning(f"   Token injection warning: {e}")
    
    async def _llm_find_sitekey(self, page_html: str) -> Optional[str]:
        """Use LLM to STRICTLY find reCAPTCHA sitekey in HTML (for 2Captcha solving)."""
        try:
            prompt = f"""You are analyzing HTML to find a reCAPTCHA sitekey for automated solving.

HTML SNIPPET:
{page_html}

CRITICAL TASK: Find the reCAPTCHA sitekey ONLY. Do NOT look for skip buttons or alternative approaches.

WHAT TO LOOK FOR:
1. data-sitekey="..." attribute in HTML elements
2. sitekey: "..." in JavaScript configuration
3. grecaptcha.render(..., {{ sitekey: "..." }})
4. Sitekey format: Long alphanumeric string (typically 40 characters)
   Example: "6LcE2QkUAAAAAIriIwk10Y_vV5BkN7s8m6XqxOp"

IMPORTANT:
- ONLY return a sitekey if you find one
- Do NOT suggest skip buttons or bypass methods
- Do NOT return null unless you are 100% certain no sitekey exists

Return ONLY this JSON:
{{
    "sitekey": "the-exact-sitekey-string-or-null",
    "found": true or false,
    "location": "exact location (e.g., 'line 234: data-sitekey attribute')"
}}

If no sitekey found: {{"sitekey": null, "found": false, "location": "not found"}}
"""
            
            response = await self.llm_analyzer._call_openai_agent(prompt, [], None)
            
            if response and response.get("found") and response.get("sitekey"):
                sitekey = response.get("sitekey")
                # Validate sitekey format (should be alphanumeric and reasonably long)
                if len(sitekey) > 20 and sitekey.replace("-", "").replace("_", "").isalnum():
                    logger.info(f"   📍 LLM found it in: {response.get('location')}")
                    return sitekey
                else:
                    logger.warning(f"   ⚠️ LLM returned invalid sitekey format: {sitekey}")
                    return None
            else:
                return None
                
        except Exception as e:
            logger.debug(f"   LLM sitekey search error: {e}")
            return None
    
    async def _llm_find_bypass_button(self, screenshot_base64: Optional[str]) -> Optional[Dict[str, str]]:
        """
        Use LLM Vision to ONLY identify skip/bypass buttons.
        Does NOT attempt to click them - returns selector for agent to click.
        """
        try:
            if not screenshot_base64:
                logger.warning("   ⚠️ No screenshot available for LLM analysis")
                return None
            
            prompt = """You are looking at a CAPTCHA page. Your ONLY task is to identify if there is a skip or bypass button.

DO NOT try to solve the CAPTCHA. ONLY look for:
1. "Skip" button
2. "Continue without CAPTCHA" link
3. "No thanks" option
4. Close/dismiss button (X) that might close the CAPTCHA
5. Any text/button that allows proceeding without solving

IMPORTANT:
- Be SPECIFIC about what you see
- Provide the EXACT text on the button
- Suggest a CSS selector (ID, class, or text-based)
- Do NOT hallucinate buttons that aren't there

Return ONLY this JSON:
{{
    "found": true or false,
    "text": "exact button text you see",
    "selector": "CSS selector (e.g., #skip-btn, .close-captcha, button:has-text('Skip'))",
    "reasoning": "brief description of what you see"
}}

If NO bypass option exists: {{"found": false, "text": null, "selector": null, "reasoning": "No skip/bypass button visible"}}
"""
            
            response = await self.llm_analyzer._call_openai_agent(prompt, [], screenshot_base64)
            
            if response and response.get("found"):
                return {
                    "text": response.get("text"),
                    "selector": response.get("selector"),
                    "reasoning": response.get("reasoning", "")
                }
            else:
                return None
                
        except Exception as e:
            logger.debug(f"   LLM bypass search error: {e}")
            return None

