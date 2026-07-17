import runpy

import pytest

import atlas.worker as worker


def test_worker_main_connects_all_stage_queues(monkeypatch: pytest.MonkeyPatch) -> None:
    redis = object()
    queue_names: list[str] = []
    work_calls: list[str] = []

    class FakeQueue:
        def __init__(self, name: str, *, connection: object) -> None:
            assert connection is redis
            queue_names.append(name)

    class FakeWorker:
        __name__ = "FakeWorker"

        def __init__(self, queues: list[FakeQueue], *, connection: object, name: str) -> None:
            assert len(queues) == 3
            assert connection is redis
            assert name.startswith("atlas-worker-")

        def work(self, *, logging_level: str) -> None:
            work_calls.append(logging_level)

    def redis_from_url(_url: str, **_kwargs: object) -> object:
        return redis

    monkeypatch.setattr(worker.Redis, "from_url", redis_from_url)
    monkeypatch.setattr(worker, "Queue", FakeQueue)
    monkeypatch.setattr(worker, "PlatformWorker", FakeWorker)

    worker.main()

    assert queue_names == ["atlas-fetch", "atlas-extract", "atlas-index"]
    assert work_calls == ["INFO"]


def test_worker_module_entrypoint(monkeypatch: pytest.MonkeyPatch) -> None:
    redis = object()

    class CliQueue:
        def __init__(self, _name: str, *, connection: object) -> None:
            assert connection is redis

    class CliWorker:
        def __init__(self, _queues: list[CliQueue], *, connection: object, name: str) -> None:
            assert connection is redis
            assert name.startswith("atlas-worker-")

        def work(self, *, logging_level: str) -> None:
            assert logging_level == "INFO"

    def redis_from_url(_url: str, **_kwargs: object) -> object:
        return redis

    monkeypatch.setattr("redis.Redis.from_url", redis_from_url)
    monkeypatch.setattr("rq.Queue", CliQueue)
    monkeypatch.setattr("rq.worker.SpawnWorker", CliWorker)
    monkeypatch.setattr("rq.worker.Worker", CliWorker)

    runpy.run_module("atlas.worker", run_name="__main__")
