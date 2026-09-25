"""Snapshots de score (Document 3, § 3.4 ; Document 6). Un snapshot figé est immuable (trigger PostgreSQL)."""

from django.db import models

from pme360.core.models import TenantModel


class ScoreSnapshot(TenantModel):
    class Kind(models.TextChoices):
        BASELINE = "BASELINE", "Référence (diagnostic initial)"
        FOLLOW_UP = "FOLLOW_UP", "Suivi"
        CLOTURE = "CLOTURE", "Clôture"
        LIVE = "LIVE", "Score courant"

    pme = models.ForeignKey("pmes.Pme", on_delete=models.PROTECT, related_name="snapshots")
    diagnostic = models.OneToOneField(
        "diagnostic.Diagnostic", null=True, blank=True, on_delete=models.PROTECT, related_name="snapshot"
    )
    framework_version = models.ForeignKey("diagnostic.FrameworkVersion", on_delete=models.PROTECT, related_name="+")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    reference_date = models.DateField()
    computed_at = models.DateTimeField()
    engine_version = models.CharField(max_length=20)
    global_score = models.DecimalField(max_digits=5, decimal_places=1, null=True)
    imo = models.DecimalField("indice de maturité organisationnelle", max_digits=5, decimal_places=1, null=True)
    ipe = models.DecimalField("indice de performance économique", max_digits=5, decimal_places=1, null=True)
    risk_index = models.DecimalField(max_digits=5, decimal_places=1, null=True)
    digital_index = models.DecimalField(max_digits=5, decimal_places=1, null=True)
    confidence = models.DecimalField(max_digits=4, decimal_places=3)
    maturity_level = models.PositiveSmallIntegerField(null=True)
    maturity_level_uncapped = models.PositiveSmallIntegerField(null=True)
    gates_failed = models.JSONField(default=list)
    intervention_priority = models.CharField(max_length=2, blank=True)
    quadrant = models.CharField(max_length=30, blank=True)
    is_frozen = models.BooleanField(default=True)
    result = models.JSONField(default=dict, help_text="Résultat complet du moteur (explicabilité).")

    class Meta:
        db_table = "score_snapshot"
        ordering = ["-reference_date", "-computed_at"]
        indexes = [models.Index(fields=["organization", "pme", "reference_date"], name="snapshot_pme_idx")]

    def __str__(self) -> str:
        return f"{self.kind} {self.reference_date} : {self.global_score}"


class ScoreItem(TenantModel):
    class Scope(models.TextChoices):
        PILLAR = "PILLAR", "Pilier"
        DIMENSION = "DIMENSION", "Dimension"
        CRITERION = "CRITERION", "Critère"
        LENS = "LENS", "Lentille"

    snapshot = models.ForeignKey(ScoreSnapshot, on_delete=models.CASCADE, related_name="items")
    scope = models.CharField(max_length=10, choices=Scope.choices)
    ref_code = models.CharField(max_length=40)
    score = models.DecimalField(max_digits=5, decimal_places=1, null=True)
    confidence = models.DecimalField(max_digits=4, decimal_places=3, null=True)
    status = models.CharField(max_length=16)
    details = models.JSONField(default=dict)

    class Meta:
        db_table = "score_item"
        constraints = [models.UniqueConstraint(fields=["snapshot", "scope", "ref_code"], name="score_item_unique")]


class MetricValue(TenantModel):
    snapshot = models.ForeignKey(ScoreSnapshot, on_delete=models.CASCADE, related_name="metric_values")
    metric_code = models.CharField(max_length=40)
    value = models.DecimalField(max_digits=20, decimal_places=6, null=True)
    points = models.PositiveSmallIntegerField(null=True)
    band_label = models.CharField(max_length=60, blank=True)
    inputs_used = models.JSONField(default=dict)
    sources = models.JSONField(default=list)

    class Meta:
        db_table = "metric_value"
        constraints = [models.UniqueConstraint(fields=["snapshot", "metric_code"], name="metric_value_unique")]
