"""
InboxHunter Agent - Source Package

A lightweight desktop agent for browser automation that connects
to the InboxHunter platform.
"""

__version__ = "2.0.0"
__author__ = "InboxHunter"

# Core components
from .core import InboxHunterAgent, AgentConfig, get_agent_config

# API clients  
from .api import PlatformWebSocket, PlatformClient

# UI
from .ui import SystemTrayApp

__all__ = [
    "InboxHunterAgent",
    "AgentConfig", 
    "get_agent_config",
    "PlatformWebSocket",
    "PlatformClient",
    "SystemTrayApp",
]
