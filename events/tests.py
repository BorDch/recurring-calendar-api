import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from threading import Barrier
from unittest import skipUnless

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, TransactionTestCase, override_settings

from .models import EventException, EventsSeries


@override_settings(SECURE_SSL_REDIRECT=False)
class CalendarApiTests(TestCase):
    def setUp(self):
        if settings.CALENDAR_PROFILE != "local":
            self.user = get_user_model().objects.create_user(
                username="calendar", password="test-password"
            )
            self.client.force_login(self.user)

    def owner(self):
        return {"owner": self.user} if settings.CALENDAR_PROFILE != "local" else {}

    def post_json(self, path, data):
        return self.client.post(path, data=json.dumps(data), content_type="application/json")

    def test_local_wrong_method_returns_405_with_csrf_checks(self):
        if settings.CALENDAR_PROFILE != "local":
            self.skipTest("local API contract")
        csrf_client = Client(enforce_csrf_checks=True)
        self.assertEqual(csrf_client.post("/events/2026/11/9/").status_code, 405)
        self.assertEqual(
            csrf_client.post("/events/range/?start=2026-11-09&end=2026-11-09").status_code, 405
        )

    def test_calendar_page(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Календарь")
        self.assertContains(response, "Создать событие")

    def test_weekly_series_and_exceptions(self):
        start_at = int(datetime(2026, 11, 9, 9, tzinfo=timezone.utc).timestamp())
        response = self.post_json("/add/", {"name": "Смена", "start_at": start_at, "period": 7})
        self.assertEqual(response.status_code, 201)
        series_id = response.json()["id"]
        self.assertEqual(EventsSeries.objects.count(), 1)

        first = f"/events/2026/11/9/"
        second = f"/events/2026/11/16/"
        third = f"/events/2026/11/23/"
        fourth = f"/events/2026/11/30/"
        self.assertEqual(self.client.get(first).json(), [{"name": "Смена", "id": series_id}])
        self.assertEqual(self.client.get("/events/2026/11/10/").json(), [])
        self.assertEqual(self.client.get(second).json(), [{"name": "Смена", "id": series_id}])

        self.assertEqual(
            self.post_json(f"/update/{series_id}/2026/11/16/", {"name": "Новая смена"}).status_code,
            204,
        )
        self.assertEqual(self.client.get(second).json(), [{"name": "Новая смена", "id": series_id}])
        self.assertEqual(self.client.get(first).json(), [{"name": "Смена", "id": series_id}])

        self.assertEqual(self.client.post(f"/remove/{series_id}/2026/11/23/").status_code, 204)
        self.assertEqual(self.client.get(third).json(), [])
        self.assertEqual(self.client.post(f"/remove/{series_id}/2026/11/30/").status_code, 204)
        self.assertEqual(self.client.get(fourth).json(), [])
        self.assertEqual(self.client.post(f"/remove-next/{series_id}/2026/12/7/").status_code, 204)
        self.assertEqual(self.client.get("/events/2026/12/7/").json(), [])
        self.assertEqual(self.client.get("/events/2026/12/14/").json(), [])
        self.assertEqual(self.client.get(second).json(), [{"name": "Новая смена", "id": series_id}])
        self.assertEqual(EventException.objects.filter(series_id=series_id).count(), 3)

        self.assertEqual(self.client.post(f"/remove/{series_id}/2026/11/23/").status_code, 404)
        self.assertEqual(self.client.post(f"/remove-next/{series_id}/2026/12/7/").status_code, 404)
        self.assertEqual(
            self.post_json(f"/update/{series_id}/2026/11/10/", {"name": "Нет"}).status_code, 404
        )

    def test_single_event_and_bad_inputs(self):
        start_at = int(datetime(2026, 11, 9, tzinfo=timezone.utc).timestamp())
        payload = {"name": "Один раз", "start_at": start_at, "period": None}
        response = self.post_json("/add/", payload)
        self.assertEqual(response.status_code, 201)
        series_id = response.json()["id"]
        self.assertEqual(
            self.client.get("/events/2026/11/9/").json(), [{"name": "Один раз", "id": series_id}]
        )
        self.assertEqual(self.client.get("/events/2026/11/10/").json(), [])

        for period in (0, -1, True, False, 1.5, 2**63):
            self.assertEqual(self.post_json("/add/", payload | {"period": period}).status_code, 400)
        for timestamp in (True, False, "1", 10**100):
            self.assertEqual(
                self.post_json("/add/", payload | {"start_at": timestamp}).status_code, 400
            )
        self.assertEqual(
            self.client.post("/add/", data="{", content_type="application/json").status_code, 400
        )
        self.assertEqual(
            self.client.post("/add/", data="{", content_type="application/json").json(),
            {"error": "Invalid JSON"},
        )
        self.assertEqual(self.post_json("/update/1/2026/11/9/", {"name": True}).status_code, 400)
        self.assertEqual(self.client.get("/events/2026/2/30/").status_code, 400)
        self.assertEqual(self.client.get("/events/2026/no/1/").status_code, 400)
        self.assertEqual(self.client.post("/remove/1/2026/2/30/").status_code, 400)
        self.assertEqual(self.client.get("/add/").status_code, 405)
        self.assertEqual(self.client.post("/events/2026/11/9/").status_code, 405)

        daily_start = int(datetime(2026, 11, 9, 23, 30, tzinfo=timezone.utc).timestamp())
        daily = self.post_json(
            "/add/", {"name": "Каждый день", "start_at": daily_start, "period": 1}
        )
        self.assertEqual(daily.status_code, 201)
        self.assertEqual(
            self.client.get("/events/2026/11/10/").json(),
            [{"name": "Каждый день", "id": daily.json()["id"]}],
        )

    def test_calendar_boundaries_and_cutoff(self):
        start = int(datetime(2024, 2, 28, 23, 59, tzinfo=timezone.utc).timestamp())
        sid = self.post_json("/add/", {"name": "Leap", "start_at": start, "period": 1}).json()["id"]
        for path in ("2024/2/28", "2024/2/29", "2024/3/1", "2025/1/1"):
            self.assertEqual(
                self.client.get(f"/events/{path}/").json(), [{"name": "Leap", "id": sid}]
            )
        self.assertEqual(self.client.get("/events/2024/2/27/").json(), [])
        self.assertEqual(self.client.post(f"/remove-next/{sid}/2024/2/29/").status_code, 204)
        self.assertEqual(self.client.get("/events/2024/2/29/").json(), [])
        self.assertEqual(self.client.get("/events/2024/3/1/").json(), [])
        self.assertEqual(
            self.client.get("/events/2024/2/28/").json(), [{"name": "Leap", "id": sid}]
        )
        single = self.post_json(
            "/add/", {"name": "Single", "start_at": start, "period": None}
        ).json()["id"]
        self.assertIn(
            {"name": "Single", "id": single}, self.client.get("/events/2024/2/28/").json()
        )
        self.assertEqual(self.client.get("/events/2024/2/29/").json(), [])

    def test_invalid_requests_and_methods(self):
        payload = {"name": "A", "start_at": 1709164799, "period": 7}
        for malformed in ("{", "[]", "null"):
            self.assertEqual(
                self.client.post("/add/", malformed, content_type="application/json").status_code,
                400,
            )
        for field in payload:
            self.assertEqual(
                self.post_json(
                    "/add/", {k: v for k, v in payload.items() if k != field}
                ).status_code,
                400,
            )
        for field in ("start_at", "period"):
            self.assertEqual(self.post_json("/add/", payload | {field: True}).status_code, 400)
        self.assertEqual(self.post_json("/add/", payload | {"start_at": 10**100}).status_code, 400)
        sid = self.post_json("/add/", payload).json()["id"]
        for path in (
            "/events/2024/2/30/",
            f"/update/{sid}/2024/2/30/",
            f"/remove/{sid}/2024/2/30/",
            f"/remove-next/{sid}/2024/2/30/",
        ):
            method = self.client.get if path.startswith("/events/") else self.client.post
            self.assertEqual(method(path).status_code, 400)
        for prefix in ("update", "remove", "remove-next"):
            path = f"/{prefix}/999999/2024/2/28/"
            response = (
                self.post_json(path, {"name": "B"})
                if prefix == "update"
                else self.client.post(path)
            )
            self.assertEqual(response.status_code, 404)
        self.assertEqual(self.post_json(f"/update/{sid}/2024/2/28/", {}).status_code, 400)
        self.assertEqual(
            self.client.post(
                f"/update/{sid}/2024/2/28/", "{", content_type="application/json"
            ).status_code,
            400,
        )
        for path in (
            "/add/",
            f"/update/{sid}/2024/2/28/",
            f"/remove/{sid}/2024/2/28/",
            f"/remove-next/{sid}/2024/2/28/",
        ):
            self.assertEqual(self.client.get(path).status_code, 405)
        self.assertEqual(self.client.post("/events/2024/2/28/").status_code, 405)

    def test_state_changes_preserve_other_dates_and_series(self):
        stamp = int(datetime(2026, 12, 25, tzinfo=timezone.utc).timestamp())
        first = self.post_json("/add/", {"name": "A", "start_at": stamp, "period": 1}).json()["id"]
        other = self.post_json("/add/", {"name": "B", "start_at": stamp, "period": 1}).json()["id"]
        self.assertEqual(
            self.post_json(f"/update/{first}/2026/12/31/", {"name": "Changed"}).status_code, 204
        )
        self.assertEqual(self.client.post(f"/remove/{first}/2026/12/31/").status_code, 204)
        self.assertEqual(self.client.post(f"/remove/{first}/2026/12/31/").status_code, 404)
        self.assertEqual(
            self.client.get("/events/2026/12/31/").json(), [{"name": "B", "id": other}]
        )
        self.assertEqual(self.client.post(f"/remove-next/{first}/2027/1/3/").status_code, 204)
        self.assertEqual(self.client.post(f"/remove-next/{first}/2027/1/1/").status_code, 204)
        self.assertEqual(self.client.post(f"/remove-next/{first}/2027/1/4/").status_code, 404)
        self.assertEqual(EventsSeries.objects.get(pk=first).cutoff_date, date(2027, 1, 1))
        self.assertEqual(self.client.get("/events/2027/1/1/").json(), [{"name": "B", "id": other}])
        self.assertEqual(
            self.client.get("/events/2026/12/30/").json(),
            [{"name": "A", "id": first}, {"name": "B", "id": other}],
        )

    def test_day_read_uses_two_calendar_queries_with_exceptions(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        series = EventsSeries.objects.bulk_create(
            [
                EventsSeries(name=f"S{i}", start_at=start, period=7, **self.owner())
                for i in range(100)
            ]
        )
        target = date(2026, 1, 1)
        EventException.objects.create(series=series[0], date=target, name="Renamed")
        EventException.objects.create(series=series[1], date=target, is_cancelled=True)
        EventException.objects.create(series=series[2], date=target, name=None)
        with self.assertNumQueries(2 if settings.CALENDAR_PROFILE == "local" else 4):
            response = self.client.get("/events/2026/1/1/")
        self.assertEqual(response.status_code, 200)
        events = response.json()
        self.assertEqual(len(events), 99)
        self.assertEqual(events[0], {"name": "Renamed", "id": series[0].id})
        self.assertNotIn(series[1].id, [event["id"] for event in events])
        self.assertEqual(events[1], {"name": "S2", "id": series[2].id})
        self.assertEqual(events[-1], {"name": "S99", "id": series[-1].id})

    def test_range_month_boundary_utc_exceptions_and_cutoff(self):
        near_midnight = int(datetime(2024, 2, 29, 23, 55, tzinfo=timezone.utc).timestamp())
        sid = self.post_json(
            "/add/", {"name": "Leap", "start_at": near_midnight, "period": 1}
        ).json()["id"]
        other = self.post_json(
            "/add/", {"name": "Other", "start_at": near_midnight, "period": None}
        ).json()["id"]
        self.assertEqual(
            self.post_json(f"/update/{sid}/2024/3/1/", {"name": "Changed"}).status_code, 204
        )
        self.assertEqual(self.client.post(f"/remove/{sid}/2024/3/2/").status_code, 204)
        self.assertEqual(self.client.post(f"/remove-next/{sid}/2024/3/4/").status_code, 204)
        response = self.client.get("/events/range/?start=2024-02-28&end=2024-03-05")
        self.assertEqual(response.status_code, 200)
        days = {item["date"]: item["events"] for item in response.json()["days"]}
        self.assertEqual(days["2024-02-28"], [])
        self.assertEqual(
            days["2024-02-29"],
            [
                {"id": sid, "name": "Leap", "time": "23:55"},
                {"id": other, "name": "Other", "time": "23:55"},
            ],
        )
        self.assertEqual(days["2024-03-01"], [{"id": sid, "name": "Changed", "time": "23:55"}])
        self.assertEqual(days["2024-03-02"], [])
        self.assertEqual(days["2024-03-03"], [{"id": sid, "name": "Leap", "time": "23:55"}])
        self.assertEqual(days["2024-03-04"], [])
        self.assertEqual(days["2024-03-05"], [])

        # Day and range endpoints share occurrence visibility and exception handling.
        for day, range_events in days.items():
            year, month, date = map(int, day.split("-"))
            daily_events = self.client.get(f"/events/{year}/{month}/{date}/").json()
            self.assertEqual(
                daily_events,
                [{"id": event["id"], "name": event["name"]} for event in range_events],
            )

    def test_range_limit_validation_and_batch_queries(self):
        start = datetime(2026, 12, 31, 0, 5, tzinfo=timezone.utc)
        EventsSeries.objects.bulk_create(
            [
                EventsSeries(name=f"S{i}", start_at=start, period=7, **self.owner())
                for i in range(100)
            ]
        )
        with self.assertNumQueries(2 if settings.CALENDAR_PROFILE == "local" else 4):
            response = self.client.get("/events/range/?start=2026-12-28&end=2027-02-07")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["days"]), 42)
        self.assertEqual(len(response.json()["days"][3]["events"]), 100)
        self.assertEqual(response.json()["days"][3]["events"][0]["time"], "00:05")
        for query in (
            "start=2026-12-28&end=2027-02-08",
            "start=2027-01-02&end=2027-01-01",
            "start=2026-02-30&end=2026-03-01",
            "start=2026-01-01",
            "start=2026-01-01&end=2026-01-02&extra=1",
            "start=20260101&end=2026-01-02",
            "start=2026-01-01&start=2026-01-02&end=2026-01-03",
        ):
            self.assertEqual(self.client.get("/events/range/?" + query).status_code, 400)
        self.assertEqual(
            self.client.post("/events/range/?start=2026-01-01&end=2026-01-02").status_code, 405
        )


