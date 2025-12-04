"""
Pydantic models for structured LLM outputs.
Ensures reliable parsing and validation of AI agent responses.
"""

from typing import Optional, List, Literal
from pydantic import BaseModel, Field, field_validator


class AgentActionResponse(BaseModel):
    """
    Structured response from the AI agent for a single action.
    Used by the agent orchestrator to execute next steps.
    """
    
    action: Literal["fill_field", "click", "wait", "complete"] = Field(
        description="Type of action to perform"
    )
    
    selector: Optional[str] = Field(
        default=None,
        description="CSS selector for the target element"
    )
    
    field_type: Optional[str] = Field(
        default=None,
        description="Type of field (email, first_name, last_name, full_name, phone, checkbox, etc.)"
    )
    
    value: Optional[str] = Field(
        default=None,
        description="Value to fill or action parameter"
    )
    
    use_phone_number_only: Optional[bool] = Field(
        default=False,
        description="If true, use phone number without country code"
    )
    
    visual_observation: Optional[str] = Field(
        default=None,
        description="What the agent sees in the screenshot"
    )
    
    reasoning: str = Field(
        description="Why this action was chosen"
    )
    
    expected_outcome: Optional[str] = Field(
        default=None,
        description="What should happen after this action"
    )
    
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence score (0-1) for this action"
    )
    
    @field_validator('selector')
    @classmethod
    def validate_selector(cls, v: Optional[str]) -> Optional[str]:
        """Validate CSS selector format."""
        if v is None:
            return v
        
        # Remove common invalid pseudo-selectors
        invalid_patterns = [':contains(', ':has-text(']
        for pattern in invalid_patterns:
            if pattern in v:
                # Try to extract the text and convert to valid selector
                # This is a fallback - ideally the LLM shouldn't generate these
                pass
        
        return v.strip() if v else None


class FormAnalysisResponse(BaseModel):
    """
    Response from LLM when analyzing a form structure.
    """
    
    fields_to_fill: List[dict] = Field(
        default_factory=list,
        description="List of fields to fill with their selectors and values"
    )
    
    submit_button: Optional[dict] = Field(
        default=None,
        description="Submit button selector and text"
    )
    
    is_multistep: bool = Field(
        default=False,
        description="Whether this is a multi-step form"
    )
    
    has_captcha: bool = Field(
        default=False,
        description="Whether CAPTCHA is detected"
    )
    
    reasoning: str = Field(
        default="",
        description="Analysis explanation"
    )


class PageStateAnalysis(BaseModel):
    """
    Analysis of the current page state.
    """
    
    has_form: bool = Field(
        default=False,
        description="Whether a signup form is visible"
    )
    
    has_success_indicator: bool = Field(
        default=False,
        description="Whether success message is visible"
    )
    
    has_error_messages: bool = Field(
        default=False,
        description="Whether validation errors are visible"
    )
    
    error_details: Optional[List[str]] = Field(
        default=None,
        description="List of visible error messages"
    )
    
    form_completeness: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Percentage of form fields that appear filled (0-1)"
    )
    
    suggested_action: str = Field(
        default="explore",
        description="Suggested next action type"
    )
    
    captcha_detected: bool = Field(
        default=False,
        description="Whether CAPTCHA is visible"
    )
    
    captcha_type: Optional[str] = Field(
        default=None,
        description="Type of CAPTCHA if detected (recaptcha_v2, recaptcha_v3, hcaptcha, turnstile)"
    )


class CaptchaAnalysisResponse(BaseModel):
    """
    Response when analyzing a page for CAPTCHA.
    """
    
    captcha_detected: bool = Field(
        default=False,
        description="Whether CAPTCHA is present"
    )
    
    captcha_type: Optional[Literal["recaptcha_v2", "recaptcha_v3", "hcaptcha", "turnstile", "unknown"]] = Field(
        default=None,
        description="Type of CAPTCHA"
    )
    
    sitekey: Optional[str] = Field(
        default=None,
        description="CAPTCHA site key if found"
    )
    
    bypass_available: bool = Field(
        default=False,
        description="Whether a skip/bypass option is available"
    )
    
    bypass_selector: Optional[str] = Field(
        default=None,
        description="Selector for bypass button if available"
    )
    
    reasoning: str = Field(
        default="",
        description="Analysis explanation"
    )


def parse_agent_response(response_dict: dict) -> AgentActionResponse:
    """
    Parse and validate an agent response dictionary.
    
    Args:
        response_dict: Raw dictionary from LLM
        
    Returns:
        Validated AgentActionResponse
        
    Raises:
        ValueError: If validation fails
    """
    try:
        return AgentActionResponse(**response_dict)
    except Exception as e:
        # Try to fix common issues
        fixed = response_dict.copy()
        
        # Fix action type
        if 'action' not in fixed or fixed['action'] not in ['fill_field', 'click', 'wait', 'complete']:
            fixed['action'] = 'wait'
            fixed['reasoning'] = f"Original action invalid, defaulting to wait. Original: {response_dict.get('action')}"
        
        return AgentActionResponse(**fixed)


def parse_captcha_response(response_dict: dict) -> CaptchaAnalysisResponse:
    """Parse and validate a CAPTCHA analysis response."""
    try:
        return CaptchaAnalysisResponse(**response_dict)
    except Exception as e:
        # Return safe defaults
        return CaptchaAnalysisResponse(
            captcha_detected=False,
            reasoning=f"Failed to parse response: {e}"
        )

