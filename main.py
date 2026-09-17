"""Backend Server Application Entry Point."""

import sys

import uvicorn

from app.config import settings
from app.deps import check_provider_requirements


def start_server():
    """Start the FastAPI & WebSocket backend server.

    Data-provider requirements are validated first so the operator is told
    which API keys are missing before any live-data run starts.
    """
    try:
        check_provider_requirements()
    except RuntimeError as e:
        print(f"STARTUP ABORTED: {e}", file=sys.stderr)
        raise SystemExit(1) from e

    uvicorn.run(
        "app.server:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=(settings.environment == "development"),
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    start_server()
