from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from atlas.config import Settings


def configure_telemetry(settings: Settings) -> None:
    if not settings.otlp_endpoint:
        return
    provider = TracerProvider(
        resource=Resource.create(
            {
                SERVICE_NAME: "atlas-api",
                SERVICE_VERSION: "0.2.0",
                "deployment.environment": settings.environment,
            }
        )
    )
    exporter = OTLPSpanExporter(endpoint=settings.otlp_endpoint)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
