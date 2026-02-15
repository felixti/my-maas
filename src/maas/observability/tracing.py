from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

if TYPE_CHECKING:
    from maas.config import Settings

logger = logging.getLogger(__name__)


def setup_tracing(settings: Settings) -> None:
    try:
        resource = Resource.create({"service.name": settings.otel_service_name})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(
            endpoint=f"{settings.otel_exporter_otlp_endpoint}/v1/traces",
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
    except Exception:
        logger.exception("Failed to initialize OpenTelemetry tracing")


def shutdown_tracing() -> None:
    try:
        provider = trace.get_tracer_provider()
        if isinstance(provider, TracerProvider):
            provider.shutdown()
    except Exception:
        logger.exception("Failed to shutdown OpenTelemetry tracing")
