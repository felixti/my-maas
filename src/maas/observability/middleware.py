from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import openlit
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

if TYPE_CHECKING:
    from fastapi import FastAPI

    from maas.config import Settings

logger = logging.getLogger(__name__)


def setup_instrumentation(app: FastAPI, settings: Settings) -> None:
    try:
        FastAPIInstrumentor.instrument_app(app)
    except Exception:
        logger.exception("Failed to instrument FastAPI with OpenTelemetry")

    try:
        openlit.init(
            otlp_endpoint=settings.otel_exporter_otlp_endpoint,
            application_name=settings.otel_service_name,
            disable_batch=False,
        )
    except Exception:
        logger.exception("Failed to initialize OpenLIT instrumentation")
