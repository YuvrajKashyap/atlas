import importlib
import os
import socket

import structlog
from redis import Redis
from rq import Queue

if os.name == "nt":
    from rq.worker import SpawnWorker as PlatformWorker
else:
    from rq.worker import RoundRobinWorker as PlatformWorker

from atlas.config import get_settings
from atlas.logging import configure_logging


def worker_name() -> str:
    """Return an RQ identity that is unique across processes and containers."""
    return f"atlas-worker-{socket.gethostname()}-{os.getpid()}"


def preload_job_modules() -> None:
    """Load heavy job dependencies once in the parent before RQ forks work horses."""
    importlib.import_module("atlas.jobs")


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    preload_job_modules()
    redis = Redis.from_url(settings.redis_url, password=settings.redis_password or None)
    queues = [
        Queue("atlas-fetch", connection=redis),
        Queue("atlas-extract", connection=redis),
        Queue("atlas-index", connection=redis),
    ]
    worker = PlatformWorker(queues, connection=redis, name=worker_name())
    structlog.get_logger(__name__).info("worker_started", worker_class=PlatformWorker.__name__)
    worker.work(logging_level=settings.log_level)


if __name__ == "__main__":
    main()
