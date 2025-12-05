#!/usr/bin/env python3
"""
InboxHunter Agent - Main Entry Point

A lightweight desktop agent that connects to the InboxHunter platform
and executes browser automation tasks.

Usage:
    python main.py                  # Normal mode with system tray
    python main.py --console        # Console mode (no GUI)
    python main.py --register       # Register agent with platform
    python main.py --version        # Show version
"""

import argparse
import asyncio
import sys
import signal
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from loguru import logger


# Version
VERSION = "2.0.0"


def setup_logging(debug: bool = False):
    """Configure logging."""
    from src.core.config import get_data_dir
    
    log_dir = get_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Remove default handler
    logger.remove()
    
    # Console handler
    log_level = "DEBUG" if debug else "INFO"
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>",
        level=log_level,
        colorize=True
    )
    
    # File handler
    logger.add(
        log_dir / "agent_{time:YYYY-MM-DD}.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG",
        rotation="1 day",
        retention="7 days",
        compression="gz"
    )
    
    logger.info(f"InboxHunter Agent v{VERSION}")


async def register_agent():
    """Interactive agent registration."""
    from src.api.client import PlatformClient
    from src.core.config import get_agent_config
    
    print("\n" + "=" * 50)
    print("InboxHunter Agent Registration")
    print("=" * 50)
    print("\nTo register this agent, you need a registration token from the dashboard.")
    print()
    print("Steps:")
    print("  1. Open the InboxHunter dashboard (http://localhost:3000)")
    print("  2. Go to Dashboard → Agents")
    print("  3. Click 'Add Agent' and copy the registration token")
    print()
    
    registration_token = input("Enter your registration token: ").strip()
    
    if not registration_token:
        print("❌ No token provided")
        return False
    
    machine_name = input("Enter a name for this agent (or press Enter for default): ").strip()
    
    # Ask for platform URL (for local development)
    print("\nPlatform API URL (press Enter for default http://localhost:3001):")
    api_url = input("API URL: ").strip() or "http://localhost:3001"
    
    print("\nRegistering agent...")
    
    client = PlatformClient(api_url=api_url)
    result = await client.register_agent(registration_token, machine_name or None)
    
    if result:
        # Save to config
        config = get_agent_config()
        config.agent_id = result["agent_id"]
        config.agent_token = result["agent_token"]
        config.platform.api_url = api_url
        config.platform.ws_url = api_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws/agent"
        config.save()
        
        print("\n✅ Agent registered successfully!")
        print(f"   Agent ID: {result['agent_id']}")
        print(f"   Platform: {api_url}")
        print("\nYou can now start the agent with: python main.py")
        return True
    else:
        print("\n❌ Registration failed. Please check your token and try again.")
        print("   Make sure the backend is running and the token is valid.")
        return False


async def run_agent_async(console_mode: bool = False):
    """Run the agent asynchronously."""
    from src.core.agent import InboxHunterAgent, AgentStatus
    from src.core.config import get_agent_config
    
    config = get_agent_config()
    agent = InboxHunterAgent(config)
    
    # Set up UI
    if console_mode:
        from src.ui.tray import ConsoleFallback as UIApp
    else:
        from src.ui.tray import get_ui_app
        UIApp = get_ui_app
    
    # Event loop reference for cross-thread calls
    loop = asyncio.get_event_loop()
    
    def start_agent():
        asyncio.run_coroutine_threadsafe(agent.run(), loop)
    
    def stop_agent():
        asyncio.run_coroutine_threadsafe(agent.stop(), loop)
    
    def quit_app():
        asyncio.run_coroutine_threadsafe(shutdown(), loop)
    
    async def shutdown():
        await agent.stop()
        await agent.cleanup()
        # Exit after cleanup
        loop.call_soon_threadsafe(loop.stop)
    
    # Create UI
    if console_mode:
        ui = UIApp(
            on_start=start_agent,
            on_stop=stop_agent,
            on_quit=quit_app
        )
    else:
        ui = get_ui_app(
            on_start=start_agent,
            on_stop=stop_agent,
            on_quit=quit_app
        )
    
    # Connect agent callbacks to UI
    agent.on_status_change(lambda s: ui.update_status(s.value))
    agent.on_stats_update(lambda s: ui.update_stats(s))
    
    # Handle signals
    def signal_handler(sig, frame):
        logger.info("Shutdown signal received")
        asyncio.run_coroutine_threadsafe(shutdown(), loop)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start UI in background
    ui_thread = ui.run_detached()
    
    # Auto-start agent if configured
    if config.auto_start and config.agent_id and config.agent_token:
        logger.info("Auto-starting agent...")
        await agent.run()
    else:
        if not config.agent_id or not config.agent_token:
            logger.warning("Agent not registered. Run with --register to set up.")
            ui.show_notification(
                "Setup Required",
                "Please register the agent with --register"
            )
        
        # Keep running until quit
        while ui_thread.is_alive():
            await asyncio.sleep(0.5)
    
    # Cleanup
    ui.stop()


def run_agent(console_mode: bool = False):
    """Run the agent (sync wrapper)."""
    try:
        asyncio.run(run_agent_async(console_mode))
    except KeyboardInterrupt:
        logger.info("Interrupted")
    except Exception as e:
        logger.error(f"Agent error: {e}", exc_info=True)
        sys.exit(1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="InboxHunter Agent - Browser automation for email list signups"
    )
    parser.add_argument(
        "--version", "-v",
        action="store_true",
        help="Show version and exit"
    )
    parser.add_argument(
        "--register",
        action="store_true",
        help="Register agent with platform"
    )
    parser.add_argument(
        "--console",
        action="store_true",
        help="Run in console mode (no system tray)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    
    args = parser.parse_args()
    
    # Setup logging first
    setup_logging(debug=args.debug)
    
    if args.version:
        print(f"InboxHunter Agent v{VERSION}")
        sys.exit(0)
    
    if args.register:
        asyncio.run(register_agent())
        sys.exit(0)
    
    # Run agent
    run_agent(console_mode=args.console)


if __name__ == "__main__":
    main()

