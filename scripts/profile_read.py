"""Profile the calendar read stages against a fresh in-memory SQLite database."""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()
from django.conf import settings

settings.DATABASES["default"]["NAME"] = ":memory:"
settings.ALLOWED_HOSTS.append("testserver")
from datetime import date

from django.core.management import call_command
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

from events.models import EventException, EventsSeries
from events.views import occurs_on

call_command("migrate", verbosity=0)
target = date(2026, 1, 1)
for count in (1000, 10000):
    EventsSeries.objects.all().delete()
    EventsSeries.objects.bulk_create(
        [
            EventsSeries(name=f"S{i}", start_at=datetime(2026, 1, 1, tzinfo=timezone.utc), period=7)
            for i in range(count)
        ],
        batch_size=1000,
    )
    with CaptureQueriesContext(connection) as queries:
        started = time.perf_counter()
        response = Client().get("/events/2026/1/1/")
        total_ms = (time.perf_counter() - started) * 1000
    started = time.perf_counter()
    with connection.cursor() as cursor:
        for query in queries:
            cursor.execute(query["sql"])
            cursor.fetchall()
    raw_sql_ms = (time.perf_counter() - started) * 1000
    started = time.perf_counter()
    exceptions = dict(
        (sid, (name, cancelled))
        for sid, name, cancelled in EventException.objects.filter(date=target).values_list(
            "series_id", "name", "is_cancelled"
        )
    )
    series = list(EventsSeries.objects.filter(start_at__date__lte=target).order_by("id"))
    fetch_ms = (time.perf_counter() - started) * 1000
    started = time.perf_counter()
    result = []
    for item in series:
        if not occurs_on(item, target):
            continue
        if item.id in exceptions:
            name, cancelled = exceptions[item.id]
            if cancelled:
                continue
            if name is not None:
                result.append({"name": name, "id": item.id})
                continue
        result.append({"name": item.name, "id": item.id})
    compute_ms = (time.perf_counter() - started) * 1000
    started = time.perf_counter()
    encoded = json.dumps(result).encode()
    json_ms = (time.perf_counter() - started) * 1000
    print(
        json.dumps(
            {
                "series": count,
                "sql_queries": len(queries),
                "events": len(result),
                "response_bytes": len(response.content),
                "total_ms": round(total_ms, 2),
                "raw_sql_fetch_ms": round(raw_sql_ms, 2),
                "sql_fetch_ms": round(fetch_ms, 2),
                "recurrence_ms": round(compute_ms, 2),
                "json_ms": round(json_ms, 2),
            },
            ensure_ascii=False,
        )
    )
