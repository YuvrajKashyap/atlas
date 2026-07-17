import runpy

import pytest

import atlas.worker as worker


def test_worker_main_connects_all_stage_queues(monkeypatch: pytest.MonkeyPatch) -> None:
    redis = object()
    queue_names: list[str] = []
    work_calls: list[str] = []
    worker_names: list[str] = []

    class FakeQueue:
        def __init__(self, name: str, *, connection: object) -> None:
            assert connection is redis
            queue_names.append(name)

    class FakeWorker:
        __name__ = "FakeWorker"

        def __init__(self, queues: list[FakeQueue], *, connection: object, name: str) -> None:
            assert len(queues) == 3
            assert connection is redis
            worker_names.append(name)

        def work(self, *, logging_level: str) -> None:
            work_calls.append(logging_level)

    def redis_from_url(_url: str, **_kwargs: object) -> object:
        return redis

    monkeypatch.setattr(worker.Redis, "from_url", redis_from_url)
    monkeypatch.setattr(worker, "Queue", FakeQueue)
    monkeypatch.setattr(worker, "PlatformWorker", FakeWorker)
    monkeypatch.setattr(worker.socket, "gethostname", lambda: "container-a")
    monkeypatch.setattr(worker.os, "getpid", lambda: 1)

    worker.main()

    assert queue_names == ["atlas-fetch", "atlas-extract", "atlas-index"]
    assert worker_names == ["atlas-worker-container-a-1"]
    assert work_calls == ["INFO"]


def test_worker_name_differs_between_containers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(worker.os, "getpid", lambda: 1)
    monkeypatch.setattr(worker.socket, "gethostname", lambda: "container-a")
    first = worker.worker_name()

    monkeypatch.setattr(worker.socket, "gethostname", lambda: "container-b")

    assert first == "atlas-worker-container-a-1"
    assert worker.worker_name() == "atlas-worker-container-b-1"


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
