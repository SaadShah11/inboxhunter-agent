"""
Health check API for AWS ELB/ECS deployment.
Provides endpoints for load balancer health probes.
"""

import os
import asyncio
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse
from loguru import logger

app = FastAPI(
    title="Reverse Outreach Bot API",
    description="Health check and monitoring API",
    version="1.0.0"
)

# Track bot status
_bot_status = {
    "running": False,
    "last_activity": None,
    "signups_count": 0,
    "errors_count": 0,
    "started_at": None
}


def update_bot_status(running: bool = None, signups: int = None, errors: int = None):
    """Update bot status from main process."""
    global _bot_status
    if running is not None:
        _bot_status["running"] = running
        if running:
            _bot_status["started_at"] = datetime.utcnow().isoformat()
    if signups is not None:
        _bot_status["signups_count"] = signups
    if errors is not None:
        _bot_status["errors_count"] = errors
    _bot_status["last_activity"] = datetime.utcnow().isoformat()


@app.get("/health")
async def health_check():
    """
    Basic health check endpoint for AWS ELB/ECS.
    Returns 200 if service is healthy, 503 otherwise.
    """
    return JSONResponse(
        status_code=200,
        content={
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "service": "reverse-outreach-bot"
        }
    )


@app.get("/health/ready")
async def readiness_check():
    """
    Readiness check - verifies the bot is ready to process requests.
    Used by Kubernetes/ECS for determining if traffic should be routed.
    """
    try:
        # Check database connectivity
        from src.config import get_config
        from src.database import DatabaseOperations
        
        config = get_config()
        db = DatabaseOperations(config.database.url)
        
        # Simple query to verify DB connection
        stats = db.get_today_stats()
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "ready",
                "database": "connected",
                "timestamp": datetime.utcnow().isoformat()
            }
        )
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
        )


@app.get("/health/live")
async def liveness_check():
    """
    Liveness check - verifies the process is alive.
    Used by Kubernetes/ECS to determine if container should be restarted.
    """
    return JSONResponse(
        status_code=200,
        content={
            "status": "alive",
            "timestamp": datetime.utcnow().isoformat()
        }
    )


@app.get("/status")
async def bot_status():
    """
    Get current bot status and statistics.
    """
    return JSONResponse(
        status_code=200,
        content={
            "bot": _bot_status,
            "environment": os.getenv("APP_ENV", "development"),
            "timestamp": datetime.utcnow().isoformat()
        }
    )


def run_health_server(port: int = 8080):
    """Run the health check server in a separate thread."""
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


if __name__ == "__main__":
    run_health_server()

