import json
from datetime import datetime, timezone
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.conf import settings
from unittest import skipUnless
from io import StringIO
from django.core.management import call_command
from .models import EventException, EventsSeries


@skipUnless(settings.CALENDAR_PROFILE in ('private', 'production'), 'authenticated profile only')
@override_settings(SECURE_SSL_REDIRECT=False)
class PrivateCalendarTests(TestCase):
    def test_two_users_csrf_logout_and_ownership(self):
        users = [get_user_model().objects.create_user(username=name, password='long-test-password') for name in ('alice', 'bob')]
        alice, bob = (Client(enforce_csrf_checks=True) for _ in users)
        self.assertEqual(alice.get('/').status_code, 302)
        self.assertEqual(alice.get('/events/2026/11/9/').status_code, 302)
        for client, user in zip((alice, bob), users):
            login = client.get('/login/')
            self.assertEqual(login.status_code, 200)
            self.assertEqual(client.post('/login/', {'username': user.username, 'password': 'long-test-password', 'csrfmiddlewaretoken': client.cookies['csrftoken'].value}).status_code, 302)
        payload = json.dumps({'name': 'Private', 'start_at': int(datetime(2026, 11, 9, tzinfo=timezone.utc).timestamp()), 'period': 7})
        self.assertEqual(alice.post('/add/', payload, content_type='application/json').status_code, 403)
        token = alice.cookies['csrftoken'].value
        created = alice.post('/add/', payload, content_type='application/json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(created.status_code, 201)
        series = EventsSeries.objects.get(pk=created.json()['id'])
        self.assertEqual(series.owner, users[0])
        legacy = EventsSeries.objects.create(name='Legacy', start_at=series.start_at, period=7)
        EventException.objects.create(series=legacy, date=datetime(2026, 11, 16).date(), name='Changed')
        bob_created = bob.post('/add/', payload.replace('Private', 'Bob event'), content_type='application/json', HTTP_X_CSRFTOKEN=bob.cookies['csrftoken'].value)
        self.assertEqual(bob_created.status_code, 201)
        bob_id = bob_created.json()['id']
        self.assertEqual([item['id'] for item in alice.get('/events/2026/11/9/').json()], [series.id])
        self.assertEqual([item['id'] for item in bob.get('/events/2026/11/9/').json()], [bob_id])
        self.assertEqual([item['id'] for item in alice.get('/events/range/?start=2026-11-09&end=2026-11-16').json()['days'][0]['events']], [series.id])
        self.assertEqual([item['id'] for item in bob.get('/events/range/?start=2026-11-09&end=2026-11-16').json()['days'][0]['events']], [bob_id])
        before = (series.name, series.cutoff_date, list(series.exceptions.values_list('date', 'name', 'is_cancelled')))
        for path in ('update', 'remove', 'remove-next'):
            response = bob.post(f'/{path}/{series.id}/2026/11/9/', json.dumps({'name':'Other'}), content_type='application/json', HTTP_X_CSRFTOKEN=bob.cookies['csrftoken'].value)
            self.assertEqual(response.status_code, 404)
        series.refresh_from_db()
        self.assertEqual((series.name, series.cutoff_date, list(series.exceptions.values_list('date', 'name', 'is_cancelled'))), before)
        self.assertEqual(alice.get('/events/2026/11/9/').json(), [{'id': series.id, 'name': 'Private'}])
        self.assertEqual(alice.post(f'/update/{series.id}/2026/11/9/', json.dumps({'name': 'No CSRF'}), content_type='application/json').status_code, 403)
        self.assertEqual(alice.get('/events/2026/11/9/').json(), [{'id': series.id, 'name': 'Private'}])
        self.assertEqual(legacy.owner_id, None)
        output = StringIO()
        call_command('assign_series', 'alice', legacy.id, stdout=output)
        legacy.refresh_from_db()
        self.assertIsNone(legacy.owner_id)
        self.assertNotIn(legacy.id, [item['id'] for item in alice.get('/events/2026/11/9/').json()])
        call_command('assign_series', 'alice', legacy.id, '--apply', stdout=StringIO())
        legacy.refresh_from_db()
        self.assertEqual(legacy.owner, users[0])
        self.assertIn(legacy.id, [item['id'] for item in alice.get('/events/2026/11/9/').json()])
        self.assertNotIn(legacy.id, [item['id'] for item in bob.get('/events/2026/11/9/').json()])
        self.assertEqual(alice.post('/logout/', HTTP_X_CSRFTOKEN=token).status_code, 302)
        self.assertEqual(alice.get('/').status_code, 302)
        self.assertEqual(alice.get('/events/range/?start=2026-11-09&end=2026-11-16').status_code, 302)
