"""
Configuration management using Pydantic for validation and type safety.
"""

import os
from pathlib import Path
from typing import List, Optional, Tuple, Union

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings


class PhoneConfig(BaseModel):
    """Phone number configuration."""
    country_code: str = "+1"
    number: str = ""
    full: str = ""


class CredentialsConfig(BaseModel):
    """Sign-up credentials configuration."""
    first_name: str
    last_name: str = ""
    full_name: str = ""
    email: str
    phone: Union[PhoneConfig, str]  # Support both old (string) and new (object) format


class CaptchaConfig(BaseModel):
    """CAPTCHA service configuration."""
    service: str = "2captcha"
    api_keys: dict = Field(default_factory=dict)
    timeout: int = 120
    retry_attempts: int = 3


class MetaAdsConfig(BaseModel):
    """Meta Ads Library configuration."""
    enabled: bool = True
    access_token: str = ""
    search_keywords: List[str] = Field(default_factory=list)
    ad_limit: int = 100


class ExtensionDataConfig(BaseModel):
    """Browser extension data configuration."""
    enabled: bool = True
    data_path: str


class CSVDataConfig(BaseModel):
    """CSV data source configuration."""
    enabled: bool = False
    data_path: str = "./data/training.csv"


class SourcesConfig(BaseModel):
    """Data sources configuration."""
    meta_ads_library: MetaAdsConfig = Field(default_factory=MetaAdsConfig)
    my_ad_finder: Optional[ExtensionDataConfig] = None
    turbo_ad_finder: Optional[ExtensionDataConfig] = None
    csv_data: CSVDataConfig = Field(default_factory=CSVDataConfig)


class StealthConfig(BaseModel):
    """Browser stealth configuration."""
    enabled: bool = True
    webdriver: bool = False
    chrome_app: bool = True
    plugins: bool = True
    mime_types: bool = True


class BehaviorConfig(BaseModel):
    """Human-like behavior configuration."""
    mouse_movements: bool = True
    typing_delay_min: float = 0.1
    typing_delay_max: float = 0.3
    typing_mistakes: bool = True
    mistake_probability: float = 0.05


class TimeoutsConfig(BaseModel):
    """Timeout configuration."""
    page_load: int = 30
    element_wait: int = 10
    form_submit: int = 15


class DelaysConfig(BaseModel):
    """Delays configuration."""
    before_form_fill: Tuple[float, float] = (1.0, 3.0)
    between_fields: Tuple[float, float] = (0.5, 1.5)
    before_submit: Tuple[float, float] = (1.0, 2.0)
    after_submit: Tuple[float, float] = (3.0, 5.0)


class ViewportConfig(BaseModel):
    """Browser viewport configuration."""
    width: int = 1920
    height: int = 1080


class AutomationConfig(BaseModel):
    """Browser automation configuration."""
    browser: str = "chromium"
    headless: bool = False
    viewport: ViewportConfig = Field(default_factory=ViewportConfig)
    user_agent: str = "auto"
    stealth: StealthConfig = Field(default_factory=StealthConfig)
    behavior: BehaviorConfig = Field(default_factory=BehaviorConfig)
    timeouts: TimeoutsConfig = Field(default_factory=TimeoutsConfig)
    delays: DelaysConfig = Field(default_factory=DelaysConfig)


class RateLimitingConfig(BaseModel):
    """Rate limiting configuration."""
    max_signups_per_hour: int = 50
    max_signups_per_day: int = 500
    delay_between_signups: Tuple[int, int] = (30, 120)
    max_consecutive_failures: int = 5
    cooldown_after_failures: int = 600


class DatabaseConfig(BaseModel):
    """Database configuration (SQLite)."""
    url: str = ""  # Empty = use default SQLite in data/bot.db
    echo: bool = False
    
    @model_validator(mode='after')
    def set_default_url(self) -> 'DatabaseConfig':
        """Set default SQLite URL if not provided."""
        if not self.url:
            from pathlib import Path
            # Use data/bot.db in project folder
            data_dir = Path("data")
            data_dir.mkdir(parents=True, exist_ok=True)
            self.url = f"sqlite:///{data_dir / 'bot.db'}"
        return self


class LoggingConfig(BaseModel):
    """Logging configuration."""
    directory: str = "./logs"
    file_name: str = "bot_{date}.log"
    rotation: str = "1 day"
    retention: str = "30 days"
    format: str = "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"


class ProxyConfig(BaseModel):
    """Proxy configuration."""
    enabled: bool = False
    url: str = ""
    username: str = ""
    password: str = ""


class FormDetectionConfig(BaseModel):
    """Form field detection rules."""
    email_field_patterns: List[str] = Field(default_factory=list)
    first_name_field_patterns: List[str] = Field(default_factory=list)
    phone_field_patterns: List[str] = Field(default_factory=list)
    submit_button_patterns: List[str] = Field(default_factory=list)


class ErrorHandlingConfig(BaseModel):
    """Error handling configuration."""
    screenshot_on_error: bool = True
    max_retries: int = 3
    retry_delay: int = 5
    skip_on_permanent_error: bool = True


class AppConfig(BaseModel):
    """Main application configuration."""
    name: str = "Reverse Outreach Bot"
    version: str = "1.0.0"
    debug: bool = True
    log_level: str = "INFO"


class LLMConfig(BaseModel):
    """LLM configuration for AI Agent."""
    enabled: bool = True
    provider: str = "openai"  # openai or anthropic
    api_key: str = ""
    model: str = "gpt-4o"