@skipUnless(settings.CALENDAR_PROFILE == "local", "local API contract")
class ConcurrentApiTests(TransactionTestCase):
    def concurrent(self, actions):
        barrier = Barrier(len(actions))

        def run(action):
            barrier.wait(timeout=5)
            return action(Client())

        with ThreadPoolExecutor(max_workers=len(actions)) as pool:
            futures = [pool.submit(run, action) for action in actions]
            return [future.result(timeout=10) for future in futures]

    def test_update_and_remove_same_date(self):
        series = EventsSeries.objects.create(
            name="A", start_at=datetime(2026, 1, 1, tzinfo=timezone.utc), period=1
        )
        path = f"/{series.id}/2026/1/2/"
        statuses = self.concurrent(
            [
                lambda c: (
                    c.post(
                        "/update" + path,
                        json.dumps({"name": "Changed"}),
                        content_type="application/json",
                    ).status_code
                ),
                lambda c: c.post("/remove" + path).status_code,
            ]
        )
        self.assertIn(sorted(statuses), ([204, 204], [204, 404]))
        self.assertTrue(
            EventException.objects.get(series=series, date=date(2026, 1, 2)).is_cancelled
        )
        self.assertEqual(self.client.get("/events/2026/1/2/").json(), [])

    def test_two_cutoffs_and_parallel_creates(self):
        series = EventsSeries.objects.create(
            name="A", start_at=datetime(2026, 1, 1, tzinfo=timezone.utc), period=1
        )
        statuses = self.concurrent(
            [
                lambda c: c.post(f"/remove-next/{series.id}/2026/1/3/").status_code,
                lambda c: c.post(f"/remove-next/{series.id}/2026/1/5/").status_code,
            ]
        )
        self.assertTrue(all(status in (204, 404) for status in statuses))
        self.assertEqual(EventsSeries.objects.get(pk=series.id).cutoff_date, date(2026, 1, 3))
        self.assertEqual(self.client.get("/events/2026/1/5/").json(), [])
        creates = self.concurrent(
            [
                lambda c, i=i: (
                    c.post(
                        "/add/",
                        json.dumps({"name": str(i), "start_at": 1767225600, "period": None}),
                        content_type="application/json",
                    ).status_code
                )
                for i in range(4)
            ]
        )
        self.assertEqual(creates, [201] * 4)
        self.assertEqual(EventsSeries.objects.count(), 5)
