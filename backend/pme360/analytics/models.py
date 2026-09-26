from django.db import models


class AnalyticsRefresh(models.Model):
    """Fraîcheur des vues analytiques (table technique, sans donnée métier ni tenant)."""

    view = models.CharField(max_length=60, unique=True)
    refreshed_at = models.DateTimeField()
    duration_ms = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "analytics_refresh"

    def __str__(self) -> str:
        return self.view
