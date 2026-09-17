"""Backend Server Application Entry Point."""

import uvicorn
from app.config import settings


def start_server():
    """Start the FastAPI & WebSocket backend server."""
    uvicorn.run(
        "app.server:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=(settings.environment == "development"),
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    start_server()
