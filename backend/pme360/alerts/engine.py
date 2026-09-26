"""Évaluation des alertes (Document 7, § 8).

Chaque règle ACTIVE de l'organisation est évaluée pour une PME ; ses seuils viennent de ``AlertRule.params``.
Une alerte est dédoublonnée par (règle, clé) et RÉSOLUE AUTOMATIQUEMENT quand sa condition disparaît.
Les libellés décrivent une évolution des données, jamais une cause ni une accusation (Document 7, § 8.2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from django.utils import timezone

from pme360.audit import services as audit
from pme360.compliance.models import Deadline
from pme360.documents.models import Document
from pme360.notifications import services as notifications
from pme360.pmes.models import Pme
from pme360.scoring.models import ScoreSnapshot

from .models import Alert, AlertRule

SEVERITY_ORDER = ["INFO", "MOYENNE", "ELEVEE", "CRITIQUE"]


@dataclass
class Finding:
    key: str
    title: str
    message: str
    severity: str | None = None
    target_type: str = ""
    target_id: str = ""
    details: dict = field(default_factory=dict)


# --- Conditions par type de règle ------------------------------------------------------------------------------


def _doc_expire(rule: AlertRule, pme: Pme, today: date) -> list[Finding]:
    notice = timedelta(days=rule.params.get("notice_days", 30))
    findings = []
    for document in Document.objects.filter(
        pme=pme,
        deleted_at__isnull=True,
        expires_at__isnull=False,
        conformity_status__in=[Document.Conformity.CONFORME, Document.Conformity.CONFORME_SOUS_RESERVE],
    ):
        newer = Document.objects.filter(
            pme=pme, document_type=document.document_type, created_at__gt=document.created_at, deleted_at__isnull=True
        ).exists()
        if newer:
            continue
        if document.expires_at < today:
            findings.append(
                Finding(
                    f"document:{document.pk}",
                    f"Document expiré : {document.title}",
                    f"{document.title} a expiré le {document.expires_at:%d/%m/%Y}. Déposez un document à jour.",
                    target_type="document",
                    target_id=str(document.pk),
                )
            )
        elif document.expires_at <= today + notice:
            findings.append(
                Finding(
                    f"document:{document.pk}:preavis",
                    f"Document bientôt expiré : {document.title}",
                    f"{document.title} expire le {document.expires_at:%d/%m/%Y}.",
                    severity="INFO",
                    target_type="document",
                    target_id=str(document.pk),
                )
            )
    return findings


def _doc_manquant(rule: AlertRule, pme: Pme, today: date) -> list[Finding]:
    from pme360.compliance.services import required_document_types

    baseline = ScoreSnapshot.objects.filter(pme=pme, is_frozen=True).order_by("reference_date").first()
    if baseline is None or (today - baseline.reference_date).days < rule.params.get("days_after_request", 30):
        return []
    present = set(
        Document.objects.filter(pme=pme, deleted_at__isnull=True, integrity_status=Document.Integrity.SAIN).values_list(
            "document_type__code", flat=True
        )
    )
    findings = []
    for type_code, criteria in required_document_types(pme).items():
        if type_code not in present:
            findings.append(
                Finding(
                    f"type:{type_code}",
                    f"Document manquant : {type_code}",
                    f"Le justificatif {type_code} est demandé (critères {', '.join(criteria)}) et n'a pas été déposé.",
                    details={"criteria": criteria},
                )
            )
    return findings


def _echeance_proche(rule: AlertRule, pme: Pme, today: date) -> list[Finding]:
    horizon = today + timedelta(days=rule.params.get("days", 7))
    return [
        Finding(
            f"deadline:{d.pk}",
            f"Échéance proche : {d.pme_obligation.template.name}",
            f"{d.pme_obligation.template.name} ({d.period_label}) est attendu avant le {d.due_date:%d/%m/%Y}.",
            target_type="deadline",
            target_id=str(d.pk),
        )
        for d in Deadline.objects.filter(
            pme=pme, status=Deadline.Status.A_FOURNIR, due_date__gte=today, due_date__lte=horizon
        ).select_related("pme_obligation__template")
    ]


def _obligation_depassee(rule: AlertRule, pme: Pme, today: date) -> list[Finding]:
    findings = []
    threshold = rule.params.get("days_overdue", 15)
    critical_after = rule.params.get("critical_days_overdue", 30)
    for deadline in Deadline.objects.filter(
        pme=pme,
        status__in=[Deadline.Status.EN_RETARD, Deadline.Status.A_FOURNIR],
        due_date__lt=today - timedelta(days=threshold),
    ).select_related("pme_obligation__template"):
        late = (today - deadline.due_date).days
        template = deadline.pme_obligation.template
        severity = "CRITIQUE" if template.is_critical and late >= critical_after else None
        findings.append(
            Finding(
                f"deadline:{deadline.pk}",
                f"Obligation dépassée : {template.name}",
                f"{template.name} ({deadline.period_label}) : {late} jours de retard.",
                severity=severity,
                target_type="deadline",
                target_id=str(deadline.pk),
                details={"days_late": late},
            )
        )
    return findings


def _anomalie_doc(rule: AlertRule, pme: Pme, today: date) -> list[Finding]:
    return [
        Finding(
            f"document:{d.pk}",
            f"Fichier bloqué : {d.title}",
            f"Un fichier déposé pour « {d.title} » a été bloqué par l'antivirus. Il n'a pas été enregistré.",
            severity="CRITIQUE",
            target_type="document",
            target_id=str(d.pk),
        )
        for d in Document.objects.filter(pme=pme, integrity_status=Document.Integrity.REJETE_SECURITE)
    ]


def _incoherence(rule: AlertRule, pme: Pme, today: date) -> list[Finding]:
    """Anomalies des contrôles (Document 4, § 5) sur les documents encore en attente de décision humaine."""
    from pme360.documents.models import DocumentCheck

    findings = []
    pending = Document.objects.filter(
        pme=pme, deleted_at__isnull=True, verification_status=Document.Verification.VERIF_HUMAINE_REQUISE
    )
    for document in pending:
        checks = [
            c
            for c in DocumentCheck.objects.filter(
                version__document=document, version__version_no=document.current_version_no
            )
            if c.details.get("anomaly")
        ]
        if not checks:
            continue
        severity = max((c.details.get("severity", "MOYENNE") for c in checks), key=SEVERITY_ORDER.index)
        findings.append(
            Finding(
                f"document:{document.pk}",
                f"Incohérence détectée : {document.title}",
                "Incohérence détectée. Vérification requise. " + " ".join(c.message for c in checks),
                severity=severity,
                target_type="document",
                target_id=str(document.pk),
                details={"checks": [c.check_code for c in checks]},
            )
        )
    return findings


def _frozen(pme: Pme) -> list[ScoreSnapshot]:
    return list(ScoreSnapshot.objects.filter(pme=pme, is_frozen=True).order_by("reference_date", "computed_at"))


def _score_baisse(rule: AlertRule, pme: Pme, today: date) -> list[Finding]:
    snapshots = _frozen(pme)
    if len(snapshots) < 2:
        return []
    previous, last = snapshots[-2], snapshots[-1]
    findings = []
    if previous.global_score is not None and last.global_score is not None:
        drop = float(previous.global_score - last.global_score)
        if drop >= rule.params.get("global_drop", 5):
            findings.append(
                Finding(
                    f"snapshot:{last.pk}:global",
                    "Score global en baisse",
                    f"Le score global passe de {previous.global_score} à {last.global_score}.",
                    target_type="snapshot",
                    target_id=str(last.pk),
                )
            )
    before = {d["code"]: d for d in previous.result.get("dimensions", [])}
    for dimension in last.result.get("dimensions", []):
        old = before.get(dimension["code"], {}).get("score")
        if (
            old is not None
            and dimension["score"] is not None
            and old - dimension["score"] >= rule.params.get("dimension_drop", 10)
        ):
            severity = "ELEVEE" if dimension["pillar"] == "A" else None
            findings.append(
                Finding(
                    f"snapshot:{last.pk}:{dimension['code']}",
                    f"Baisse : {dimension['short_name']}",
                    f"{dimension['short_name']} passe de {round(old)} à {round(dimension['score'])}.",
                    severity=severity,
                    target_type="snapshot",
                    target_id=str(last.pk),
                )
            )
    return findings


def _risque_eleve(rule: AlertRule, pme: Pme, today: date) -> list[Finding]:
    snapshots = _frozen(pme)
    if not snapshots or snapshots[-1].risk_index is None:
        return []
    last = snapshots[-1]
    if float(last.risk_index) >= rule.params.get("risk_index", 70):
        return [
            Finding(
                "risk",
                "Exposition au risque élevée",
                f"L'exposition au risque est de {last.risk_index}/100 (maîtrise des risques faible).",
                target_type="snapshot",
                target_id=str(last.pk),
            )
        ]
    return []


def _stagnation(rule: AlertRule, pme: Pme, today: date) -> list[Finding]:
    snapshots = _frozen(pme)
    baseline = next((s for s in snapshots if s.kind == ScoreSnapshot.Kind.BASELINE), None)
    if baseline is None or pme.lifecycle_status != Pme.LifecycleStatus.ACCOMPAGNEMENT_ACTIF:
        return []
    months = (today - baseline.reference_date).days / 30.44
    if months < rule.params.get("months", 6):
        return []
    last = snapshots[-1]
    gain = float(last.global_score - baseline.global_score) if last.global_score is not None else 0
    if gain < rule.params.get("min_gain", 2):
        return [
            Finding(
                "stagnation",
                "Absence de progression",
                f"Moins de {rule.params.get('min_gain', 2)} points gagnés en {round(months)} mois d'accompagnement.",
                details={"gain": round(gain, 1)},
            )
        ]
    return []


def _ca_baisse(rule: AlertRule, pme: Pme, today: date) -> list[Finding]:
    snapshots = _frozen(pme)
    if not snapshots:
        return []
    metric = next((m for m in snapshots[-1].result.get("metrics", []) if m["code"] == "CA_CROISSANCE"), None)
    if metric and metric["value"] is not None and metric["value"] <= rule.params.get("growth_max", -0.20):
        return [
            Finding(
                "ca",
                "Baisse importante du chiffre d'affaires",
                f"Le chiffre d'affaires évolue de {round(metric['value'] * 100)} % sur un an.",
                details={"growth": metric["value"]},
            )
        ]
    return []


def _action_retard(rule: AlertRule, pme: Pme, today: date) -> list[Finding]:
    """Action du plan en retard (Document 7, § 8.2) : ÉLEVÉE si critique ou en retard de plus de 15 jours."""
    from pme360.plans.services import overdue_actions

    findings = []
    for action in overdue_actions(pme, today):
        late = (today - action.due_date).days
        severe = late > rule.params.get("late_days", 15) or float(action.priority_score) >= rule.params.get(
            "critical_priority", 70
        )
        findings.append(
            Finding(
                f"action:{action.pk}",
                f"Action en retard : {action.title}",
                f"{action.human_ref} devait être terminée le {action.due_date:%d/%m/%Y} ({late} j de retard).",
                severity="ELEVEE" if severe else None,
                target_type="action",
                target_id=str(action.pk),
                details={"late_days": late, "waiting_on": action.waiting_on},
            )
        )
    return findings


EVALUATORS = {
    "ACTION_RETARD": _action_retard,
    "DOC_EXPIRE": _doc_expire,
    "DOC_MANQUANT": _doc_manquant,
    "ECHEANCE_PROCHE": _echeance_proche,
    "OBLIGATION_DEPASSEE": _obligation_depassee,
    "ANOMALIE_DOC": _anomalie_doc,
    "SCORE_BAISSE": _score_baisse,
    "RISQUE_ELEVE": _risque_eleve,
    "STAGNATION": _stagnation,
    "CA_BAISSE": _ca_baisse,
    "INCOHERENCE": _incoherence,
}


# --- Création / résolution ------------------------------------------------------------------------------------


def _raise(rule: AlertRule, pme: Pme, finding: Finding) -> Alert | None:
    if Alert.objects.filter(rule=rule, dedup_key=finding.key, status__in=Alert.OPEN).exists():
        return None
    alert = Alert.objects.create(
        pme=pme,
        rule=rule,
        severity=finding.severity or rule.severity,
        title=finding.title,
        message=finding.message,
        details=finding.details,
        target_type=finding.target_type,
        target_id=finding.target_id,
        dedup_key=finding.key,
    )
    audit.record(
        "alert.raised",
        instance=alert,
        pme_id=pme.pk,
        actor_type="SYSTEM",
        after={"rule": rule.code, "severity": alert.severity, "title": alert.title},
    )
    if SEVERITY_ORDER.index(alert.severity) >= SEVERITY_ORDER.index("MOYENNE"):
        notifications.notify(
            notifications.recipients(pme, rule.recipients),
            "ALERT_RAISED",
            {
                "severity": alert.get_severity_display().lower(),
                "title": alert.title,
                "message": alert.message,
                "pme": pme.legal_name,
            },
            link=f"/pme/{pme.pk}?onglet=alertes",
            pme=pme,
            severity=alert.severity,
        )
    return alert


def _auto_resolve(rule: AlertRule, pme: Pme, active_keys: set[str]) -> int:
    stale = Alert.objects.filter(rule=rule, pme=pme, status__in=Alert.OPEN).exclude(dedup_key__in=active_keys)
    count = 0
    for alert in stale:
        alert.status = Alert.Status.RESOLUE
        alert.resolved_at = timezone.now()
        alert.resolution_note = "Résolue automatiquement : la condition n'est plus remplie."
        alert.save(update_fields=["status", "resolved_at", "resolution_note", "updated_at"])
        audit.record("alert.auto_resolved", instance=alert, pme_id=pme.pk, actor_type="SYSTEM")
        count += 1
    return count


def evaluate_pme(pme: Pme, today: date) -> dict:
    raised = resolved = 0
    for rule in AlertRule.objects.filter(is_active=True, kind__in=EVALUATORS):
        findings = EVALUATORS[rule.kind](rule, pme, today)
        for finding in findings:
            raised += _raise(rule, pme, finding) is not None
        resolved += _auto_resolve(rule, pme, {f.key for f in findings})
    return {"raised": raised, "resolved": resolved}


def evaluate_kind(pme: Pme, kind: str, today: date) -> dict:
    """Évaluation ciblée d'un type de règle (ex. après l'analyse d'un document)."""
    raised = resolved = 0
    for rule in AlertRule.objects.filter(is_active=True, kind=kind):
        findings = EVALUATORS[kind](rule, pme, today)
        for finding in findings:
            raised += _raise(rule, pme, finding) is not None
        resolved += _auto_resolve(rule, pme, {f.key for f in findings})
    return {"raised": raised, "resolved": resolved}


def raise_document_anomaly(document: Document, message: str) -> None:
    rule = AlertRule.objects.filter(kind="ANOMALIE_DOC", is_active=True).first()
    if rule:
        _raise(
            rule,
            document.pme,
            Finding(
                f"document:{document.pk}",
                f"Fichier bloqué : {document.title}",
                message,
                severity="CRITIQUE",
                target_type="document",
                target_id=str(document.pk),
            ),
        )


def transition(alert: Alert, status: str, user, note: str = "") -> Alert:
    from rest_framework.exceptions import ValidationError

    if alert.status not in Alert.OPEN:
        raise ValidationError({"status": ["Cette alerte est déjà close."]})
    if status == Alert.Status.IGNOREE and not note.strip():
        raise ValidationError({"note": ["Motif obligatoire pour ignorer une alerte."]})
    before = {"status": alert.status}
    alert.status = status
    if status in (Alert.Status.RESOLUE, Alert.Status.IGNOREE):
        alert.resolved_by = user
        alert.resolved_at = timezone.now()
        alert.resolution_note = note.strip()
    alert.save()
    audit.record(f"alert.{status.lower()}", instance=alert, pme_id=alert.pme_id, before=before, after={"note": note})
    return alert
