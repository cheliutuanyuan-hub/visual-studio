"""Uvicorn entrypoint: ``python -m visual_studio``.

Reads configuration from the environment (``VISUAL_*`` vars / ``.env``) and
launches the HTTP server with the background worker running.
"""

from __future__ import annotations

import uvicorn

from visual_studio.api.app import create_app
from visual_studio.config import get_settings
from visual_studio.service.generation_service import GenerationService


def main() -> None:
    config = get_settings()
    service = GenerationService(config)
    app = create_app(service)
    uvicorn.run(app, host=config.host, port=config.port, log_level="info")


if __name__ == "__main__":
    main()
