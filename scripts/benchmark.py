"""Run a disposable SQLite HTTP benchmark; prints one JSON record per scenario."""

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
START = 1767225600  # 2026-01-01 00:00 UTC


def request(base, method, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = Request(
        base + path, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    begin = time.perf_counter()
    try:
        with urlopen(req, timeout=60) as response:
            status = response.status
            body = response.read()
    except HTTPError as error:
        status = error.code
        body = error.read()
    except URLError, TimeoutError:
        status = 0
        body = b""
    latency = (time.perf_counter() - begin) * 1000
    events = len(json.loads(body)) if method == "GET" and status == 200 else None
    return (
        status,
        latency,
        b"database" in body.lower() and b"locked" in body.lower(),
        len(body),
        events,
    )


def percentile(values, percent):
    values = sorted(values)
    return round(values[min(len(values) - 1, int((len(values) - 1) * percent + 0.5))], 2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--long", action="store_true", help="60/30 requests per scenario instead of baseline 12/6"
    )
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="recurring-bench-") as tmp:
        target = Path(tmp)
        shutil.copy2(ROOT / "manage.py", target)
        shutil.copytree(
            ROOT / "config", target / "config", ignore=shutil.ignore_patterns("__pycache__")
        )
        shutil.copytree(
            ROOT / "events", target / "events", ignore=shutil.ignore_patterns("__pycache__")
        )

        def manage(*args):
            subprocess.run(
                [PYTHON, "manage.py", *args], cwd=target, check=True, stdout=subprocess.DEVNULL
            )

        manage("migrate", "--noinput")
        port = 18000 + os.getpid() % 10000
        base = f"http://127.0.0.1:{port}"
        server = subprocess.Popen(
            [PYTHON, "manage.py", "runserver", "--noreload", f"127.0.0.1:{port}"],
            cwd=target,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            for _ in range(100):
                if server.poll() is not None:
                    raise RuntimeError("server exited")
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                        break
                except OSError:
                    time.sleep(0.05)
            else:
                raise RuntimeError("server did not start")
            inserted = 0
            for size in (1000, 10000):
                seed = (
                    "from datetime import datetime, timezone; "
                    "from events.models import EventsSeries; "
                    f"EventsSeries.objects.bulk_create([EventsSeries(name='S'+str(i),start_at=datetime.fromtimestamp({START},timezone.utc),period=7) for i in range({size})], batch_size=1000)"
                )
                if size == 1000:
                    manage("shell", "-c", seed)
                else:
                    # Add 9,000 rows to the existing 1,000.
                    seed = seed.replace("range(10000)", "range(1000,10000)")
                    manage("shell", "-c", seed)
                for workers in (1, 4, 8):
                    for kind in ("read", "mixed"):
                        count = (
                            (30 if size == 10000 else 60)
                            if args.long
                            else (6 if size == 10000 else 12)
                        )
                        rows_before = size + inserted

                        def task(i):
                            if kind == "mixed" and i % 5 == 0:
                                return request(
                                    base,
                                    "POST",
                                    "/add/",
                                    {
                                        "name": f"new-{size}-{workers}-{i}",
                                        "start_at": START,
                                        "period": None,
                                    },
                                )
                            return request(base, "GET", "/events/2026/1/1/")

                        started = time.perf_counter()
                        with ThreadPoolExecutor(max_workers=workers) as pool:
                            results = list(pool.map(task, range(count)))
                        duration = time.perf_counter() - started
                        statuses = {}
                        for status, _, _, _, _ in results:
                            statuses[status] = statuses.get(status, 0) + 1
                        latencies = [latency for _, latency, _, _, _ in results]
                        read_counts = [
                            events for _, _, _, _, events in results if events is not None
                        ]
                        read_bytes = [
                            size_bytes for status, _, _, size_bytes, _ in results if status == 200
                        ]
                        print(
                            json.dumps(
                                {
                                    "series": size,
                                    "rows_before": rows_before,
                                    "kind": kind,
                                    "concurrency": workers,
                                    "requests": count,
                                    "duration_s": round(duration, 3),
                                    "rps": round(count / duration, 2),
                                    "p50_ms": percentile(latencies, 0.50),
                                    "p95_ms": percentile(latencies, 0.95),
                                    "p99_ms": percentile(latencies, 0.99),
                                    "statuses": statuses,
                                    "max_ms": round(max(latencies), 2),
                                    "read_events_min_max": [min(read_counts), max(read_counts)]
                                    if read_counts
                                    else None,
                                    "read_bytes_min_max": [min(read_bytes), max(read_bytes)]
                                    if read_bytes
                                    else None,
                                    "sqlite_locked": sum(locked for _, _, locked, _, _ in results),
                                },
                                ensure_ascii=False,
                            ),
                            flush=True,
                        )
                        if kind == "mixed":
                            inserted += sum(status == 201 for status, _, _, _, _ in results)
        finally:
            server.terminate()
            server.wait(timeout=5)


if __name__ == "__main__":
    main()
