"""
Agent configuration management.
Handles local config storage and platform config sync.
"""

import json
import os
from pathlib import Path
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from loguru import logger


def get_data_dir() -> Path:
    """Get the application data directory based on OS."""
    if os.name == 'nt':  # Windows
        base = Path(os.environ.get('APPDATA', Path.home()))
    elif os.name == 'posix':
        if os.uname().sysname == 'Darwin':  # macOS
            base = Path.home() / 'Library' / 'Application Support'
        else:  # Linux
            base = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
    else:
        base = Path.home()
    
    data_dir = base / 'InboxHunter'
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


class PlatformConfig(BaseModel):
    """Configuration received from platform."""
    api_url: str = "https://api.inboxhunter.io"
    ws_url: str = "wss://api.inboxhunter.io/ws"


class CredentialsConfig(BaseModel):
    """User credentials for form filling."""
    first_name: str = ""
    last_name: str = ""
    full_name: str = ""
    email: str = ""
    phone_country_code: str = "+1"
    phone_number: str = ""
    phone_full: str = ""


class AutomationConfig(BaseModel):
    """Browser automation settings."""
    headless: bool = False
    browser: str = "chromium"
    viewport_width: int = 1920
    viewport_height: int = 1080
    stealth_enabled: bool = True
    typing_delay_min: float = 0.1
    typing_delay_max: float = 0.3


class LLMConfig(BaseModel):
    """LLM settings (received from platform or local)."""
    enabled: bool = True
    provider: str = "openai"
    api_key: str = ""
    model: str = "gpt-4o"


class CaptchaConfig(BaseModel):
    """CAPTCHA service settings."""
    service: str = "2captcha"
    api_key: str = ""
    timeout: int = 120


class AgentConfig(BaseModel):
    """Main agent configuration."""
    # Agent identity
    agent_id: str = ""
    agent_token: str = ""
    
    # Platform connection
    platform: PlatformConfig = Field(default_factory=PlatformConfig)
    
    # Task settings
    credentials: CredentialsConfig = Field(default_factory=CredentialsConfig)
    automation: AutomationConfig = Field(default_factory=AutomationConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    captcha: CaptchaConfig = Field(default_factory=CaptchaConfig)
    
    # Local settings
    auto_start: bool = True
    minimize_to_tray: bool = True
    check_updates: bool = True
    log_level: str = "INFO"
    
    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "AgentConfig":
        """Load configuration from file."""
        if config_path is None:
            config_path = get_data_dir() / "agent_config.json"
        
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    data = json.load(f)
                return cls(**data)
            except Exception as e:
                logger.warning(f"Failed to load config: {e}, using defaults")
        
        return cls()
    
    def save(self, config_path: Optional[Path] = None):
        """Save configuration to file."""
        if config_path is None:
            config_path = get_data_dir() / "agent_config.json"
        
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(config_path, 'w') as f:
            json.dump(self.model_dump(), f, indent=2)
        
        logger.debug(f"Config saved to {config_path}")
    
    def update_from_platform(self, platform_config: Dict[str, Any]):
        """Update config with settings from platform."""
        if "credentials" in platform_config:
            creds = platform_config["credentials"]
            self.credentials = CredentialsConfig(
                first_name=creds.get("first_name", ""),
                last_name=creds.get("last_name", ""),
                full_name=creds.get("full_name", ""),
                email=creds.get("email", ""),
                phone_country_code=creds.get("phone", {}).get("country_code", "+1"),
                phone_number=creds.get("phone", {}).get("number", ""),
                phone_full=creds.get("phone", {}).get("full", "")
            )
        
        if "llm" in platform_config:
            llm = platform_config["llm"]
            self.llm = LLMConfig(
                enabled=llm.get("enabled", True),
                provider=llm.get("provider", "openai"),
                api_key=llm.get("api_key", ""),
                model=llm.get("model", "gpt-4o")
            )
        
        if "captcha" in platform_config:
            captcha = platform_config["captcha"]
            self.captcha = CaptchaConfig(
                service=captcha.get("service", "2captcha"),
                api_key=captcha.get("api_key", ""),
                timeout=captcha.get("timeout", 120)
            )
        
        if "automation" in platform_config:
            auto = platform_config["automation"]
            self.automation = AutomationConfig(
                headless=auto.get("headless", False),
                browser=auto.get("browser", "chromium"),
                viewport_width=auto.get("viewport_width", 1920),
                viewport_height=auto.get("viewport_height", 1080),
                stealth_enabled=auto.get("stealth_enabled", True)
            )
        
        self.save()
        logger.info("Config updated from platform")


# Global config instance
_agent_config: Optional[AgentConfig] = None


def get_agent_config() -> AgentConfig:
    """Get global agent configuration."""
    global _agent_config
    if _agent_config is None:
        _agent_config = AgentConfig.load()
    return _agent_config


def reload_agent_config() -> AgentConfig:
    """Reload agent configuration from file."""
    global _agent_config
    _agent_config = AgentConfig.load()
    return _agent_config

