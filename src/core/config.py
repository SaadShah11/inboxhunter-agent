"""
Agent configuration management.
Handles local config storage and platform config sync.
"""

import json
import os
import yaml
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
    api_url: str = "http://localhost:3001"
    ws_url: str = "ws://localhost:3001/ws/agent"


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
        """Load configuration from file, merging JSON and YAML configs."""
        if config_path is None:
            config_path = get_data_dir() / "agent_config.json"
        
        # Start with empty config
        config = cls()
        
        # Load from JSON (agent_config.json - has agent_id and agent_token)
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    data = json.load(f)
                config = cls(**data)
            except Exception as e:
                logger.warning(f"Failed to load JSON config: {e}")
        
        # Also load from YAML config (config/config.yaml - has API keys, credentials)
        yaml_paths = [
            Path("config/config.yaml"),
            Path(__file__).parent.parent.parent / "config" / "config.yaml",
        ]
        
        for yaml_path in yaml_paths:
            if yaml_path.exists():
                try:
                    with open(yaml_path, 'r') as f:
                        yaml_data = yaml.safe_load(f) or {}
                    
                    # Merge YAML settings into config (YAML takes priority for API keys)
                    if "llm" in yaml_data:
                        llm = yaml_data["llm"]
                        # Only override if YAML has a non-empty API key
                        if llm.get("api_key") and llm.get("api_key") != "YOUR_OPENAI_API_KEY":
                            config.llm = LLMConfig(
                                enabled=llm.get("enabled", config.llm.enabled),
                                provider=llm.get("provider", config.llm.provider),
                                api_key=llm.get("api_key", config.llm.api_key),
                                model=llm.get("model", config.llm.model)
                            )
                    
                    if "captcha" in yaml_data:
                        captcha = yaml_data["captcha"]
                        if captcha.get("api_key"):
                            config.captcha = CaptchaConfig(
                                service=captcha.get("service", config.captcha.service),
                                api_key=captcha.get("api_key", config.captcha.api_key),
                                timeout=captcha.get("timeout", config.captcha.timeout)
                            )
                    
                    if "credentials" in yaml_data:
                        creds = yaml_data["credentials"]
                        phone = creds.get("phone", {})
                        config.credentials = CredentialsConfig(
                            first_name=creds.get("first_name", config.credentials.first_name),
                            last_name=creds.get("last_name", config.credentials.last_name),
                            full_name=creds.get("full_name", config.credentials.full_name),
                            email=creds.get("email", config.credentials.email),
                            phone_country_code=phone.get("country_code", config.credentials.phone_country_code),
                            phone_number=phone.get("number", config.credentials.phone_number),
                            phone_full=phone.get("full", config.credentials.phone_full)
                        )
                    
                    if "automation" in yaml_data:
                        auto = yaml_data["automation"]
                        config.automation = AutomationConfig(
                            headless=auto.get("headless", config.automation.headless),
                            browser=auto.get("browser", config.automation.browser),
                            viewport_width=auto.get("viewport_width", config.automation.viewport_width),
                            viewport_height=auto.get("viewport_height", config.automation.viewport_height),
                            stealth_enabled=auto.get("stealth_enabled", config.automation.stealth_enabled),
                            typing_delay_min=auto.get("typing_delay_min", config.automation.typing_delay_min),
                            typing_delay_max=auto.get("typing_delay_max", config.automation.typing_delay_max)
                        )
                    
                    if "platform" in yaml_data:
                        platform = yaml_data["platform"]
                        # Only override platform URLs if not already set from registration
                        if not config.platform.api_url or config.platform.api_url == "http://localhost:3001":
                            config.platform = PlatformConfig(
                                api_url=platform.get("api_url", config.platform.api_url),
                                ws_url=platform.get("ws_url", config.platform.ws_url)
                            )
                    
                    logger.debug(f"Merged YAML config from {yaml_path}")
                    break  # Only load from first found YAML
                    
                except Exception as e:
                    logger.warning(f"Failed to load YAML config from {yaml_path}: {e}")
        
        return config
    
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

