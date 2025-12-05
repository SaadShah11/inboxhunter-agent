"""
Socket.io client for real-time communication with InboxHunter platform.
Uses python-socketio to connect to NestJS Socket.io server.
"""

import asyncio
import json
from typing import Optional, Dict, Any, Callable, Awaitable
from datetime import datetime
from loguru import logger

try:
    import socketio
    SOCKETIO_AVAILABLE = True
except ImportError:
    SOCKETIO_AVAILABLE = False
    logger.warning("python-socketio not installed. Run: pip install python-socketio[asyncio_client]")


class PlatformWebSocket:
    """
    Socket.io client for bi-directional communication with platform.
    
    Events (from server):
    - connected: Connection acknowledged
    - task:execute: New task to execute
    - config:update: Configuration update
    - command: Control command (pause, stop, etc.)
    
    Events (to server):
    - heartbeat: Keep-alive ping
    - task:progress: Task progress update
    - task:complete: Task completion
    - log: Log message
    """
    
    RECONNECT_DELAY = 5  # Seconds between reconnection attempts
    HEARTBEAT_INTERVAL = 30  # Seconds between heartbeats
    
    def __init__(
        self,
        url: str,
        agent_id: str,
        agent_token: str,
        on_task: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
        on_config_update: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
        on_command: Optional[Callable[[str, Dict[str, Any]], Awaitable[None]]] = None
    ):
        """
        Initialize Socket.io client.
        
        Args:
            url: Platform URL (http://localhost:3001)
            agent_id: Unique agent identifier
            agent_token: Authentication token
            on_task: Callback for incoming tasks
            on_config_update: Callback for config updates
            on_command: Callback for control commands
        """
        # Convert ws:// to http:// for Socket.io
        self.url = url.replace("ws://", "http://").replace("wss://", "https://")
        # Remove /ws/agent path if present (Socket.io uses namespace differently)
        if "/ws/agent" in self.url:
            self.url = self.url.replace("/ws/agent", "")
        
        self.agent_id = agent_id
        self.agent_token = agent_token
        
        # Callbacks
        self.on_task = on_task
        self.on_config_update = on_config_update
        self.on_command = on_command
        
        # Connection state
        self._sio: Optional[socketio.AsyncClient] = None
        self._connected = False
        self._should_run = True
        
        # Heartbeat task
        self._heartbeat_task: Optional[asyncio.Task] = None
    
    @property
    def is_connected(self) -> bool:
        """Check if currently connected."""
        return self._connected and self._sio is not None
    
    async def connect(self) -> bool:
        """
        Establish Socket.io connection to platform.
        
        Returns:
            True if connected successfully
        """
        if not SOCKETIO_AVAILABLE:
            logger.error("python-socketio not available. Install with: pip install python-socketio[asyncio_client]")
            return False
        
        try:
            logger.info(f"Connecting to {self.url}/ws/agent...")
            
            # Create Socket.io client
            self._sio = socketio.AsyncClient(
                reconnection=True,
                reconnection_attempts=5,
                reconnection_delay=self.RECONNECT_DELAY,
                logger=False,
                engineio_logger=False
            )
            
            # Register event handlers
            self._register_handlers()
            
            # Connect with auth token
            await self._sio.connect(
                self.url,
                namespaces=['/ws/agent'],
                auth={'token': self.agent_token},
                transports=['websocket', 'polling']
            )
            
            # Wait a moment for connection to establish
            await asyncio.sleep(0.5)
            
            if self._sio.connected:
                self._connected = True
                logger.success("✅ Socket.io connected to platform")
                
                # Start heartbeat
                self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                
                return True
            else:
                logger.error("Socket.io connection failed")
                return False
            
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self._connected = False
            return False
    
    def _register_handlers(self):
        """Register Socket.io event handlers."""
        sio = self._sio
        
        @sio.on('connect', namespace='/ws/agent')
        async def on_connect():
            logger.info("Socket.io: Connected event received")
            self._connected = True
        
        @sio.on('disconnect', namespace='/ws/agent')
        async def on_disconnect():
            logger.warning("Socket.io: Disconnected from platform")
            self._connected = False
        
        @sio.on('connected', namespace='/ws/agent')
        async def on_connected_ack(data):
            logger.info(f"Socket.io: Connection acknowledged - Agent ID: {data.get('agentId')}")
        
        @sio.on('task:execute', namespace='/ws/agent')
        async def on_task_execute(data):
            logger.info(f"Socket.io: Received task to execute")
            if self.on_task:
                await self.on_task(data)
        
        @sio.on('config:update', namespace='/ws/agent')
        async def on_config_update(data):
            logger.info("Socket.io: Received config update")
            if self.on_config_update:
                await self.on_config_update(data)
        
        @sio.on('command', namespace='/ws/agent')
        async def on_command(data):
            command = data.get('command')
            params = data.get('params', {})
            logger.info(f"Socket.io: Received command: {command}")
            if self.on_command:
                await self.on_command(command, params)
        
        @sio.on('error', namespace='/ws/agent')
        async def on_error(data):
            logger.error(f"Socket.io: Server error: {data}")
        
        @sio.on('connect_error', namespace='/ws/agent')
        async def on_connect_error(data):
            logger.error(f"Socket.io: Connection error: {data}")
    
    async def disconnect(self):
        """Disconnect from platform."""
        self._should_run = False
        self._connected = False
        
        # Cancel heartbeat
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        
        # Disconnect Socket.io
        if self._sio:
            try:
                await self._sio.disconnect()
            except:
                pass
            self._sio = None
        
        logger.info("Socket.io disconnected")
    
    async def _heartbeat_loop(self):
        """Background task to send heartbeats."""
        while self._should_run and self._connected:
            try:
                await asyncio.sleep(self.HEARTBEAT_INTERVAL)
                if self._connected and self._sio:
                    await self._sio.emit('heartbeat', {'status': 'online'}, namespace='/ws/agent')
                    logger.debug("Heartbeat sent")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
    
    async def send_task_result(self, task_id: str, result: Dict[str, Any]):
        """
        Send task execution result to platform.
        
        Args:
            task_id: ID of the completed task
            result: Task result dictionary
        """
        if not self._connected or not self._sio:
            logger.warning("Not connected, cannot send task result")
            return
        
        try:
            await self._sio.emit('task:complete', {
                'taskId': task_id,
                'result': result
            }, namespace='/ws/agent')
            logger.debug(f"Sent result for task {task_id}")
        except Exception as e:
            logger.error(f"Failed to send task result: {e}")
    
    async def send_task_progress(self, task_id: str, progress: int, status: str = None):
        """
        Send task progress update.
        
        Args:
            task_id: Task ID
            progress: Progress percentage (0-100)
            status: Optional status message
        """
        if not self._connected or not self._sio:
            return
        
        try:
            await self._sio.emit('task:progress', {
                'taskId': task_id,
                'progress': progress,
                'status': status
            }, namespace='/ws/agent')
        except Exception as e:
            logger.error(f"Failed to send progress: {e}")
    
    async def send_log(self, level: str, message: str, metadata: Dict = None):
        """
        Send log message to platform for remote viewing.
        
        Args:
            level: Log level (info, warning, error)
            message: Log message
            metadata: Optional additional data
        """
        if not self._connected or not self._sio:
            return
        
        try:
            await self._sio.emit('log', {
                'level': level,
                'message': message,
                'metadata': metadata
            }, namespace='/ws/agent')
        except Exception as e:
            logger.debug(f"Failed to send log: {e}")
    
    async def send_scraped_links(self, links: list):
        """
        Send scraped links to platform for bulk storage.
        
        Args:
            links: List of scraped link data dictionaries
        """
        if not self._connected or not self._sio:
            logger.warning("Not connected, cannot send scraped links")
            return
        
        try:
            await self._sio.emit('scrape:results', {
                'links': links,
                'count': len(links)
            }, namespace='/ws/agent')
            logger.info(f"Sent {len(links)} scraped links to platform")
        except Exception as e:
            logger.error(f"Failed to send scraped links: {e}")
    
    async def process_messages(self):
        """
        Process incoming messages.
        Socket.io handles this automatically, but we need this for compatibility.
        """
        if not self._connected:
            return
        
        # Socket.io handles message processing internally
        # Just yield control to event loop
        await asyncio.sleep(0.1)


class MockPlatformWebSocket:
    """
    Mock WebSocket client for offline/testing mode.
    Simulates platform communication without actual connection.
    """
    
    def __init__(self, **kwargs):
        self.is_connected = False
        self.on_task = kwargs.get("on_task")
        self.on_config_update = kwargs.get("on_config_update")
        self.on_command = kwargs.get("on_command")
    
    async def connect(self) -> bool:
        logger.info("Mock Socket.io: Simulating connection")
        self.is_connected = True
        return True
    
    async def disconnect(self):
        self.is_connected = False
        logger.info("Mock Socket.io: Disconnected")
    
    async def send_task_result(self, task_id: str, result: Dict[str, Any]):
        logger.info(f"Mock Socket.io: Task result for {task_id}: {result.get('success')}")
    
    async def send_task_progress(self, task_id: str, progress: int, status: str = None):
        logger.debug(f"Mock Socket.io: Progress {progress}%")
    
    async def send_log(self, level: str, message: str, metadata: Dict = None):
        pass
    
    async def send_scraped_links(self, links: list):
        logger.info(f"Mock Socket.io: Scraped {len(links)} links")
    
    async def process_messages(self):
        await asyncio.sleep(0.1)
