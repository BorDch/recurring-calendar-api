"""Ordering-sensitive write tests, run only against a real PostgreSQL connection."""
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from threading import Event
from unittest import skipUnless

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection, transaction, close_old_connections
from django.test import Client, TransactionTestCase, override_settings

from .models import EventException, EventsSeries


@skipUnless(settings.CALENDAR_PROFILE == 'production', 'PostgreSQL production only')
@override_settings(SECURE_SSL_REDIRECT=False)
class PostgreSQLConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='writer', password='test-password')
        self.series = EventsSeries.objects.create(owner=self.user, name='A',
            start_at=datetime(2026, 1, 1, tzinfo=timezone.utc), period=1)

    def ordered_write(self, first, second):
        """Hold the series row until PostgreSQL confirms the other connection waits on it."""
        started = Event()
        worker_pid = []
        def worker():
            close_old_connections()
            connection.ensure_connection()
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '8s'")
                cursor.execute("SET statement_timeout = '10s'")
            pid = connection.connection.info.backend_pid
            worker_pid.append(pid)
            started.set()
            client = Client()
            client.force_login(self.user)
            try:
                return pid, second(client)
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                EventsSeries.objects.select_for_update().get(pk=self.series.pk)
                first()
                future = pool.submit(worker)
                self.assertTrue(started.wait(5))
                # The worker reports its backend PID through pg_stat_activity;
                # wait until its request is blocked on the held row lock.
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT count(*) FROM pg_stat_activity WHERE pid = %s AND wait_event_type = 'Lock'", [worker_pid[0]])
                        if cursor.fetchone()[0]:
                            break
                    time.sleep(.01)
                else:
                    self.fail('second connection did not wait for the row lock')
            return future.result(timeout=12)[1]

    def test_cancel_then_rename_cannot_restore_occurrence(self):
        target = date(2026, 1, 2)
        def cancel():
            EventException.objects.create(series=self.series, date=target, is_cancelled=True)
        status = self.ordered_write(cancel, lambda c: c.post(
            f'/update/{self.series.pk}/2026/1/2/', json.dumps({'name': 'Renamed'}),
            content_type='application/json').status_code)
        self.assertEqual(status, 404)
        self.assertTrue(EventException.objects.get(series=self.series, date=target).is_cancelled)

    def test_later_cutoff_cannot_restore_earlier_cutoff(self):
        def earlier_cutoff():
            self.series.cutoff_date = date(2026, 1, 3)
            self.series.save(update_fields=['cutoff_date'])
        status = self.ordered_write(earlier_cutoff, lambda c: c.post(
            f'/remove-next/{self.series.pk}/2026/1/5/').status_code)
        self.assertEqual(status, 404)
        self.series.refresh_from_db()
        self.assertEqual(self.series.cutoff_date, date(2026, 1, 3))

    def test_existing_exception_is_serialized_with_cancel(self):
        target = date(2026, 1, 2)
        def rename():
            EventException.objects.create(series=self.series, date=target, name='Renamed')
        status = self.ordered_write(rename, lambda c: c.post(
            f'/remove/{self.series.pk}/2026/1/2/').status_code)
        self.assertEqual(status, 204)
        self.assertEqual(EventException.objects.filter(series=self.series, date=target).count(), 1)
        self.assertTrue(EventException.objects.get(series=self.series, date=target).is_cancelled)
