import json
import sys
from pathlib import Path
from typing import Any, cast

OVERALL_MINIMUM = 85.0
CRITICAL_MINIMUMS = {
    "src/atlas/scheduler.py": 90.0,
    "src/atlas/worker.py": 90.0,
    "src/atlas/jobs.py": 90.0,
    "src/atlas/fetcher.py": 90.0,
    "src/atlas/robots.py": 90.0,
    "src/atlas/tasking.py": 90.0,
    "src/atlas/indexer.py": 90.0,
}


def _percent(summary: dict[str, object]) -> float:
    return float(cast(float | int, summary["percent_covered"]))


def main() -> None:
    report_path = Path(sys.argv[1] if len(sys.argv) > 1 else "coverage.json")
    report = cast(dict[str, Any], json.loads(report_path.read_text(encoding="utf-8")))
    failures: list[str] = []
    overall = _percent(cast(dict[str, object], report["totals"]))
    if overall < OVERALL_MINIMUM:
        failures.append(f"overall coverage {overall:.2f}% is below {OVERALL_MINIMUM:.0f}%")

    files = cast(dict[str, Any], report["files"])
    normalized = {name.replace("\\", "/"): value for name, value in files.items()}
    for suffix, minimum in CRITICAL_MINIMUMS.items():
        match = next((value for name, value in normalized.items() if name.endswith(suffix)), None)
        if match is None:
            failures.append(f"critical module is absent from coverage: {suffix}")
            continue
        covered = _percent(cast(dict[str, object], match["summary"]))
        if covered < minimum:
            failures.append(f"{suffix} coverage {covered:.2f}% is below {minimum:.0f}%")

    if failures:
        raise SystemExit("Coverage gate failed:\n- " + "\n- ".join(failures))
    print(f"Coverage gate passed: overall {overall:.2f}%, critical modules >= 90%")


if __name__ == "__main__":
    main()