class Config(BaseModel):
    """Root configuration."""
    app: AppConfig = Field(default_factory=AppConfig)
    credentials: CredentialsConfig
    captcha: CaptchaConfig
    llm: LLMConfig = Field(default_factory=LLMConfig)
    sources: SourcesConfig
    automation: AutomationConfig
    rate_limiting: RateLimitingConfig = Field(default_factory=RateLimitingConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    proxy: ProxyConfig = Field(default_factory=ProxyConfig)
    form_detection: FormDetectionConfig = Field(default_factory=FormDetectionConfig)
    error_handling: ErrorHandlingConfig = Field(default_factory=ErrorHandlingConfig)


class ConfigLoader:
    """Configuration loader with environment variable support."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize configuration loader."""
        if config_path is None:
            # Try multiple possible config locations
            possible_paths = [
                Path("config/config.yaml"),
                Path("config.yaml"),
                Path(__file__).parent.parent / "config" / "config.yaml"
            ]
            
            for path in possible_paths:
                if path.exists():
                    config_path = str(path)
                    break
            
            if config_path is None:
                raise FileNotFoundError(
                    "Config file not found. Please create config/config.yaml from config.example.yaml"
                )
        
        self.config_path = Path(config_path)
        self._config: Optional[Config] = None
    
    def load(self) -> Config:
        """Load and validate configuration."""
        if self._config is not None:
            return self._config
        
        # Load YAML file
        with open(self.config_path, 'r') as f:
            config_data = yaml.safe_load(f)
        
        # Override with environment variables if present
        config_data = self._apply_env_overrides(config_data)
        
        # Validate and create config object
        self._config = Config(**config_data)
        return self._config
    
    def _apply_env_overrides(self, config_data: dict) -> dict:
        """Apply environment variable overrides to config.
        
        Environment variables take precedence over config file values.
        This enables secure deployment where secrets are injected via env vars.
        """
        # App settings
        if os.getenv("APP_DEBUG"):
            config_data.setdefault("app", {})["debug"] = os.getenv("APP_DEBUG", "false").lower() == "true"
        if os.getenv("APP_LOG_LEVEL"):
            config_data.setdefault("app", {})["log_level"] = os.getenv("APP_LOG_LEVEL")
        
        # Override credentials from environment
        if os.getenv("SIGNUP_FIRST_NAME"):
            config_data.setdefault("credentials", {})["first_name"] = os.getenv("SIGNUP_FIRST_NAME")
        if os.getenv("SIGNUP_LAST_NAME"):
            config_data.setdefault("credentials", {})["last_name"] = os.getenv("SIGNUP_LAST_NAME")
        if os.getenv("SIGNUP_FULL_NAME"):
            config_data.setdefault("credentials", {})["full_name"] = os.getenv("SIGNUP_FULL_NAME")
        if os.getenv("SIGNUP_EMAIL"):
            config_data.setdefault("credentials", {})["email"] = os.getenv("SIGNUP_EMAIL")
        if os.getenv("SIGNUP_PHONE"):
            config_data.setdefault("credentials", {})["phone"] = os.getenv("SIGNUP_PHONE")
        
        # Override CAPTCHA keys
        if os.getenv("TWOCAPTCHA_API_KEY"):
            config_data.setdefault("captcha", {}).setdefault("api_keys", {})["twocaptcha"] = os.getenv("TWOCAPTCHA_API_KEY")
        if os.getenv("ANTICAPTCHA_API_KEY"):
            config_data.setdefault("captcha", {}).setdefault("api_keys", {})["anticaptcha"] = os.getenv("ANTICAPTCHA_API_KEY")
        
        # Override LLM settings
        if os.getenv("OPENAI_API_KEY"):
            config_data.setdefault("llm", {})["api_key"] = os.getenv("OPENAI_API_KEY")
            config_data.setdefault("llm", {})["enabled"] = True
        if os.getenv("LLM_PROVIDER"):
            config_data.setdefault("llm", {})["provider"] = os.getenv("LLM_PROVIDER")
        if os.getenv("LLM_MODEL"):
            config_data.setdefault("llm", {})["model"] = os.getenv("LLM_MODEL")
        
        # Override database URL
        if os.getenv("DATABASE_URL"):
            config_data.setdefault("database", {})["url"] = os.getenv("DATABASE_URL")
        
        # Override Meta Ads settings
        if os.getenv("META_ACCESS_TOKEN"):
            config_data.setdefault("sources", {}).setdefault("meta_ads_library", {})["access_token"] = os.getenv("META_ACCESS_TOKEN")
        
        # Automation settings (for production)
        if os.getenv("HEADLESS"):
            config_data.setdefault("automation", {})["headless"] = os.getenv("HEADLESS", "true").lower() == "true"
        
        # Proxy settings
        if os.getenv("PROXY_URL"):
            config_data.setdefault("proxy", {})["enabled"] = True
            config_data.setdefault("proxy", {})["url"] = os.getenv("PROXY_URL")
        if os.getenv("PROXY_USERNAME"):
            config_data.setdefault("proxy", {})["username"] = os.getenv("PROXY_USERNAME")
        if os.getenv("PROXY_PASSWORD"):
            config_data.setdefault("proxy", {})["password"] = os.getenv("PROXY_PASSWORD")
        
        return config_data
    
    @property
    def config(self) -> Config:
        """Get loaded configuration."""
        if self._config is None:
            return self.load()
        return self._config


# Global config instance
_config_loader: Optional[ConfigLoader] = None


def get_config() -> Config:
    """Get global configuration instance."""
    global _config_loader
    if _config_loader is None:
        _config_loader = ConfigLoader()
    return _config_loader.config


def reload_config(config_path: Optional[str] = None):
    """Reload configuration from file."""
    global _config_loader
    _config_loader = ConfigLoader(config_path)
    return _config_loader.load()

