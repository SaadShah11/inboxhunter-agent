"""
REST API client for InboxHunter platform.
Used for authentication, registration, and non-real-time operations.
"""

import httpx
from typing import Optional, Dict, Any, List
from datetime import datetime
from loguru import logger

from src.core.config import get_data_dir


class PlatformClient:
    """
    REST API client for InboxHunter platform.
    
    Handles:
    - Agent registration
    - Authentication
    - Configuration sync
    - File uploads (screenshots, logs)
    - Version checking
    """
    
    DEFAULT_API_URL = "https://api.inboxhunter.io"
    TIMEOUT = 30
    
    def __init__(
        self,
        api_url: Optional[str] = None,
        agent_id: Optional[str] = None,
        agent_token: Optional[str] = None
    ):
        """
        Initialize API client.
        
        Args:
            api_url: Platform API URL
            agent_id: Agent identifier (from registration)
            agent_token: Authentication token
        """
        self.api_url = (api_url or self.DEFAULT_API_URL).rstrip('/')
        self.agent_id = agent_id
        self.agent_token = agent_token
        
        self._client: Optional[httpx.AsyncClient] = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        self._client = httpx.AsyncClient(
            timeout=self.TIMEOUT,
            headers=self._get_headers()
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with authentication."""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "InboxHunter-Agent/2.0"
        }
        
        if self.agent_token:
            headers["Authorization"] = f"Bearer {self.agent_token}"
        
        if self.agent_id:
            headers["X-Agent-ID"] = self.agent_id
        
        return headers
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Make API request.
        
        Args:
            method: HTTP method
            endpoint: API endpoint (e.g., /agent/register)
            data: Request body data
            params: Query parameters
            
        Returns:
            Response data or None on error
        """
        url = f"{self.api_url}{endpoint}"
        
        try:
            async with httpx.AsyncClient(timeout=self.TIMEOUT) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    json=data,
                    params=params,
                    headers=self._get_headers()
                )
                
                if response.status_code >= 400:
                    logger.error(f"API error {response.status_code}: {response.text}")
                    return None
                
                return response.json()
                
        except httpx.TimeoutException:
            logger.error(f"Request timeout: {endpoint}")
            return None
        except Exception as e:
            logger.error(f"Request error: {e}")
            return None
    
    # ==================== Agent Management ====================
    
    async def register_agent(
        self,
        user_token: str,
        machine_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Register a new agent with the platform.
        
        Args:
            user_token: User's authentication token (from web login)
            machine_name: Optional name for this machine
            
        Returns:
            Registration data including agent_id and agent_token
        """
        import platform
        import uuid
        
        # Generate machine fingerprint
        machine_id = str(uuid.uuid4())  # In production, use actual hardware ID
        
        data = {
            "user_token": user_token,
            "machine_id": machine_id,
            "machine_name": machine_name or platform.node(),
            "os": platform.system(),
            "os_version": platform.release(),
            "agent_version": "2.0.0"
        }
        
        result = await self._request("POST", "/agent/register", data=data)
        
        if result:
            self.agent_id = result.get("agent_id")
            self.agent_token = result.get("agent_token")
            logger.info(f"Agent registered: {self.agent_id}")
        
        return result
    
    async def authenticate(self) -> bool:
        """
        Verify agent authentication with platform.
        
        Returns:
            True if authenticated successfully
        """
        if not self.agent_id or not self.agent_token:
            logger.error("No agent credentials")
            return False
        
        result = await self._request("GET", "/agent/verify")
        
        if result and result.get("valid"):
            logger.info("Authentication verified")
            return True
        
        logger.error("Authentication failed")
        return False
    
    async def get_agent_config(self) -> Optional[Dict[str, Any]]:
        """
        Get agent configuration from platform.
        
        Returns:
            Configuration data
        """
        result = await self._request("GET", "/agent/config")
        
        if result:
            logger.debug("Config retrieved from platform")
        
        return result
    
    async def update_agent_status(
        self,
        status: str,
        details: Optional[Dict] = None
    ) -> bool:
        """
        Update agent status on platform.
        
        Args:
            status: Current status (idle, running, error, etc.)
            details: Additional status details
            
        Returns:
            True if updated successfully
        """
        data = {
            "status": status,
            "timestamp": datetime.utcnow().isoformat(),
            **(details or {})
        }
        
        result = await self._request("POST", "/agent/status", data=data)
        return result is not None
    
    # ==================== Tasks ====================
    
    async def get_pending_tasks(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get pending tasks from platform.
        
        Args:
            limit: Maximum number of tasks to retrieve
            
        Returns:
            List of task objects
        """
        result = await self._request(
            "GET",
            "/agent/tasks",
            params={"limit": limit, "status": "pending"}
        )
        
        if result:
            return result.get("tasks", [])
        
        return []
    
    async def submit_task_result(
        self,
        task_id: str,
        result: Dict[str, Any]
    ) -> bool:
        """
        Submit task execution result.
        
        Args:
            task_id: Task ID
            result: Execution result
            
        Returns:
            True if submitted successfully
        """
        data = {
            "task_id": task_id,
            "result": result,
            "completed_at": datetime.utcnow().isoformat()
        }
        
        response = await self._request("POST", f"/agent/tasks/{task_id}/result", data=data)
        return response is not None
    
    # ==================== File Uploads ====================
    
    async def upload_screenshot(
        self,
        task_id: str,
        screenshot_path: str,
        screenshot_type: str = "result"
    ) -> Optional[str]:
        """
        Upload a screenshot to platform.
        
        Args:
            task_id: Associated task ID
            screenshot_path: Path to screenshot file
            screenshot_type: Type (result, error, debug)
            
        Returns:
            Uploaded file URL or None
        """
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                with open(screenshot_path, "rb") as f:
                    files = {"file": f}
                    data = {
                        "task_id": task_id,
                        "type": screenshot_type
                    }
                    
                    response = await client.post(
                        f"{self.api_url}/agent/screenshots",
                        files=files,
                        data=data,
                        headers={"Authorization": f"Bearer {self.agent_token}"}
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        return result.get("url")
                    
                    logger.error(f"Screenshot upload failed: {response.status_code}")
                    return None
                    
        except Exception as e:
            logger.error(f"Screenshot upload error: {e}")
            return None
    
    # ==================== Version ====================
    
    async def check_version(self, current_version: str) -> Optional[Dict[str, Any]]:
        """
        Check for agent updates.
        
        Args:
            current_version: Current agent version
            
        Returns:
            Update info if available
        """
        result = await self._request(
            "GET",
            "/agent/version",
            params={"current_version": current_version}
        )
        
        return result
    
    # ==================== Signups ====================
    
    async def get_signup_history(
        self,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get signup history from platform.
        
        Args:
            limit: Number of records to retrieve
            offset: Pagination offset
            
        Returns:
            List of signup records
        """
        result = await self._request(
            "GET",
            "/agent/signups",
            params={"limit": limit, "offset": offset}
        )
        
        if result:
            return result.get("signups", [])
        
        return []


# Convenience function for quick API calls
async def get_platform_client(
    api_url: Optional[str] = None,
    agent_id: Optional[str] = None,
    agent_token: Optional[str] = None
) -> PlatformClient:
    """
    Get a configured platform client.
    
    If no credentials provided, loads from config.
    """
    from src.core.config import get_agent_config
    
    if not agent_id or not agent_token:
        config = get_agent_config()
        agent_id = config.agent_id
        agent_token = config.agent_token
        api_url = api_url or config.platform.api_url
    
    return PlatformClient(
        api_url=api_url,
        agent_id=agent_id,
        agent_token=agent_token
    )

