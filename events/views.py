import json
import re
import time
from datetime import date, datetime, timedelta, timezone
from functools import wraps

from django.db import OperationalError, transaction
from django.db.models import F
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import EventException, EventsSeries


def request_date(year, month, day):
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


def occurs_on(series, target):
    start_date = series.start_at.astimezone(timezone.utc).date()
    days_since_start = (target - start_date).days
    if days_since_start < 0 or (series.cutoff_date is not None and target >= series.cutoff_date):
        return False
    if series.period is None:
        return days_since_start == 0
    return days_since_start % series.period == 0


def visible_on(series, target):
    if not occurs_on(series, target):
        return False
    return not EventException.objects.filter(series=series, date=target, is_cancelled=True).exists()


def json_body(request):
    return json.loads(request.body)


def retry_locked(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        for attempt in range(20):
            try:
                return view(*args, **kwargs)
            except OperationalError as error:
                if "locked" not in str(error).lower() or attempt == 19:
                    raise
                time.sleep(0.01 * (attempt + 1))
    return wrapped


def lock_series(series_id):
    # SQLite obtains its writer lock before checking visibility; retries cover busy writers.
    EventsSeries.objects.filter(pk=series_id).update(name=F("name"))
    return get_object_or_404(EventsSeries, pk=series_id)


@require_GET
def calendar_home(request):
    return render(request, "events/calendar.html")


@require_GET
def events_range(request):
    if (set(request.GET) != {"start", "end"}
            or any(len(request.GET.getlist(field)) != 1 for field in ("start", "end"))
            or any(not re.fullmatch(r"\d{4}-\d{2}-\d{2}", request.GET[field])
                   for field in ("start", "end"))):
        return JsonResponse({"error": "Invalid range"}, status=400)
    try:
        start = date.fromisoformat(request.GET["start"])
        end = date.fromisoformat(request.GET["end"])
    except ValueError:
        return JsonResponse({"error": "Invalid range"}, status=400)
    days = (end - start).days + 1
    if not 1 <= days <= 42:
        return JsonResponse({"error": "Range must contain 1 to 42 days"}, status=400)

    result = {start + timedelta(days=offset): [] for offset in range(days)}
    exceptions = {
        (series_id, exception_date): (name, is_cancelled)
        for series_id, exception_date, name, is_cancelled in EventException.objects.filter(
            date__range=(start, end)
        ).values_list("series_id", "date", "name", "is_cancelled")
    }
    for series in EventsSeries.objects.filter(start_at__date__lte=end).order_by("id"):
        utc_time = series.start_at.astimezone(timezone.utc).strftime("%H:%M")
        for target in result:
            if not occurs_on(series, target):
                continue
            exception = exceptions.get((series.id, target))
            if exception is not None:
                name, is_cancelled = exception
                if is_cancelled:
                    continue
            else:
                name = None
            result[target].append({"id": series.id, "name": series.name if name is None else name,
                                   "time": utc_time})
    return JsonResponse({"days": [{"date": day.isoformat(), "events": events}
                                  for day, events in result.items()]})


@retry_locked
@csrf_exempt
@require_POST
def add_event(request):
    try:
        data = json_body(request)
    except ValueError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    if not isinstance(data, dict) or set(data) != {"name", "start_at", "period"}:
        return JsonResponse({"error": "Invalid fields"}, status=400)

    name, start_at, period = data["name"], data["start_at"], data["period"]
    if type(name) is not str or type(start_at) is not int:
        return JsonResponse({"error": "Invalid fields"}, status=400)
    if period is not None and (type(period) is not int or not 1 <= period <= 2**63 - 1):
        return JsonResponse({"error": "Invalid period"}, status=400)
    try:
        start_datetime = datetime.fromtimestamp(start_at, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return JsonResponse({"error": "Invalid timestamp"}, status=400)

    series = EventsSeries.objects.create(name=name, start_at=start_datetime, period=period)
    return JsonResponse({"id": series.id}, status=201)


@require_GET
def events_on_date(request, year, month, day):
    target = request_date(year, month, day)
    if target is None:
        return JsonResponse({"error": "Invalid date"}, status=400)

    exceptions = {
        series_id: (name, is_cancelled)
        for series_id, name, is_cancelled in EventException.objects.filter(date=target).values_list(
            "series_id", "name", "is_cancelled"
        )
    }
    result = []
    for series in EventsSeries.objects.filter(start_at__date__lte=target).order_by("id"):
        if not occurs_on(series, target):
            continue
        if series.id in exceptions:
            name, is_cancelled = exceptions[series.id]
            if is_cancelled:
                continue
            if name is not None:
                result.append({"name": name, "id": series.id})
                continue
        result.append({"name": series.name, "id": series.id})
    return JsonResponse(result, safe=False)


@retry_locked
@csrf_exempt
@require_POST
@transaction.atomic
def update_event(request, id, year, month, day):
    target = request_date(year, month, day)
    if target is None:
        return JsonResponse({"error": "Invalid date"}, status=400)
    try:
        data = json_body(request)
    except ValueError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    if not isinstance(data, dict) or set(data) != {"name"} or type(data["name"]) is not str:
        return JsonResponse({"error": "Invalid fields"}, status=400)

    series = lock_series(id)
    if not visible_on(series, target):
        return HttpResponse(status=404)
    EventException.objects.update_or_create(
        series=series, date=target, defaults={"name": data["name"], "is_cancelled": False}
    )
    return HttpResponse(status=204)


@retry_locked
@csrf_exempt
@require_POST
@transaction.atomic
def remove_event(request, id, year, month, day):
    target = request_date(year, month, day)
    if target is None:
        return JsonResponse({"error": "Invalid date"}, status=400)
    series = lock_series(id)
    if not visible_on(series, target):
        return HttpResponse(status=404)
    EventException.objects.update_or_create(
        series=series, date=target, defaults={"name": None, "is_cancelled": True}
    )
    return HttpResponse(status=204)


@retry_locked
@csrf_exempt
@require_POST
@transaction.atomic
def remove_next(request, id, year, month, day):
    target = request_date(year, month, day)
    if target is None:
        return JsonResponse({"error": "Invalid date"}, status=400)
    series = lock_series(id)
    if not visible_on(series, target):
        return HttpResponse(status=404)
    series.cutoff_date = target
    series.save(update_fields=["cutoff_date"])
    return HttpResponse(status=204)
