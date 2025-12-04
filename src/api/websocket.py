"""
WebSocket client for real-time communication with InboxHunter platform.
"""

import asyncio
import json
from typing import Optional, Dict, Any, Callable, Awaitable
from datetime import datetime
from loguru import logger

try:
    import websockets
    from websockets.client import WebSocketClientProtocol
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    logger.warning("websockets library not installed, using fallback")


class PlatformWebSocket:
    """
    WebSocket client for bi-directional communication with platform.
    
    Message types:
    - task: New task to execute
    - config: Configuration update
    - command: Control command (pause, stop, etc.)
    - heartbeat: Keep-alive ping
    - result: Task result (agent → platform)
    - status: Agent status update (agent → platform)
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
        Initialize WebSocket client.
        
        Args:
            url: WebSocket URL (wss://api.inboxhunter.io/ws)
            agent_id: Unique agent identifier
            agent_token: Authentication token
            on_task: Callback for incoming tasks
            on_config_update: Callback for config updates
            on_command: Callback for control commands
        """
        self.url = url
        self.agent_id = agent_id
        self.agent_token = agent_token
        
        # Callbacks
        self.on_task = on_task
        self.on_config_update = on_config_update
        self.on_command = on_command
        
        # Connection state
        self._ws: Optional[Any] = None  # WebSocketClientProtocol
        self._connected = False
        self._reconnecting = False
        self._should_run = True
        
        # Message queue for offline buffering
        self._outgoing_queue: asyncio.Queue = asyncio.Queue()
        
        # Tasks
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._receive_task: Optional[asyncio.Task] = None
    
    @property
    def is_connected(self) -> bool:
        """Check if currently connected."""
        return self._connected and self._ws is not None
    
    async def connect(self) -> bool:
        """
        Establish WebSocket connection to platform.
        
        Returns:
            True if connected successfully
        """
        if not WEBSOCKETS_AVAILABLE:
            logger.error("websockets library not available")
            return False
        
        try:
            # Build connection URL with auth
            auth_url = f"{self.url}?agent_id={self.agent_id}&token={self.agent_token}"
            
            logger.info(f"Connecting to {self.url}...")
            
            self._ws = await websockets.connect(
                auth_url,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=5
            )
            
            self._connected = True
            logger.info("WebSocket connected")
            
            # Send initial status
            await self._send_status("connected")
            
            # Start background tasks
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            self._receive_task = asyncio.create_task(self._receive_loop())
            
            # Flush any queued messages
            await self._flush_queue()
            
            return True
            
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self._connected = False
            return False
    
    async def disconnect(self):
        """Disconnect from platform."""
        self._should_run = False
        self._connected = False
        
        # Cancel background tasks
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        
        # Close WebSocket
        if self._ws:
            try:
                await self._ws.close()
            except:
                pass
            self._ws = None
        
        logger.info("WebSocket disconnected")
    
    async def _receive_loop(self):
        """Background task to receive and process messages."""
        while self._should_run and self._ws:
            try:
                message = await self._ws.recv()
                await self._handle_message(message)
                
            except websockets.ConnectionClosed:
                logger.warning("WebSocket connection closed")
                self._connected = False
                if self._should_run:
                    await self._reconnect()
                break
                
            except Exception as e:
                logger.error(f"Receive error: {e}")
                await asyncio.sleep(1)
    
    async def _heartbeat_loop(self):
        """Background task to send heartbeats."""
        while self._should_run:
            try:
                await asyncio.sleep(self.HEARTBEAT_INTERVAL)
                if self._connected:
                    await self._send({
                        "type": "heartbeat",
                        "timestamp": datetime.utcnow().isoformat()
                    })
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
    
    async def _reconnect(self):
        """Attempt to reconnect to platform."""
        if self._reconnecting:
            return
        
        self._reconnecting = True
        attempt = 0
        
        while self._should_run:
            attempt += 1
            logger.info(f"Reconnection attempt {attempt}...")
            
            if await self.connect():
                self._reconnecting = False
                return
            
            # Exponential backoff (max 60 seconds)
            delay = min(self.RECONNECT_DELAY * (2 ** (attempt - 1)), 60)
            logger.info(f"Reconnecting in {delay}s...")
            await asyncio.sleep(delay)
        
        self._reconnecting = False
    
    async def _handle_message(self, raw_message: str):
        """
        Process incoming WebSocket message.
        
        Args:
            raw_message: Raw JSON message string
        """
        try:
            message = json.loads(raw_message)
            msg_type = message.get("type")
            data = message.get("data", {})
            
            logger.debug(f"Received message: {msg_type}")
            
            if msg_type == "task":
                if self.on_task:
                    await self.on_task(data)
                    
            elif msg_type == "config":
                if self.on_config_update:
                    await self.on_config_update(data)
                    
            elif msg_type == "command":
                command = data.get("command")
                params = data.get("params", {})
                if self.on_command:
                    await self.on_command(command, params)
                    
            elif msg_type == "heartbeat_ack":
                logger.debug("Heartbeat acknowledged")
                
            elif msg_type == "error":
                logger.error(f"Platform error: {data.get('message')}")
                
            else:
                logger.warning(f"Unknown message type: {msg_type}")
                
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON message: {raw_message[:100]}")
        except Exception as e:
            logger.error(f"Message handling error: {e}")
    
    async def _send(self, message: Dict[str, Any]) -> bool:
        """
        Send message to platform.
        
        Args:
            message: Message dictionary to send
            
        Returns:
            True if sent successfully
        """
        if not self._connected or not self._ws:
            # Queue for later
            await self._outgoing_queue.put(message)
            return False
        
        try:
            await self._ws.send(json.dumps(message))
            return True
        except Exception as e:
            logger.error(f"Send error: {e}")
            await self._outgoing_queue.put(message)
            return False
    
    async def _flush_queue(self):
        """Send all queued messages."""
        while not self._outgoing_queue.empty():
            try:
                message = self._outgoing_queue.get_nowait()
                if self._ws:
                    await self._ws.send(json.dumps(message))
            except Exception as e:
                logger.error(f"Queue flush error: {e}")
                break
    
    async def _send_status(self, status: str, details: Optional[Dict] = None):
        """Send status update to platform."""
        await self._send({
            "type": "status",
            "data": {
                "status": status,
                "agent_id": self.agent_id,
                "timestamp": datetime.utcnow().isoformat(),
                **(details or {})
            }
        })
    
    async def send_task_result(self, task_id: str, result: Dict[str, Any]):
        """
        Send task execution result to platform.
        
        Args:
            task_id: ID of the completed task
            result: Task result dictionary
        """
        await self._send({
            "type": "result",
            "data": {
                "task_id": task_id,
                "result": result,
                "timestamp": datetime.utcnow().isoformat()
            }
        })
        logger.debug(f"Sent result for task {task_id}")
    
    async def send_log(self, level: str, message: str):
        """
        Send log message to platform for remote viewing.
        
        Args:
            level: Log level (info, warning, error)
            message: Log message
        """
        await self._send({
            "type": "log",
            "data": {
                "level": level,
                "message": message,
                "timestamp": datetime.utcnow().isoformat()
            }
        })
    
    async def request_task(self):
        """Request a new task from the platform."""
        await self._send({
            "type": "request_task",
            "data": {
                "agent_id": self.agent_id,
                "timestamp": datetime.utcnow().isoformat()
            }
        })
    
    async def process_messages(self):
        """
        Process incoming messages (call this in main loop if not using background tasks).
        """
        if not self._connected or not self._ws:
            return
        
        try:
            # Non-blocking check for messages
            message = await asyncio.wait_for(self._ws.recv(), timeout=0.1)
            await self._handle_message(message)
        except asyncio.TimeoutError:
            pass
        except websockets.ConnectionClosed:
            self._connected = False
            if self._should_run:
                asyncio.create_task(self._reconnect())


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
        logger.info("Mock WebSocket: Simulating connection")
        self.is_connected = True
        return True
    
    async def disconnect(self):
        self.is_connected = False
        logger.info("Mock WebSocket: Disconnected")
    
    async def send_task_result(self, task_id: str, result: Dict[str, Any]):
        logger.info(f"Mock WebSocket: Task result for {task_id}: {result.get('success')}")
    
    async def send_log(self, level: str, message: str):
        pass
    
    async def request_task(self):
        logger.info("Mock WebSocket: Task requested")
    
    async def process_messages(self):
        await asyncio.sleep(0.1)

