"""
LLM-powered page analyzer for dynamic form detection and filling.
Uses AI to understand page structure and determine actions.
"""

import asyncio
import json
import re
from typing import Dict, List, Optional, Any
from playwright.async_api import Page
from loguru import logger


class LLMPageAnalyzer:
    """
    Analyze web pages using LLM to determine form filling strategy.
    Works without hardcoded selectors by understanding page structure.
    """
    
    def __init__(self, page: Page, credentials: Dict[str, str], llm_provider: str = "openai", 
                 api_key: Optional[str] = None, llm_config: Optional[Dict[str, Any]] = None):
        """
        Initialize LLM page analyzer.
        
        Args:
            page: Playwright page object
            credentials: User credentials (email, name, phone)
            llm_provider: LLM provider ('openai', 'anthropic', or 'none' for rule-based)
            api_key: API key for LLM service (deprecated, use llm_config)
            llm_config: LLM configuration dict with api_key, model, etc.
        """
        self.page = page
        self.credentials = credentials
        self.llm_provider = llm_provider
        
        # Support both old api_key param and new llm_config
        if llm_config:
            self.llm_config = llm_config
        else:
            self.llm_config = {"api_key": api_key} if api_key else {}
        
    async def analyze_and_fill_form(self) -> Dict[str, Any]:
        """
        Analyze page and fill form dynamically.
        
        Returns:
            Dictionary with success status and actions taken
        """
        logger.info("🔍 Analyzing page with LLM...")
        
        # Get page structure
        page_info = await self._extract_page_info()
        
        # Analyze with LLM or rule-based fallback
        if self.llm_provider != "none" and self.api_key:
            analysis = await self._llm_analyze(page_info)
        else:
            analysis = await self._rule_based_analyze(page_info)
        
        # Execute the filling strategy
        result = await self._execute_filling_strategy(analysis)
        
        return result
    
    async def _extract_page_info(self) -> Dict[str, Any]:
        """Extract relevant information from the page, including HTML and visibility status."""
        try:
            # Get page structure with visibility information + simplified HTML
            page_structure = await self.page.evaluate("""
                () => {
                    const isVisible = (elem) => {
                        if (!elem) return false;
                        const style = window.getComputedStyle(elem);
                        return style.display !== 'none' && 
                               style.visibility !== 'hidden' && 
                               style.opacity !== '0' &&
                               elem.offsetParent !== null;
                    };
                    
                    const result = {
                        title: document.title,
                        url: window.location.href,
                        forms: [],
                        buttons: [],
                        inputs: [],
                        visibleText: document.body.innerText.substring(0, 1000),
                        simplifiedHtml: ''
                    };
                    
                    // Extract simplified HTML (forms, inputs, buttons only)
                    const cleanHtml = document.createElement('div');
                    
                    // Clone visible forms
                    document.querySelectorAll('form').forEach((form, idx) => {
                        if (isVisible(form)) {
                            const formClone = form.cloneNode(true);
                            // Remove scripts and styles
                            formClone.querySelectorAll('script, style, noscript').forEach(el => el.remove());
                            cleanHtml.appendChild(formClone);
                        }
                    });
                    
                    // If no forms, get standalone inputs and buttons
                    if (cleanHtml.children.length === 0) {
                        const container = document.createElement('div');
                        container.id = 'extracted-elements';
                        
                        document.querySelectorAll('input:not([type="hidden"]), textarea, button').forEach(elem => {
                            if (isVisible(elem)) {
                                container.appendChild(elem.cloneNode(true));
                            }
                        });
                        
                        cleanHtml.appendChild(container);
                    }
                    
                    result.simplifiedHtml = cleanHtml.innerHTML;
                    
                    // Find all forms
                    document.querySelectorAll('form').forEach((form, idx) => {
                        const formInfo = {
                            id: form.id || `form_${idx}`,
                            action: form.action,
                            method: form.method,
                            inputs: [],
                            visible: isVisible(form)
                        };
                        
                        form.querySelectorAll('input, textarea, select').forEach(input => {
                            if (input.type !== 'hidden') {
                                formInfo.inputs.push({
                                    type: input.type || 'text',
                                    name: input.name,
                                    id: input.id,
                                    placeholder: input.placeholder || '',
                                    required: input.required,
                                    value: input.value || '',
                                    visible: isVisible(input)
                                });
                            }
                        });
                        
                        result.forms.push(formInfo);
                    });
                    
                    // Find all inputs (even outside forms) - only visible ones, including select/dropdowns/checkboxes/radios
                    document.querySelectorAll('input:not([type="hidden"]), textarea, select').forEach(input => {
                        // For radio/checkbox, also check if parent label is visible
                        const parentLabel = input.closest('label');
                        const isVisibleInput = isVisible(input) || (parentLabel && isVisible(parentLabel));
                        
                        if (isVisibleInput) {
                            const isSelect = input.tagName === 'SELECT';
                            const inputType = input.type || 'text';
                            
                            // Get label text for radio/checkbox
                            let labelText = '';
                            let isHiddenInput = false;
                            let hasWrappingLabel = false;
                            
                            if (inputType === 'radio' || inputType === 'checkbox') {
                                // Check if input itself is hidden (sr-only pattern)
                                isHiddenInput = input.className.includes('sr-only') || 
                                              input.className.includes('visually-hidden') ||
                                              !isVisible(input);
                                
                                if (parentLabel) {
                                    hasWrappingLabel = true;
                                    labelText = parentLabel.textContent?.trim() || '';
                                } else {
                                    // Look for associated label
                                    const label = input.id ? document.querySelector(`label[for="${input.id}"]`) : null;
                                    labelText = label ? label.textContent?.trim() : '';
                                }
                            }
                            
                            result.inputs.push({
                                type: isSelect ? 'select' : inputType,
                                name: input.name,
                                id: input.id,
                                placeholder: input.placeholder || '',
                                className: input.className,
                                ariaLabel: input.getAttribute('aria-label') || '',
                                label: labelText,
                                value: input.value || '',
                                checked: input.checked || false,
                                visible: true,
                                hidden_input: isHiddenInput,  // Flag for sr-only checkboxes
                                wrapped_in_label: hasWrappingLabel,  // Flag for wrapped pattern
                                options: isSelect ? Array.from(input.options).map(opt => opt.value || opt.text) : []
                            });
                        }
                    });
                    
                    // Find div/span-based checkboxes/options (common in modern forms)
                    // These are clickable divs that act as checkboxes but aren't actual <input> elements
                    const divCheckboxSelectors = [
                        'div[role="checkbox"]',
                        'div[role="option"]',
                        'div[class*="option"]',
                        'div[class*="choice"]',
                        'div[class*="selector"]',
                        'div[class*="card"][role="button"]',
                        'label[class*="option"]',
                        'label[class*="choice"]'
                    ].join(',');
                    
                    document.querySelectorAll(divCheckboxSelectors).forEach(opt => {
                        if (isVisible(opt)) {
                            result.inputs.push({
                                type: 'div-checkbox',  // Special type for div-based checkboxes
                                name: opt.getAttribute('name') || '',
                                id: opt.id,
                                placeholder: '',
                                className: opt.className,
                                ariaLabel: opt.getAttribute('aria-label') || '',
                                label: opt.textContent?.trim() || '',
                                value: opt.getAttribute('value') || '',
                                checked: opt.getAttribute('aria-checked') === 'true' || opt.classList.contains('checked') || opt.classList.contains('selected'),
                                visible: true,
                                options: [],
                                selector: `#${opt.id}` || `.${opt.className.split(' ')[0]}` || `div:has-text('${opt.textContent?.trim().substring(0, 20)}')`
                            });
                        }
                    });
                    
                    // Find all clickable elements (buttons, inputs, divs, anchors, etc.)
                    const clickableSelectors = [
                        'button',
                        'input[type="submit"]',
                        'input[type="button"]',
                        'a[role="button"]',
                        'a[href="#"]',
                        'a[onclick]',
                        'div[onclick]',
                        'div[role="button"]',
                        'div.btn',
                        'div.button',
                        'div[class*="btn"]',
                        'div[class*="submit"]',
                        'span[onclick]',
                        'span[role="button"]'
                    ].join(',');
                    
                    document.querySelectorAll(clickableSelectors).forEach(btn => {
                        // For inputs, check if visible OR if it's a submit type
                        const isVisibleOrSubmit = isVisible(btn) || (btn.tagName === 'INPUT' && btn.type === 'submit');
                        if (isVisibleOrSubmit) {
                            result.buttons.push({
                                text: btn.textContent?.trim() || btn.value || btn.innerText?.trim() || '',
                                type: btn.type || btn.tagName.toLowerCase(),
                                id: btn.id,
                                name: btn.name || '',
                                className: btn.className,
                                onclick: btn.getAttribute('onclick') ? 'yes' : 'no',
                                visible: isVisible(btn)
                            });
                        }
                    });
                    
                    return result;
                }
            """)
            
            logger.debug(f"Found {len(page_structure.get('forms', []))} forms, "
                        f"{len(page_structure.get('inputs', []))} inputs, "
                        f"{len(page_structure.get('buttons', []))} buttons")
            
            return page_structure
            
        except Exception as e:
            logger.error(f"Error extracting page info: {e}")
            return {"forms": [], "inputs": [], "buttons": []}
    
    async def _rule_based_analyze(self, page_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Rule-based analysis (fallback when no LLM).
        Uses pattern matching to identify fields - ONLY VISIBLE ONES.
        """
        logger.info("Using rule-based analysis...")
        
        strategy = {
            "fields_to_fill": [],
            "submit_button": None
        }
        
        # Only use standalone visible inputs (forms might have hidden fields)
        all_inputs = page_info.get('inputs', [])
        
        # Filter to only visible inputs
        visible_inputs = [inp for inp in all_inputs if inp.get('visible', True)]
        
        logger.debug(f"Found {len(visible_inputs)} visible input fields")
        
        seen_types = set()  # Avoid duplicates
        
        # Identify email field
        for input_field in visible_inputs:
            field_text = f"{input_field.get('name', '')} {input_field.get('id', '')} {input_field.get('placeholder', '')} {input_field.get('ariaLabel', '')}".lower()
            
            if 'email' not in seen_types and (input_field.get('type') == 'email' or 'email' in field_text or 'e-mail' in field_text):
                strategy["fields_to_fill"].append({
                    "field_type": "email",
                    "value": self.credentials['email'],
                    "selector": self._build_selector(input_field),
                    "found_by": "email pattern"
                })
                seen_types.add('email')
                continue
            
            # Identify name field  
            if 'name' not in seen_types and 'name' in field_text and 'last' not in field_text and 'username' not in field_text and 'email' not in field_text:
                strategy["fields_to_fill"].append({
                    "field_type": "name",
                    "value": self.credentials['first_name'],
                    "selector": self._build_selector(input_field),
                    "found_by": "name pattern"
                })
                seen_types.add('name')
                continue
            
            # Identify phone field
            if 'phone' not in seen_types and (input_field.get('type') == 'tel' or 'phone' in field_text or 'mobile' in field_text or 'cell' in field_text):
                strategy["fields_to_fill"].append({
                    "field_type": "phone",
                    "value": self.credentials['phone'],
                    "selector": self._build_selector(input_field),
                    "found_by": "phone pattern"
                })
                seen_types.add('phone')
                continue
        
        # Find visible submit button
        for button in page_info.get('buttons', []):
            if not button.get('visible', True):
                continue
            button_text = button.get('text', '').lower()
            if any(word in button_text for word in ['submit', 'sign up', 'register', 'join', 'continue', 'get started', 'send', 'next']):
                strategy["submit_button"] = {
                    "text": button.get('text'),
                    "selector": f'button:has-text("{button.get("text")}")'
                }
                break
        
        logger.info(f"Rule-based analysis found {len(strategy['fields_to_fill'])} VISIBLE fields to fill")
        return strategy
    
    async def _llm_analyze(self, page_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Use AI (GPT-4 or Claude) to intelligently analyze the page HTML and determine actions.
        """
        logger.info(f"🤖 Using {self.llm_provider} AI for intelligent HTML analysis...")
        
        try:
            # Get simplified HTML
            html_content = page_info.get('simplifiedHtml', '')
            
            # Truncate HTML if too long (keep it under 6000 chars for context window)
            if len(html_content) > 6000:
                html_content = html_content[:6000] + "\n... (HTML truncated)"
            
            # Prepare the prompt with HTML
            prompt = f"""You are an AI agent tasked with signing up for an email marketing list on a landing page.

CURRENT PAGE INFORMATION:
- URL: {page_info.get('url', 'Unknown')}
- Title: {page_info.get('title', 'Unknown')}

AVAILABLE CREDENTIALS TO USE:
- Name: {self.credentials.get('first_name', 'Test User')}
- Email: {self.credentials.get('email', 'test@example.com')}
- Phone: {self.credentials.get('phone', '+1234567890')}

PAGE HTML (VISIBLE ELEMENTS ONLY):
```html
{html_content}
```

VISIBLE INPUT FIELDS DETECTED:
{self._format_inputs_for_llm(page_info.get('inputs', []))}

VISIBLE BUTTONS DETECTED (with actual selectors):
{self._format_buttons_with_selectors(page_info.get('buttons', []))}

YOUR TASK:
Analyze the HTML structure and visible elements to determine:
1. What input fields need to be filled with which credentials
2. What button to click to submit/continue
3. Whether this is a multi-step form (has hidden fields that will appear)

IMPORTANT RULES:
- ONLY use fields that are currently VISIBLE (check visibility in the data above)
- For multi-step forms (like ClickFunnels), only fill the CURRENT visible step
- Prioritize email fields - they're usually the first/most important
- If you see "Next", "Continue", or "Get Started" buttons, that's likely the submit button
- Return CSS selectors in format: #id or input[name="fieldname"] or button:has-text("text")
- Use the most specific selector possible (ID > name > class)

Return ONLY a valid JSON object with this exact structure (no markdown, no explanation outside JSON):
{{
    "fields_to_fill": [
        {{"field_type": "email", "value": "{self.credentials.get('email', 'test@example.com')}", "selector": "#email"}},
        {{"field_type": "name", "value": "{self.credentials.get('first_name', 'Test')}", "selector": "#name"}}
    ],
    "submit_button": {{"text": "Sign Up", "selector": "button:has-text('Sign Up')"}},
    "reasoning": "Brief explanation: what fields found, what button to click, if multi-step",
    "is_multistep": false
}}"""

            if self.llm_provider == "openai":
                strategy = await self._call_openai(prompt)
            elif self.llm_provider == "anthropic":
                strategy = await self._call_anthropic(prompt)
            else:
                logger.warning(f"Unknown LLM provider: {self.llm_provider}")
                return await self._rule_based_analyze(page_info)
            
            logger.success(f"✅ AI Analysis: {strategy.get('reasoning', 'No reasoning provided')}")
            logger.info(f"📝 AI identified {len(strategy.get('fields_to_fill', []))} fields to fill")
            return strategy
            
        except Exception as e:
            logger.error(f"AI analysis failed: {e}. Falling back to rule-based.")
            import traceback
            logger.debug(traceback.format_exc())
            return await self._rule_based_analyze(page_info)
    
    def _format_inputs_for_llm(self, inputs: List[Dict]) -> str:
        """Format input fields for LLM prompt."""
        if not inputs:
            return "No visible input fields found."
        
        result = []
        for i, inp in enumerate(inputs[:15], 1):  # Increased to 15 to show more checkboxes
            inp_type = inp.get('type', 'text')
            label = inp.get('label', '')
            is_hidden = inp.get('hidden_input', False)
            is_wrapped = inp.get('wrapped_in_label', False)
            
            # Special formatting for div-checkboxes
            if inp_type == 'div-checkbox':
                result.append(f"{i}. ⚠️ DIV-CHECKBOX (use 'click' action!): '{label}', "
                             f"ID: {inp.get('id', 'N/A')}, "
                             f"Class: {inp.get('className', 'N/A')}")
            elif inp_type in ['checkbox', 'radio']:
                # Add visual indicators for hidden/wrapped checkboxes
                pattern_info = ""
                if is_hidden and is_wrapped:
                    pattern_info = " 🎯 [HIDDEN+WRAPPED: use fill_field]"
                elif is_hidden:
                    pattern_info = " 🎯 [HIDDEN: sr-only pattern]"
                elif is_wrapped:
                    pattern_info = " 🎯 [WRAPPED in label]"
                
                result.append(f"{i}. Type: {inp_type}{pattern_info}, Label: '{label}', "
                             f"ID: {inp.get('id', 'N/A')}, "
                             f"Name: {inp.get('name', 'N/A')}, "
                             f"Checked: {inp.get('checked', False)}")
            else:
                result.append(f"{i}. Type: {inp_type}, "
                             f"Name: {inp.get('name', 'N/A')}, "
                             f"ID: {inp.get('id', 'N/A')}, "
                             f"Placeholder: {inp.get('placeholder', 'N/A')}")
        return "\n".join(result)
    
    def _format_buttons_for_llm(self, buttons: List[Dict]) -> str:
        """Format buttons for LLM prompt."""
        if not buttons:
            return "No visible buttons found."
        
        result = []
        for i, btn in enumerate(buttons[:15], 1):  # Limit to first 15
            result.append(f"{i}. Text: '{btn.get('text', 'N/A')[:50]}', "
                         f"Type: {btn.get('type', 'N/A')}, "
                         f"ID: {btn.get('id', 'N/A')}, "
                         f"Class: {btn.get('className', 'N/A')[:30]}, "
                         f"Onclick: {btn.get('onclick', 'no')}")
        return "\n".join(result)
    
    def _format_buttons_with_selectors(self, buttons: List[Dict]) -> str:
        """Format buttons with suggested CSS selectors."""
        if not buttons:
            return "No visible buttons found."
        
        result = []
        for i, btn in enumerate(buttons[:15], 1):
            text = btn.get('text', '')[:40]
            btn_id = btn.get('id', '')
            btn_class = btn.get('className', '')
            btn_type = btn.get('type', 'button')
            
            # Generate best selector
            if btn_id:
                selector = f"#{btn_id}"
            elif btn_class:
                # Take first class
                first_class = btn_class.split()[0] if btn_class else ''
                selector = f"{btn_type}.{first_class}" if first_class else btn_type
            else:
                selector = f"{btn_type} (use text search: '{text}')"
            
            result.append(f"{i}. Text: '{text}' | Selector: {selector} | ID: {btn_id or 'none'} | Class: {btn_class[:30] or 'none'}")
        
        return "\n".join(result)
    
    async def _call_openai(self, prompt: str) -> Dict[str, Any]:
        """Call OpenAI GPT-4 API (text-only, cheaper than vision)."""
        import aiohttp
        import json
        
        api_key = self.llm_config.get('api_key', '')
        if not api_key or 'YOUR_' in api_key:
            raise ValueError("OpenAI API key not configured")
        
        # Use gpt-4o for best results, or gpt-4-turbo, or gpt-4
        model = self.llm_config.get('model', 'gpt-4o')
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are an expert web automation agent specialized in form filling. Return only valid JSON."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": 1500,
            "temperature": 0.2,  # Lower for more consistent/deterministic responses
            "response_format": {"type": "json_object"}  # Force JSON response
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"OpenAI API error ({response.status}): {error_text}")
                
                result = await response.json()
                content = result['choices'][0]['message']['content']
                
                # Parse JSON response
                strategy = json.loads(content)
                return strategy
    
    async def _call_anthropic(self, prompt: str) -> Dict[str, Any]:
        """Call Anthropic Claude API (text-only)."""
        import aiohttp
        import json
        
        api_key = self.llm_config.get('api_key', '')
        if not api_key:
            raise ValueError("Anthropic API key not configured")
        
        model = self.llm_config.get('model', 'claude-3-5-sonnet-20241022')
        
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01"
        }
        
        # Add system prompt for JSON formatting
        full_prompt = f"""{prompt}

CRITICAL: Return ONLY a valid JSON object. Do not include any markdown formatting, explanations, or text outside the JSON."""
        
        payload = {
            "model": model,
            "max_tokens": 1500,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "user",
                    "content": full_prompt
                }
            ]
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Anthropic API error ({response.status}): {error_text}")
                
                result = await response.json()
                content = result['content'][0]['text']
                
                # Extract JSON from response (Claude might wrap in markdown)
                if '```json' in content:
                    content = content.split('```json')[1].split('```')[0].strip()
                elif '```' in content:
                    content = content.split('```')[1].split('```')[0].strip()
                
                strategy = json.loads(content)
                return strategy
    
    def _build_selector(self, input_field: Dict[str, Any]) -> str:
        """Build a CSS selector for an input field."""
        # Try ID first (most specific)
        if input_field.get('id'):
            return f'#{input_field["id"]}'
        
        # Try name
        if input_field.get('name'):
            return f'input[name="{input_field["name"]}"]'
        
        # Try type + placeholder
        if input_field.get('type') and input_field.get('placeholder'):
            return f'input[type="{input_field["type"]}"][placeholder*="{input_field["placeholder"][:20]}"]'
        
        # Fallback to type
        if input_field.get('type'):
            return f'input[type="{input_field["type"]}"]'
        
        return 'input'
    
    async def _execute_filling_strategy(self, strategy: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the filling strategy determined by analysis."""
        result = {
            "success": False,
            "fields_filled": [],
            "errors": []
        }
        
        try:
            # Fill each identified field
            for field_info in strategy.get("fields_to_fill", []):
                try:
                    selector = field_info['selector']
                    value = field_info['value']
                    
                    logger.info(f"Filling {field_info['field_type']} field: {selector}")
                    
                    # Wait for field
                    element = await self.page.wait_for_selector(selector, timeout=5000)
                    if element:
                        await element.click()
                        await element.fill(value)
                        result["fields_filled"].append(field_info['field_type'])
                        logger.success(f"✅ Filled {field_info['field_type']} field")
                    
                except Exception as e:
                    error_msg = f"Failed to fill {field_info.get('field_type', 'unknown')}: {e}"
                    logger.warning(error_msg)
                    result["errors"].append(error_msg)
            
            # Click submit button
            if strategy.get("submit_button"):
                try:
                    button_selector = strategy["submit_button"]["selector"]
                    logger.info(f"Clicking submit button: {button_selector}")
                    
                    button = await self.page.wait_for_selector(button_selector, timeout=5000)
                    if button:
                        await button.click()
                        logger.success("✅ Submit button clicked")
                        result["success"] = len(result["fields_filled"]) > 0
                    
                except Exception as e:
                    error_msg = f"Failed to click submit: {e}"
                    logger.warning(error_msg)
                    result["errors"].append(error_msg)
            else:
                logger.warning("No submit button identified")
                result["errors"].append("No submit button found")
            
        except Exception as e:
            logger.error(f"Error executing strategy: {e}")
            result["errors"].append(str(e))
        
        return result
    
    async def _call_llm_for_next_action(self, context: Dict[str, Any], 
                                        conversation_history: List[Dict[str, str]],
                                        screenshot_base64: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Call LLM to determine next action in the agent reasoning loop.
        
        Args:
            context: Current page context and state
            conversation_history: Previous conversation turns
            screenshot_base64: Base64 encoded screenshot of current page
            
        Returns:
            Dictionary with next action details or None
        """
        if screenshot_base64:
            logger.info("🤖 Asking LLM for next action (with screenshot vision)...")
        else:
            logger.info("🤖 Asking LLM for next action...")
        
        try:
            # Build prompt for next action
            prompt = self._build_agent_prompt(context)
            
            # Call appropriate LLM
            if self.llm_provider == "openai":
                response = await self._call_openai_agent(prompt, conversation_history, screenshot_base64)
            elif self.llm_provider == "anthropic":
                response = await self._call_anthropic_agent(prompt, conversation_history, screenshot_base64)
            else:
                logger.warning("LLM not configured, using fallback logic")
                response = self._fallback_next_action(context)
            
            return response
            
        except Exception as e:
            error_msg = str(e)
            # Don't log full error for rate limits (agent orchestrator handles it)
            if "rate_limit" in error_msg.lower():
                logger.debug(f"Rate limit error (will be handled by retry logic): {error_msg[:200]}")
            else:
                logger.error(f"Error calling LLM for next action: {e}")
            # Re-raise for agent orchestrator to handle
            raise
    
    def _build_agent_prompt(self, context: Dict[str, Any]) -> str:
        """Build prompt for agent reasoning."""
        
        credentials = context.get("credentials", {})
        current_step = context.get("current_step", 1)
        fields_filled = context.get("fields_filled", [])
        action_history = context.get("action_history", [])
        has_success = context.get("has_success_indicator", False)
        
        # Format inputs
        visible_inputs = context.get("visible_inputs", [])
        inputs_text = self._format_inputs_for_llm(visible_inputs)
        buttons_text = self._format_buttons_for_llm(context.get("visible_buttons", []))
        
        # Count checkboxes for alert
        checkbox_count = sum(1 for inp in visible_inputs if inp.get('type') in ['checkbox', 'radio', 'div-checkbox'])
        checkbox_alert = f"\n🚨 ALERT: {checkbox_count} CHECKBOX/SELECTION FIELDS DETECTED - YOU MUST INTERACT WITH THEM!\n" if checkbox_count > 0 else ""
        
        # Extract phone info
        phone = credentials.get('phone', {})
        if isinstance(phone, dict):
            phone_display = f"{phone.get('full', '+1234567890')} (Country: {phone.get('country_code', '+1')}, Number: {phone.get('number', '234567890')})"
        else:
            phone_display = str(phone)
        
        # Error messages
        error_messages = context.get("error_messages", [])
        has_errors = context.get("has_error_messages", False)
        error_text = "\n".join([f"- {err.get('text', '')}" for err in error_messages[:3]]) if has_errors else "None"
        
        # Build failed selector warnings
        failed_warnings = context.get('failed_selector_hints', [])
        failed_warning_section = ""
        if failed_warnings:
            failed_warning_section = f"""
🚨🚨🚨 CRITICAL - PREVIOUS FAILURES DETECTED 🚨🚨🚨
The following selectors/actions have FAILED multiple times. DO NOT use them again!

{chr(10).join(failed_warnings)}

YOU MUST try a DIFFERENT approach for these failed selectors!
If you see the same selector above, use a COMPLETELY DIFFERENT selector or method.
============================================================

"""
        
        # Check if screenshot is available
        has_screenshot = context.get('screenshot') is not None
        vision_status = "WITH VISION 📸" if has_screenshot else "TEXT ONLY (no screenshot to save tokens)"
        
        prompt = f"""{failed_warning_section}You are an AI agent helping to sign up for an email list. {vision_status}

🔍 OBSERVATION PROCESS:
{f'''1. Look at the screenshot - what do you SEE on the page?
2. Identify form fields, buttons, error messages visually
3. Understand the page layout and structure
4. Make decisions based on VISUAL appearance + HTML data''' if has_screenshot else '''1. You do NOT have a screenshot (token optimization)
2. Rely on HTML structure, inputs list, buttons list, and page text
3. Use selector information from inputs/buttons lists
4. Be extra careful with selectors - verify they exist in inputs list'''}

GOAL: Sign up using these credentials:
- First Name: {credentials.get('first_name', 'Test')}
- Last Name: {credentials.get('last_name', 'User')}
- Full Name: {credentials.get('full_name', credentials.get('first_name', 'Test User'))}
- Email: {credentials.get('email', 'test@example.com')}
- Phone: {phone_display}

CURRENT SITUATION:
- Step: {current_step}
- Page URL: {context.get('page_url', 'Unknown')}
- Fields already filled: {', '.join(fields_filled) if fields_filled else 'None'}
- Checkboxes ALREADY checked: {len(context.get('checkboxes_checked', []))} ({'⚠️ DO NOT CHECK MORE - move to other fields!' if context.get('checkboxes_checked') else 'None yet'})
- Success indicator detected: {has_success}
- Validation errors detected: {has_errors}

⚠️ ERROR MESSAGES ON PAGE:
{error_text}
{checkbox_alert}
VISIBLE FORM ELEMENTS:
Inputs:
{inputs_text}

Buttons:
{buttons_text}

PAGE TEXT SAMPLE:
{context.get('page_text_sample', '')}

📜 LAST ACTION RESULT:
{("✅ SUCCESS: " + json.dumps(action_history[-1], indent=2)) if action_history and action_history[-1].get("success") else ("❌ FAILED: " + json.dumps(action_history[-1], indent=2) if action_history else "No previous action")}

RECENT ACTIONS (Last 3):
{json.dumps(action_history[-3:], indent=2) if action_history else 'None yet'}

🚨 REPEATED FAILURES - CHANGE YOUR APPROACH:
{chr(10).join(context.get('failed_selector_hints', [])) if context.get('failed_selector_hints') else 'No repeated failures yet (first attempt for all selectors)'}

📸 SCREENSHOT PROVIDED: Look at the screenshot to understand the VISUAL state of the page.

⚠️ IF LAST ACTION FAILED - READ THIS FIRST:
- Check "LAST ACTION RESULT" above - did it fail?
- If YES: Read the error message carefully
- DO NOT retry the same selector/action
- Check "REPEATED FAILURES" section for suggested solutions
- Try a DIFFERENT approach (different selector, different method, or alternative strategy)

YOUR TASK:
1. OBSERVE: Look at the screenshot + HTML carefully
   - Do you see form fields (email, name, phone)?
   - **SCAN for checkboxes/selections** (look in inputs list for type="checkbox" or "div-checkbox")!
   - Do you see navigation buttons ("Sign Up", "Learn More", "Get Started")?
   - Do you see errors, success messages, validation warnings?
   - **CRITICAL**: Check if last action succeeded or failed!
2. THINK: What is the current state?
   - If NO form visible: Look for buttons to click (Sign Up, Register, Join, etc.)
   - If form visible: **Fill ALL fields one by one** (email → name → phone → ONE checkbox → submit)
   - For checkbox groups: **Check ONLY ONE checkbox, then move to next field**
   - If error visible: Fix the error (may need to check more checkboxes or fix field)
   - If success visible: Mark complete
   - **If last action FAILED**: Understand why and change approach
   - **If form submission failed with checkbox error**: Go back and check MORE checkboxes
3. **LEARN FROM FAILURES**: 
   - Check "REPEATED FAILURES" section above
   - If a selector failed even once → try something different immediately
   - Read the suggested solutions and use them
   - For hidden checkboxes: Already fixed - fill_field should now work!
4. DECIDE: Choose the NEXT SINGLE ACTION
   - **For checkboxes**: Check ONE, then immediately move to NEXT FIELD (don't check more!)
   - If last action failed with same selector → use DIFFERENT selector
   - If checkbox fails with "hidden" → it's now fixed, retry once
   - After successfully checking one checkbox → proceed to next form field
5. REFLECT: Never repeat the same failing action twice

🔍 EXPLORATION MODE:
- If you don't see a signup form yet, EXPLORE the page
- Look for buttons like: "Sign Up", "Get Started", "Join Now", "Learn More", "Try Free"
- Click them to navigate to the actual signup page
- Don't give up until you've tried all promising navigation options

📸 VISUAL ANALYSIS PRIORITY:
- Look at the screenshot FIRST before making decisions
- Error messages: Can you SEE red text, error icons, or validation messages?
- Success indicators: Do you SEE "Thank you", checkmarks, or confirmation messages?
- Hidden elements: If you can't SEE it in screenshot, don't interact with it
- Page state: Does the page look like it changed after last action?
- CAPTCHA: Do you SEE a CAPTCHA challenge (checkbox, images, reCAPTCHA logo)?

⚠️ CRITICAL: EXPLORATION & NAVIGATION:
- **NO FORM YET?** Look for navigation buttons first:
  * "Sign Up" / "Sign-up" / "Signup"
  * "Get Started" / "Start Now" / "Start Free"
  * "Join Now" / "Join Free" / "Register"
  * "Learn More" / "See More" / "Find Out"
  * "Try Free" / "Free Trial" / "Demo"
  * "Download" / "Get Access" / "Claim"
- **Click navigation buttons** to find the signup form (don't give up!)
- **Be persistent:** Many landing pages hide forms behind buttons

⚠️ MULTI-STEP FORMS & CHECKBOX/RADIO:
- Forms can be MULTI-STEP (checkboxes → Next → form fields → Submit)
- **CHECKBOX/RADIO + NEXT BUTTON FLOW**: If you see checkbox/radio inputs with a "Next"/"Continue" button:
  1. FIRST: Select a checkbox/radio (set value="true") 
  2. THEN: Click the Next/Continue button
  3. NEVER click Next without selecting an option first!
- If validation errors appear, you likely need to select a checkbox/radio before clicking Next

⚠️ NAME FIELD HANDLING - CRITICAL:
- "First Name" or "First" or "firstname" → field_type: "first_name"
- "Last Name" or "Last" or "lastname" → field_type: "last_name"
- "Full Name" or "Name" or "fullname" → field_type: "full_name"
- **IMPORTANT**: Look at the field label/placeholder carefully:
  * If it says "Full Name" or "Your Name" → use field_type: "full_name"
  * If it says "First Name" → use field_type: "first_name"
  * Don't use first_name when the field clearly asks for full name!

⚠️ CHECKBOX/RADIO/SELECTION RULES - CRITICAL:
- **SCAN THE ENTIRE FORM** - Don't skip fields! Look for ALL required selections before submitting
- **COMMON PATTERNS**: Forms often ask "Which platforms?", "Select your interests", "Choose options"
- **ALWAYS fill checkboxes/radios BEFORE clicking Next/Continue/Submit buttons**

**THREE TYPES OF CHECKBOXES:**
1. **HIDDEN CHECKBOXES WRAPPED IN LABELS** (sr-only/visually-hidden pattern) - MOST COMMON:
   - Pattern: `<label><input class="sr-only" type="checkbox"></label>`
   - The actual <input> is hidden, but the wrapping <label> is clickable
   - Marked with 🎯 [HIDDEN+WRAPPED] in inputs list
   - Use: action="fill_field", field_type="checkbox", value="true"
   - Example: {{"action": "fill_field", "selector": "#facebook-checkbox", "field_type": "checkbox", "value": "true"}}
   - System will automatically click the parent label for you!
   
2. **DIV/SPAN-BASED CHECKBOXES** (clickable divs that ACT as checkboxes):
   - These are divs/spans with onClick handlers, NOT actual <input> elements
   - Look for: class="option", role="checkbox", clickable divs with text like "Facebook", "Instagram"
   - Marked with ⚠️ DIV-CHECKBOX in inputs list
   - Use: action="click", selector pointing to the div/span/label
   - Example: {{"action": "click", "selector": "div:has-text('Facebook')"}}
   - HTML pattern: <div class="option-card" role="button"><span>Facebook</span></div>
   
3. **VISIBLE CHECKBOXES** (normal <input type="checkbox">):
   - Standard checkboxes that are visible on the page
   - Use fill_field with field_type="checkbox"

**DETECTION STRATEGY:**
- Check HTML for: <input type="checkbox">, role="checkbox", clickable divs near checkbox labels
- If you see text like "Select platforms:", "Choose options:", there ARE checkboxes!
- Look in the HTML inputs list for elements with type="checkbox"
- Look for divs with class names like "option", "choice", "card", "selector"

**ERROR RECOVERY:**
- If fill_field fails → Try click on the label or parent div
- If form submission fails with validation errors → You likely MISSED checkboxes!
- Always select at least ONE option from checkbox groups

**MULTI-CHECKBOX GROUPS - CONSERVATIVE STRATEGY:**
- **🚨🚨 CRITICAL CHECK: Look at "Checkboxes ALREADY checked" in CURRENT SITUATION above**
- **IF any checkboxes are already checked → SKIP to OTHER FIELD TYPES (business name, etc)**
- **DO NOT reason "need to select one more platform/option" - ONE IS ALWAYS ENOUGH**
- Multiple checkboxes with same `name` attribute = multi-select group
- **🚨 CRITICAL: Select ONLY ONE checkbox and IMMEDIATELY move to OTHER fields**
- **DO NOT select multiple checkboxes from the same group in sequential steps**
- Example: For "What social platforms?", select Facebook ONLY → then fill OTHER fields (business name, etc)
- **NEVER check Instagram/Twitter/LinkedIn after already checking Facebook**
- Only select MULTIPLE checkboxes if:
  1. Label explicitly says "select all that apply" or "select multiple" or "choose all"
  2. OR form submission fails with EXPLICIT validation error requiring more selections
- After checking ONE checkbox in a group → SKIP to the NEXT DIFFERENT FIELD TYPE

**CRITICAL - CHECKBOX FAILURE RECOVERY:**
- If a checkbox fails 2+ times with the SAME selector → TRY A DIFFERENT CHECKBOX in the same group!
- Example: If Facebook checkbox fails → Try Instagram or Twitter instead
- Don't retry the same failing checkbox endlessly - move on to alternatives
- As long as you check AT LEAST ONE checkbox in a multi-select group, most forms will accept it

**SELECTION STRATEGY:**
- Age ranges: Select adult age (18-21, 22+)
- Agreement: Select "I agree"
- **Platforms/Categories: Select ONLY ONE most common option (e.g., "Facebook")**
- **Multi-checkbox groups: Check ONE checkbox, then move to next field**
- Only select multiple if label says "select all" or form validation requires it
- If unsure, select the FIRST reasonable option and move on

⚠️ UNKNOWN/CUSTOM FIELDS:
- **Business Name / Company Name**: Use field_type: "business_name" (system will auto-generate)
- **Checkboxes**: Use field_type: "checkbox" with value="true"
- **Other custom fields**: Use a descriptive field_type and the system will generate a value
- Examples: field_type: "business_name", "company", "organization", "title", "message"

ACTION TYPES:
1. "fill_field" - Fill a form field (text/email/phone/checkbox/radio/select)
2. "click" - Click a button/link
3. "wait" - Wait for page to load
4. "complete" - Sign up is complete (success message visible) OR no signup form exists

        IMPORTANT RULES:
        - Take ONE action at a time
        - **CHECK "FAILED SELECTOR ANALYSIS" ABOVE** - Don't retry selectors that already failed 2+ times!
        - If previous action failed, try a DIFFERENT approach (different selector or different action type)
        - Only fill VISIBLE fields (check visibility in data above)
        - For multi-step forms, complete current step, then click "Next"/"Continue"
        - **CRITICAL**: ONLY use action: "complete" when you SEE visual confirmation of success:
          * "Thank you for signing up!"
          * "Check your email"
          * "Success!"
          * Green checkmark or success icon
          * Confirmation page or "You're all set" message
        - **DO NOT** mark complete just because you filled fields - you MUST see success confirmation!
        - Always provide valid CSS selectors ONLY (prefer #id > [name="x"] > .classname)
        - NEVER use :contains() or other invalid pseudo-classes - use CSS selectors only
        - Don't fill fields already filled: {fields_filled}
        - **CRITICAL - BEFORE SUBMITTING**: Look at the screenshot carefully - do you see ANY:
          * Empty required fields (with red borders or asterisks)?
          * Unchecked checkboxes with error messages?
          * Validation errors in red text?
          * "Response required" or "Please select" messages?
        - **IF ANY ERRORS VISIBLE**: DO NOT click submit! Fill the missing fields first!
        - **VALIDATE BEFORE SUBMIT**: Make sure ALL visible required fields are filled and NO errors are shown
        - CRITICAL: If an action failed (see errors above), DON'T retry the same selector! Try a different approach
        - CRITICAL: If validation errors appear (see above), check error messages and fix the problematic field
        - NAME FIELDS: Match field label to credential (Full Name → full_name, First Name → first_name, Last Name → last_name)
        - CHECKBOXES/RADIOS CRITICAL: If present, fill them FIRST before clicking Next/Continue! Set value="true" to check
        - If you see checkboxes/radios + Next button → select checkbox THEN click Next (not the other way around!)
        - SUBMIT BUTTONS can be: button, input[type=submit], div, span, or a tags
        - Look for clickable elements with text like: "Submit", "Sign up", "Next", "Continue", "Start", "Register", "Join", etc.
        - Use class names, IDs, and attributes to identify elements (e.g., div.place-btn, button[class*="next"])
        - If no form visible yet, try clicking exploration buttons: "Get Started", "Sign Up", "Start Now", etc.
        - Give the process 5-7 steps before deciding there's no form - forms can appear after interactions
        - NEVER click: slideshow buttons, carousel arrows, video play/pause, main navigation menus
        - If no form after 10+ steps AND no more navigation buttons to try → action: "complete"
        - EXHAUST ALL OPTIONS: Try all promising buttons before giving up
        
        PHONE NUMBER HANDLING - CRITICAL:
        - **LOOK CAREFULLY**: Is there a country code dropdown/select next to the phone input?
        - **SCENARIO 1**: COUNTRY CODE DROPDOWN + PHONE INPUT (separate):
          * FIRST: Try to fill the country code dropdown (action: "fill_field", field_type: "country_code")
          * Common dropdown selectors: select[name*="country"], select[name*="code"], #country_code
          * For custom dropdowns (not <select>), try: div[role="button"], button with country flag
          * THEN: Fill phone input with JUST the number - NO country code prefix
          * In JSON, set: "use_phone_number_only": true
        - **SCENARIO 2**: SINGLE phone input field (no separate dropdown):
          * Fill with the FULL phone number including country code
          * In JSON, set: "use_phone_number_only": false (or omit)
        - **FALLBACK STRATEGY** - If country code selection fails 2+ times:
          * Stop trying to change the country code
          * Instead, generate a phone number that matches the DEFAULT country code you see
          * Example: If dropdown shows "+92", use field_type: "phone_fallback" to generate a +92 number
          * Use "use_phone_number_only": true
        - **ERROR HANDLING**: If you see "Invalid phone number" error:
          * Check if country code matches the phone number
          * If you can't change country code after 2 tries, use phone_fallback strategy
        
        ERROR HANDLING (VISUAL):
        - ⚠️ LOOK at the screenshot - do you SEE any red text, error icons, or validation messages?
        - If you SEE errors in the screenshot, READ them carefully
        - Common visual error indicators: red borders, red text, exclamation icons, "✗" symbols
        - **CRITICAL**: If you see errors about "Response required" or "Please select" → find and fill that checkbox/field FIRST
        - **BEFORE CLICKING SUBMIT**: Scroll through the form visually - are there any empty required fields below?
        - STOP clicking submit if you SEE the same error appear again
        - Try to FIX the error by understanding what the visual error message says
        - If you can't fix after 2 attempts, explain what you SEE and mark complete
        
        ACTION FAILURE RECOVERY - WHAT TO DO WHEN ACTIONS FAIL:
        1. **"Could not find clickable element"** for a CHECKBOX:
           → CHANGE approach: Use action="fill_field" with field_type="checkbox" instead of action="click"
           → OR try clicking the label: label[for="checkbox-id"]
           → OR try clicking visible text like div:has-text("Facebook")
        
        2. **"Timeout" or "Element not found"**:
           → The selector is wrong or element doesn't exist
           → Look at the HTML/screenshot and find a DIFFERENT selector
           → Try: parent element, sibling element, or text-based search
        
        3. **"Element not visible"** or "hidden element"**:
           → For checkboxes: Use fill_field with field_type="checkbox"
           → For other elements: Try clicking parent container or label
        
        4. **Same selector failing 2+ times**:
           → STOP using that selector immediately!
           → Check "FAILED SELECTOR ANALYSIS" section for suggested alternatives
           → Use a completely different approach (different selector, different action type)
        
        5. **Validation errors after filling field**:
           → Read the error message visually
           → Adjust your approach (e.g., change country code, use fallback phone number)
           → Don't retry the exact same action
        
        PRE-SUBMIT VALIDATION CHECKLIST:
        1. 📸 Look at the ENTIRE form in the screenshot
        2. ✅ Are ALL input fields filled? (name, email, phone, business name, etc.)
        3. ✅ Are ALL required checkboxes selected?
        4. ✅ Are there NO red error messages visible?
        5. ✅ Is the phone number validation passing?
        6. ONLY if ALL checks pass → click submit
        7. If ANY check fails → fix that field FIRST before submitting
        
        CAPTCHA HANDLING:
        - If you SEE a CAPTCHA (checkbox, puzzle, reCAPTCHA logo): action: "wait" and reasoning: "CAPTCHA detected"
        - The system will automatically attempt to solve it with 2Captcha
        - After CAPTCHA appears, wait for it to be solved before proceeding
        - If there's a "Skip" button visible, you can try clicking it
        
        SELF-REFLECTION:
        - After each action, compare new screenshot with previous state
        - Did anything change visually? New error? Success message? Page transition?
        - If nothing changed after clicking, the button might not have worked - try different element
        - Learn from failures: "I clicked X, nothing happened, so I should try Y instead"

Return ONLY valid JSON with this structure:
{{
    "action": "fill_field" | "click" | "wait" | "complete",
    "selector": "#element-id or button[type='submit']",
    "field_type": "email" | "first_name" | "last_name" | "full_name" | "phone" | "phone_fallback" | "country_code" | "business_name" | "checkbox" | "custom_field_type" (only for fill_field),
    "use_phone_number_only": true | false (only for phone fields with separate country code dropdown),
    "value": "auto-filled from credentials or 'true'/'false' for checkboxes",
    "visual_observation": "What do I SEE in the screenshot? Any errors or changes?",
    "reasoning": "Based on what I SEE, why am I taking this action?",
    "expected_outcome": "What should happen after this action?"
}}

Examples (VALID CSS selectors only):

EXPLORATION:
{{"action": "click", "selector": "a.cta-button", "visual_observation": "I see a landing page with a prominent 'Get Started Free' button but no form fields yet", "reasoning": "Need to click this button to navigate to the actual signup form", "expected_outcome": "Will navigate to a page with signup form"}}
{{"action": "click", "selector": "#start-trial-btn", "visual_observation": "I see 'Start Free Trial' button with ID 'start-trial-btn'", "reasoning": "This button likely leads to signup form", "expected_outcome": "Navigate to registration page"}}

FORM FILLING:
{{"action": "fill_field", "selector": "#fullName", "field_type": "full_name", "visual_observation": "I see an empty 'Full name' input field with ID 'fullName'", "reasoning": "The field label says 'Full name' so using full_name type", "expected_outcome": "Full name will be populated with first + last name"}}
{{"action": "fill_field", "selector": "#businessName", "field_type": "business_name", "visual_observation": "I see an empty 'Business Name' field with a red error", "reasoning": "Form requires business name, system will auto-generate one", "expected_outcome": "Business name will be filled with generated value"}}
{{"action": "fill_field", "selector": "#email", "field_type": "email", "visual_observation": "I see an empty email input field in the screenshot", "reasoning": "The form needs an email address", "expected_outcome": "Email field will be populated"}}
{{"action": "fill_field", "selector": "#countryCode", "field_type": "country_code", "visual_observation": "I see a country code dropdown next to the phone field", "reasoning": "Need to select country code before filling phone number", "expected_outcome": "Country code will be selected"}}
{{"action": "fill_field", "selector": "[name='phoneNumber']", "field_type": "phone", "use_phone_number_only": true, "visual_observation": "I see the phone number input field with a country code dropdown already filled", "reasoning": "Country code is separate, so filling only the number part", "expected_outcome": "Phone number will be filled without country code prefix"}}
{{"action": "fill_field", "selector": "[name='phoneNumber']", "field_type": "phone_fallback", "use_phone_number_only": true, "visual_observation": "Country code dropdown won't change from +92, and I've tried 2 times", "reasoning": "Can't change country code, generating number for default +92", "expected_outcome": "Random phone number matching +92 country code will be filled"}}
{{"action": "fill_field", "selector": "#facebook-checkbox", "field_type": "checkbox", "value": "true", "visual_observation": "I see checkboxes for social platforms with error message", "reasoning": "Need to select at least one platform, choosing Facebook", "expected_outcome": "Facebook checkbox will be checked, error will disappear"}}
{{"action": "fill_field", "selector": "#bYslsUhCCfjCzuYqZ1WSr", "field_type": "checkbox", "value": "true", "visual_observation": "Previous click action failed with 'Could not find clickable', checkbox is likely hidden", "reasoning": "Switching from click to fill_field for hidden checkbox", "expected_outcome": "Hidden checkbox will be checked via fill_field"}}
{{"action": "click", "selector": "#continue-btn", "visual_observation": "I see the 'Continue' button is blue and appears clickable. All fields are filled.", "reasoning": "Form is complete and ready to proceed", "expected_outcome": "Page will show next step of form or success message"}}

SUCCESS:
{{"action": "complete", "visual_observation": "I see a green checkmark and 'Thank you for signing up!' message in the screenshot", "reasoning": "Visual confirmation of successful signup", "expected_outcome": "Task is complete"}}

SELECTOR BEST PRACTICES:
✅ GOOD: Use IDs, classes, or attributes from the HTML data provided
   - "#signup-button" (ID - most reliable)
   - "button.cta-primary" (class)
   - "a[href*='signup']" (attribute)
   
❌ AVOID: Invalid pseudo-selectors
   - "button:contains('text')" - use text search as fallback only
   - If you must use text, format as: "button" and describe "contains 'Start free trial'"
   
💡 TIP: Look at the HTML/button data provided - use actual IDs and classes you see!
"""
        
        return prompt
    
    async def _call_openai_agent(self, prompt: str, conversation_history: List[Dict[str, str]], 
                                 screenshot_base64: Optional[str] = None) -> Dict[str, Any]:
        """Call OpenAI for agent action decision with optional screenshot."""
        import aiohttp
        
        api_key = self.llm_config.get('api_key', '')
        if not api_key or 'YOUR_' in api_key:
            raise ValueError("OpenAI API key not configured")
        
        model = self.llm_config.get('model', 'gpt-4o')
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        # Build messages with conversation history
        messages = [
            {
                "role": "system",
                "content": "You are an expert web automation agent with vision capabilities. Analyze screenshots and page structure to make intelligent decisions. Think step-by-step and return only valid JSON."
            }
        ]
        
        # Add conversation history (last 3 turns to save tokens with vision)
        for msg in conversation_history[-3:]:
            messages.append(msg)
        
        # Add current prompt with optional screenshot
        if screenshot_base64:
            # Vision API format with image
            messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{screenshot_base64}",
                            "detail": "high"  # High detail for form analysis
                        }
                    }
                ]
            })
        else:
            # Text only
            messages.append({
                "role": "user",
                "content": prompt
            })
        
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": 1000,
            "temperature": 0.1,  # Very low for consistent decisions
            "response_format": {"type": "json_object"}
        }
        
        # Make API call - fail fast on rate limits (agent orchestrator handles retries)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=45)  # Longer timeout for vision
                ) as response:
                    if response.status == 429:  # Rate limit - fail fast
                        error_text = await response.text()
                        raise Exception(f"rate_limit_exceeded: {error_text}")
                    
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"OpenAI API error ({response.status}): {error_text}")
                    
                    result = await response.json()
                    content = result['choices'][0]['message']['content']
                    
                    return json.loads(content)
        except asyncio.TimeoutError:
            raise Exception("OpenAI API request timed out")
    
    async def _call_anthropic_agent(self, prompt: str, conversation_history: List[Dict[str, str]],
                                    screenshot_base64: Optional[str] = None) -> Dict[str, Any]:
        """Call Anthropic Claude for agent action decision."""
        import aiohttp
        
        api_key = self.llm_config.get('api_key', '')
        if not api_key:
            raise ValueError("Anthropic API key not configured")
        
        model = self.llm_config.get('model', 'claude-3-5-sonnet-20241022')
        
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01"
        }
        
        # Build messages with optional screenshot
        messages = []
        for msg in conversation_history[-3:]:  # Less history with vision to save tokens
            messages.append(msg)
        
        if screenshot_base64:
            # Vision format for Claude
            messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": screenshot_base64
                        }
                    },
                    {
                        "type": "text",
                        "text": prompt + "\n\nCRITICAL: Return ONLY valid JSON, no markdown, no explanations."
                    }
                ]
            })
        else:
            messages.append({
                "role": "user",
                "content": prompt + "\n\nCRITICAL: Return ONLY valid JSON, no markdown, no explanations."
            })
        
        payload = {
            "model": model,
            "max_tokens": 1000,
            "temperature": 0.1,
            "messages": messages
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Anthropic API error ({response.status}): {error_text}")
                
                result = await response.json()
                content = result['content'][0]['text']
                
                # Extract JSON
                if '```json' in content:
                    content = content.split('```json')[1].split('```')[0].strip()
                elif '```' in content:
                    content = content.split('```')[1].split('```')[0].strip()
                
                return json.loads(content)
    
    def _fallback_next_action(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback logic when LLM is not available."""
        fields_filled = context.get("fields_filled", [])
        inputs = context.get("visible_inputs", [])
        buttons = context.get("visible_buttons", [])
        
        # Check if we have success indicator
        if context.get("has_success_indicator", False):
            return {
                "action": "complete",
                "reasoning": "Success indicator detected on page"
            }
        
        # Try to fill email if not filled
        if not any("email" in f for f in fields_filled):
            for inp in inputs:
                if inp.get("type") == "email" or "email" in inp.get("name", "").lower():
                    return {
                        "action": "fill_field",
                        "selector": self._build_selector(inp),
                        "field_type": "email",
                        "reasoning": "Filling email field"
                    }
        
        # Try to fill name if not filled
        if not any("name" in f for f in fields_filled):
            for inp in inputs:
                name_attr = inp.get("name", "").lower()
                if "name" in name_attr and "email" not in name_attr:
                    return {
                        "action": "fill_field",
                        "selector": self._build_selector(inp),
                        "field_type": "name",
                        "reasoning": "Filling name field"
                    }
        
        # Try to click submit button/div
        for btn in buttons:
            text = btn.get("text", "").lower()
            btn_type = btn.get("type", "").lower()
            btn_class = btn.get("className", "").lower()
            
            # Check if it looks like a submit element
            is_submit = any(word in text for word in ["submit", "sign up", "apuntar", "continue", "next", "join", "register"])
            is_submit = is_submit or any(word in btn_class for word in ["btn", "button", "submit", "place-btn"])
            
            if is_submit:
                # Build selector based on type
                if btn.get("id"):
                    selector = f'#{btn["id"]}'
                elif "btn" in btn_class or "button" in btn_class:
                    selector = f'{btn_type}.{btn_class.split()[0]}' if btn_class else f'{btn_type}:has-text("{btn.get("text")[:20]}")'
                else:
                    selector = f'{btn_type}:has-text("{btn.get("text")[:20]}")'
                
                return {
                    "action": "click",
                    "selector": selector,
                    "reasoning": f"Clicking {btn_type} submit element"
                }
        
        # Default: complete
        return {
            "action": "complete",
            "reasoning": "No more actions identified"
        }

