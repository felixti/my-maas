from __future__ import annotations

import builtins
import importlib
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI

from maas import config
from maas.dependencies import lifespan_resources
from maas.observability.middleware import setup_instrumentation
from maas.observability.tracing import setup_tracing, shutdown_tracing

builtins.importlib = importlib

_cached_get_settings = config.get_settings


def get_settings() -> config.Settings:
    if lifespan_resources.settings is not None:
        return lifespan_resources.settings
    return _cached_get_settings()


config.get_settings = get_settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    setup_tracing(settings)
    await lifespan_resources.startup()
    yield
    await lifespan_resources.shutdown()
    shutdown_tracing()


def create_app() -> FastAPI:
    from maas.ltm.router import router as ltm_router
    from maas.stm.router import router as stm_router

    app = FastAPI(
        title="Memory as a Service",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(stm_router, prefix="/stm", tags=["STM"])
    app.include_router(ltm_router, prefix="/ltm", tags=["LTM"])

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    setup_instrumentation(app, get_settings())

    return app


app = create_app()
