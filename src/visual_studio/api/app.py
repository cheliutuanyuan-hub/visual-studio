"""FastAPI application factory.

``create_app`` wires the HTTP layer to a :class:`GenerationService`. The
lifespan hook performs restart recovery (reconcile) and starts the background
worker that drains the queue, so a POST to ``/v1/generate/batch`` is turned into
succeeded tasks automatically.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from visual_studio.api.routers import generate, health, tasks
from visual_studio.logging_config import get_logger
from visual_studio.service.generation_service import GenerationService

logger = get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    service: GenerationService = app.state.service
    reset = service.reconcile()
    logger.info("startup: reconciled %d dangling task(s)", reset)
    service.start_worker()
    try:
        yield
    finally:
        service.stop_worker()


def create_app(service: GenerationService) -> FastAPI:
    """Build the FastAPI app bound to ``service``."""
    app = FastAPI(
        title="visual-studio",
        description="Constrained e-commerce visual asset generation service.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.service = service

    app.include_router(health.router)
    app.include_router(generate.router)
    app.include_router(tasks.router)

    # Serve generated artifacts (mock: .svg, real providers: .png) at /outputs.
    app.mount(
        "/outputs",
        StaticFiles(directory=service.config.output_dir, check_dir=False),
        name="outputs",
    )
    return app


def _build_default_app() -> FastAPI:
    """Module-level app for the ``uvicorn visual_studio.api.app:app`` target.

    ``python -m visual_studio`` is the canonical launcher; this exists so the
    common ``uvicorn <module>:app`` invocation also works without a factory arg.
    """
    from visual_studio.config import get_settings
    from visual_studio.service.generation_service import GenerationService

    return create_app(GenerationService(get_settings()))


app = _build_default_app()
