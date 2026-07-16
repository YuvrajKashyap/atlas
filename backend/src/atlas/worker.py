import os

import structlog
from redis import Redis
from rq import Queue

if os.name == "nt":
    from rq.worker import SpawnWorker as PlatformWorker
else:
    from rq.worker import Worker as PlatformWorker

from atlas.config import get_settings
from atlas.logging import configure_logging


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    redis = Redis.from_url(settings.redis_url)
    queue = Queue("atlas-fetch", connection=redis)
    worker = PlatformWorker([queue], connection=redis, name=f"atlas-worker-{os.getpid()}")
    structlog.get_logger(__name__).info("worker_started", worker_class=PlatformWorker.__name__)
    worker.work(logging_level=settings.log_level)


if __name__ == "__main__":
    main()
