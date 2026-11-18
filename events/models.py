from django.conf import settings
from django.db import models


class EventsSeries(models.Model):
    """One stored rule whose UTC occurrences share a single public ID."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="event_series",
    )
    name = models.TextField()
    start_at = models.DateTimeField()
    period = models.BigIntegerField(null=True, blank=True)
    # "Remove this and following" excludes the chosen date too: first excluded UTC date.
    cutoff_date = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(period__isnull=True)
                | (models.Q(period__gte=1) & models.Q(period__lte=2**63 - 1)),
                name="event_series_period_null_or_positive",
            ),
        ]


class EventException(models.Model):
    """A rename or cancellation for one occurrence of a series."""

    series = models.ForeignKey(EventsSeries, on_delete=models.CASCADE, related_name="exceptions")
    date = models.DateField()
    name = models.TextField(null=True, blank=True)
    is_cancelled = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["series", "date"], name="unique_series_exception_date"),
        ]
