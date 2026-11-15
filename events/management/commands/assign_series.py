from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from events.models import EventsSeries


class Command(BaseCommand):
    help = 'Preview or assign selected unowned series to a user.'

    def add_arguments(self, parser):
        parser.add_argument('username')
        parser.add_argument('ids', nargs='+', type=int)
        parser.add_argument('--apply', action='store_true', help='Write the assignments')

    def handle(self, username, ids, apply, **options):
        try:
            user = get_user_model().objects.get(username=username)
        except get_user_model().DoesNotExist as exc:
            raise CommandError('Unknown user') from exc
        ids = set(ids)
        series = list(EventsSeries.objects.filter(pk__in=ids).order_by('pk'))
        if len(series) != len(ids):
            raise CommandError('Some series do not exist')
        if any(item.owner_id is not None for item in series):
            raise CommandError('All selected series must be unowned')
        for item in series:
            self.stdout.write(f'{item.pk}: {item.name} -> {user.username}')
        if apply:
            with transaction.atomic():
                updated = EventsSeries.objects.filter(pk__in=ids, owner__isnull=True).update(owner=user)
                if updated != len(ids):
                    raise CommandError('Some series were assigned concurrently; no assignments saved')
            self.stdout.write(self.style.SUCCESS(f'Assigned {updated} series'))
        else:
            self.stdout.write('Preview only; add --apply to assign')
