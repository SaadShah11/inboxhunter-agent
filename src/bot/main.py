"""
Main entry point for the Reverse Outreach Bot.
"""

import asyncio
import argparse
import sys
import os
import threading
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger
from src.utils.logger import setup_logger
from src.config import get_config
from src.bot.orchestrator import ReverseOutreachBot


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Reverse Outreach Automation Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with enabled sources (Meta Ads Library by default)
  python -m src.bot.main
  
  # Run with specific source
  python -m src.bot.main --source meta
  
  # Limit number of sign-ups
  python -m src.bot.main --max-signups 10
  
  # Debug mode with verbose logging
  python -m src.bot.main --debug
        """
    )
    
    parser.add_argument(
        "--source",
        choices=["meta", "extensions", "csv"],
        default=None,
        help="Specific data source to use (default: uses enabled sources from config)"
    )
    
    parser.add_argument(
        "--max-signups",
        type=int,
        default=None,
        help="Maximum number of sign-ups to process"
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode with verbose logging"
    )
    
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to custom config file"
    )
    
    return parser.parse_args()


def start_health_server():
    """Start health check server in background thread for AWS ELB/ECS."""
    try:
        from src.api.health import run_health_server
        health_port = int(os.getenv("HEALTH_PORT", "8080"))
        logger.info(f"🏥 Starting health check server on port {health_port}")
        run_health_server(port=health_port)
    except Exception as e:
        logger.warning(f"Failed to start health server: {e}")


async def main():
    """Main execution function."""
    args = parse_args()
    
    # Setup logger
    setup_logger()
    
    # Print banner
    print_banner()
    
    # Start health check server in production mode
    if os.getenv("HEADLESS", "false").lower() == "true" or os.getenv("ENABLE_HEALTH_SERVER", "false").lower() == "true":
        health_thread = threading.Thread(target=start_health_server, daemon=True)
        health_thread.start()
    
    # Load config
    try:
        if args.config:
            from src.config import reload_config
            config = reload_config(args.config)
        else:
            config = get_config()
        
        # Override debug setting if specified
        if args.debug:
            config.app.debug = True
            config.app.log_level = "DEBUG"
            logger.remove()
            setup_logger()
            logger.debug("Debug mode enabled")
    
    except FileNotFoundError as e:
        logger.error(f"❌ Configuration error: {e}")
        logger.info("💡 Please create config/config.yaml from config/config.example.yaml")
        return 1
    except Exception as e:
        logger.error(f"❌ Failed to load configuration: {e}")
        return 1
    
    # Validate configuration
    if not validate_config(config):
        return 1
    
    # Initialize and run bot
    try:
        bot = ReverseOutreachBot(config)
        await bot.run(source=args.source, max_signups=args.max_signups)
        
        return 0
        
    except KeyboardInterrupt:
        logger.warning("\n⚠️ Bot stopped by user")
        return 130
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        return 1


def print_banner():
    """Print application banner."""
    banner = """
    ╔══════════════════════════════════════════════════════════╗
    ║                                                          ║
    ║         🤖  REVERSE OUTREACH AUTOMATION BOT  🤖          ║
    ║                                                          ║
    ║          Automated Email List Sign-up System            ║
    ║                     Version 1.0.0                        ║
    ║                                                          ║
    ╚══════════════════════════════════════════════════════════╝
    """
    print(banner)


def validate_config(config) -> bool:
    """
    Validate configuration before running.
    
    Args:
        config: Configuration object
        
    Returns:
        True if valid, False otherwise
    """
    errors = []
    
    # Check credentials
    if not config.credentials.email or "@" not in config.credentials.email:
        errors.append("Invalid email address in credentials")
    
    if not config.credentials.first_name:
        errors.append("First name is required in credentials")
    
    if not config.credentials.phone:
        errors.append("Phone number is required in credentials")
    
    # Warnings (non-fatal)
    warnings = []
    
    # Check data sources (Meta Ads Library is primary for MVP)
    if config.sources.meta_ads_library.enabled:
        if not config.sources.meta_ads_library.access_token or \
           config.sources.meta_ads_library.access_token.startswith("YOUR_"):
            warnings.append("Meta Ads Library access token not configured - will skip Meta scraping")
        if not config.sources.meta_ads_library.search_keywords:
            warnings.append("No search keywords configured for Meta Ads Library")
    else:
        warnings.append("Meta Ads Library is disabled - this is the primary data source for MVP")
    
    # CAPTCHA warnings
    if config.captcha.api_keys.get("twocaptcha", "").startswith("YOUR_"):
        warnings.append("2Captcha API key not configured - CAPTCHA solving will fail")
    
    if config.captcha.api_keys.get("anticaptcha", "").startswith("YOUR_"):
        warnings.append("Anti-Captcha API key not configured")
    
    # Print validation results
    if errors:
        logger.error("❌ Configuration validation failed:")
        for error in errors:
            logger.error(f"   • {error}")
        return False
    
    if warnings:
        logger.warning("⚠️  Configuration warnings:")
        for warning in warnings:
            logger.warning(f"   • {warning}")
        logger.info("Continuing anyway...")
    
    logger.success("✅ Configuration validated")
    return True


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

