"""Obligations, échéances récurrentes, relances et taux de conformité (Document 8, § 4 à § 6)."""

from __future__ import annotations

from calendar import monthrange
from collections.abc import Iterator
from datetime import date, timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from pme360.audit import services as audit
from pme360.core import jsonlogic
from pme360.core.exceptions import BusinessError
from pme360.documents.models import Document, DocumentType
from pme360.notifications import services as notifications
from pme360.pmes.models import Pme

from .models import Deadline, DeadlineReminder, ObligationTemplate, PmeObligation, RegulatoryRule

Frequency = ObligationTemplate.Frequency
TRACKED_LIFECYCLES = (
    Pme.LifecycleStatus.ONBOARDING,
    Pme.LifecycleStatus.DIAGNOSTIC_EN_COURS,
    Pme.LifecycleStatus.ACCOMPAGNEMENT_ACTIF,
)
MONTHS = [
    "Janvier",
    "Février",
    "Mars",
    "Avril",
    "Mai",
    "Juin",
    "Juillet",
    "Août",
    "Septembre",
    "Octobre",
    "Novembre",
    "Décembre",
]


# --- Registre réglementaire (RM-08) ---------------------------------------------------------------------------


def verify_rule(rule: RegulatoryRule, user, *, source_reference: str, verified_at: date, note: str) -> RegulatoryRule:
    """Marque une règle comme vérifiée : référence précise, date et vérificateur obligatoires."""
    if not source_reference.strip():
        raise ValidationError({"source_reference": ["Indiquez le texte et l'article vérifiés."]})
    if verified_at > timezone.localdate():
        raise ValidationError({"verified_at": ["La date de vérification ne peut pas être dans le futur."]})
    before = {"status": rule.status}
    rule.status = RegulatoryRule.Status.VERIFIE
    rule.source_reference = source_reference.strip()
    rule.verified_at = verified_at
    rule.verified_by = user
    rule.verification_note = note.strip()
    rule.review_due_at = verified_at + timedelta(days=365)
    rule.save()
    audit.record(
        "regulatory_rule.verified",
        instance=rule,
        before=before,
        after={"status": rule.status, "source_reference": rule.source_reference, "verified_at": verified_at},
    )
    from pme360.ai.knowledge import index_regulatory

    index_regulatory()
    return rule


def set_rule_status(rule: RegulatoryRule, status: str, note: str) -> RegulatoryRule:
    if status == RegulatoryRule.Status.VERIFIE:
        raise ValidationError({"status": ["Utilisez l'action de vérification (source, date et vérificateur)."]})
    before = {"status": rule.status}
    rule.status = status
    rule.verification_note = note.strip() or rule.verification_note
    rule.save()
    # Une règle qui n'est plus vérifiée désactive les obligations qui en dépendent (les échéances passées restent).
    deactivated = list(
        ObligationTemplate.objects.filter(regulatory_rule=rule, is_active=True).values_list("code", flat=True)
    )
    ObligationTemplate.objects.filter(regulatory_rule=rule).update(is_active=False)
    audit.record(
        "regulatory_rule.status_changed",
        instance=rule,
        before=before,
        after={"status": status, "deactivated_obligations": deactivated},
    )
    from pme360.ai.knowledge import index_regulatory

    index_regulatory()
    return rule


def set_template_active(template: ObligationTemplate, active: bool) -> ObligationTemplate:
    rule = template.regulatory_rule
    if active and rule is not None and rule.status != RegulatoryRule.Status.VERIFIE:
        raise BusinessError(
            f"La règle {rule.code} n'est pas vérifiée : l'obligation ne peut pas être activée (RM-08).",
            code="rule_not_verified",
            rule=rule.code,
        )
    template.is_active = active
    template.save(update_fields=["is_active", "updated_at"])
    audit.record("obligation.activated" if active else "obligation.deactivated", instance=template)
    return template


# --- Profil et périodes ---------------------------------------------------------------------------------------


def obligation_profile(pme: Pme) -> dict:
    """Profil utilisé par les règles d'applicabilité : fiche PME + profil du dernier diagnostic validé."""
    from pme360.scoring.models import ScoreSnapshot

    profile = {
        "headcount": pme.headcount,
        "size_category": pme.size_category,
        "sector": pme.sector.code if pme.sector_id else None,
        "is_company": pme.legal_form.is_company if pme.legal_form_id else None,
        "lifecycle_status": pme.lifecycle_status,
    }
    snapshot = ScoreSnapshot.objects.filter(pme=pme, is_frozen=True).order_by("-reference_date").first()
    if snapshot:
        profile = {**snapshot.result.get("profile", {}), **{k: v for k, v in profile.items() if v is not None}}
    return profile


def _add_months(day: date, months: int) -> date:
    month = day.month - 1 + months
    year = day.year + month // 12
    month = month % 12 + 1
    return date(year, month, min(day.day, monthrange(year, month)[1]))


def period_containing(frequency: str, day: date) -> tuple[date, date, str]:
    if frequency == Frequency.MENSUELLE:
        start = day.replace(day=1)
        return start, _add_months(start, 1) - timedelta(days=1), f"{MONTHS[start.month - 1]} {start.year}"
    if frequency == Frequency.TRIMESTRIELLE:
        quarter = (day.month - 1) // 3
        start = date(day.year, quarter * 3 + 1, 1)
        return start, _add_months(start, 3) - timedelta(days=1), f"T{quarter + 1} {start.year}"
    if frequency == Frequency.SEMESTRIELLE:
        half = (day.month - 1) // 6
        start = date(day.year, half * 6 + 1, 1)
        return start, _add_months(start, 6) - timedelta(days=1), f"S{half + 1} {start.year}"
    if frequency == Frequency.ANNUELLE:
        return date(day.year, 1, 1), date(day.year, 12, 31), str(day.year)
    raise ValueError(frequency)


def periods(frequency: str, start: date, until_due: date, due_days: int) -> Iterator[tuple[date, date, str, date]]:
    """Périodes depuis celle qui contient ``start`` dont l'échéance tombe au plus tard le ``until_due``."""
    if frequency == Frequency.PONCTUELLE:
        due = start + timedelta(days=due_days)
        if due <= until_due:
            yield start, start, "Transmission initiale", due
        return
    period_start, period_end, label = period_containing(frequency, start)
    while True:
        due = period_end + timedelta(days=due_days)
        if due > until_due:
            return
        yield period_start, period_end, label, due
        period_start, period_end, label = period_containing(frequency, period_end + timedelta(days=1))


def resolved_frequency(template: ObligationTemplate, profile: dict) -> str:
    if template.frequency_rule:
        value = jsonlogic.evaluate(template.frequency_rule, profile)
        if value in Frequency.values:
            return value
    return template.frequency


def applicable(template: ObligationTemplate, profile: dict) -> bool:
    return not template.applicability or bool(jsonlogic.evaluate(template.applicability, profile))


# --- Synchronisation et génération (planificateur quotidien) --------------------------------------------------


def sync_obligations(pme: Pme, today: date) -> list[PmeObligation]:
    """Instancie les obligations actives applicables ; gère le changement de périodicité (Document 8, § 4)."""
    profile = obligation_profile(pme)
    obligations = []
    for template in ObligationTemplate.objects.filter(is_active=True).select_related("document_type"):
        if not applicable(template, profile):
            continue
        frequency = resolved_frequency(template, profile)
        obligation, created = PmeObligation.objects.get_or_create(
            pme=pme, template=template, defaults={"start_date": today, "frequency": frequency}
        )
        if created:
            audit.record(
                "obligation.assigned",
                instance=obligation,
                pme_id=pme.pk,
                after={"template": template.code, "frequency": frequency},
                actor_type="SYSTEM",
            )
        elif obligation.frequency != frequency and obligation.status == PmeObligation.Status.ACTIVE:
            # À partir de la période suivante ; l'historique n'est pas modifié.
            future = obligation.deadlines.filter(
                period_start__gt=today, status=Deadline.Status.A_FOURNIR, documents__isnull=True
            )
            removed = future.count()
            future.delete()
            audit.record(
                "obligation.frequency_changed",
                instance=obligation,
                pme_id=pme.pk,
                before={"frequency": obligation.frequency},
                after={"frequency": frequency, "future_deadlines_regenerated": removed},
                actor_type="SYSTEM",
            )
            obligation.frequency = frequency
            obligation.save(update_fields=["frequency", "updated_at"])
            notifications.notify(
                notifications.recipients(pme, ["CONSEILLER"]),
                "ALERT_RAISED",
                {
                    "severity": "information",
                    "title": f"Périodicité modifiée : {template.name}",
                    "message": f"{pme.legal_name} : la périodicité passe à « {Frequency(frequency).label} » "
                    "à partir de la prochaine période. Merci de confirmer.",
                },
                pme=pme,
                link=f"/pme/{pme.pk}?onglet=documents",
            )
        obligations.append(obligation)
    return obligations


def generate_deadlines(obligation: PmeObligation, today: date) -> int:
    """Crée les échéances d'un horizon glissant ; idempotent (unicité obligation × début de période)."""
    if obligation.status != PmeObligation.Status.ACTIVE:
        return 0
    horizon = today + timedelta(days=settings.PME360_DEADLINE_HORIZON_DAYS)
    created = 0
    template = obligation.template
    for period_start, period_end, label, due in periods(
        obligation.frequency, obligation.start_date, horizon, template.due_days_after_period_end
    ):
        if obligation.end_date and period_start > obligation.end_date:
            break
        _, was_created = Deadline.objects.get_or_create(
            pme_obligation=obligation,
            period_start=period_start,
            defaults={"pme": obligation.pme, "period_end": period_end, "period_label": label, "due_date": due},
        )
        created += was_created
    return created


def update_temporal_statuses(pme: Pme, today: date) -> None:
    Deadline.objects.filter(pme=pme, status=Deadline.Status.A_FOURNIR, due_date__lt=today).update(
        status=Deadline.Status.EN_RETARD
    )
    for deadline in Deadline.objects.filter(
        pme=pme, status__in=[Deadline.Status.CONFORME, Deadline.Status.CONFORME_SOUS_RESERVE]
    ).prefetch_related("documents"):
        if any(d.expires_at and d.expires_at < today for d in deadline.documents.all()):
            deadline.status = Deadline.Status.EXPIRE
            deadline.save(update_fields=["status", "updated_at"])


REMINDER_OPEN = (Deadline.Status.A_FOURNIR, Deadline.Status.EN_RETARD, Deadline.Status.NON_CONFORME)


def send_reminders(pme: Pme, today: date) -> int:
    """Une relance par échéance et par décalage, au plus une par jour et par échéance (la plus récente due)."""
    sent = 0
    deadlines = Deadline.objects.filter(pme=pme, status__in=REMINDER_OPEN).select_related(
        "pme_obligation__template__document_type"
    )
    for deadline in deadlines:
        template = deadline.pme_obligation.template
        elapsed = (today - deadline.due_date).days
        due_offsets = [offset for offset in template.reminder_offsets if offset <= elapsed]
        if not due_offsets:
            continue
        offset = max(due_offsets)
        _, created = DeadlineReminder.objects.get_or_create(
            deadline=deadline, offset_days=offset, defaults={"sent_on": today}
        )
        if not created:
            continue
        sent += 1
        context = {
            "document": template.document_type.name,
            "period": deadline.period_label,
            "due_date": deadline.due_date.strftime("%d/%m/%Y"),
            "pme": pme.legal_name,
            "days": elapsed,
        }
        link = "/espace"
        if offset < 0:
            notifications.notify(notifications.pme_users(pme), "DEADLINE_REMINDER", context, link=link, pme=pme)
        elif offset == 0:
            notifications.notify(notifications.pme_users(pme), "DEADLINE_DUE_TODAY", context, link=link, pme=pme)
        else:
            kinds = ["PME"] + (["CONSEILLER"] if offset >= 15 else [])
            notifications.notify(
                notifications.recipients(pme, kinds), "DEADLINE_OVERDUE", context, link=link, pme=pme, severity="ELEVEE"
            )
            if offset >= 30 and template.is_critical:
                notifications.notify(
                    notifications.recipients(pme, ["RESPONSABLE_PROGRAMME"]),
                    "DEADLINE_ESCALATION",
                    context,
                    link=f"/pme/{pme.pk}?onglet=documents",
                    pme=pme,
                    severity="CRITIQUE",
                )
    return sent


def run_for_pme(pme: Pme, today: date) -> dict:
    from pme360.alerts import engine as alerts

    stats = {"obligations": 0, "deadlines_created": 0, "reminders": 0}
    if pme.lifecycle_status in TRACKED_LIFECYCLES:
        obligations = sync_obligations(pme, today)
        stats["obligations"] = len(obligations)
        stats["deadlines_created"] = sum(generate_deadlines(o, today) for o in obligations)
    update_temporal_statuses(pme, today)
    stats["reminders"] = send_reminders(pme, today)
    alerts.evaluate_pme(pme, today)
    return stats


def waive(deadline: Deadline, reason: str, user) -> Deadline:
    if not reason.strip():
        raise ValidationError({"reason": ["Motif de dispense obligatoire."]})
    before = {"status": deadline.status}
    deadline.status = Deadline.Status.DISPENSE
    deadline.closed_at = timezone.now()
    deadline.save(update_fields=["status", "closed_at", "updated_at"])
    audit.record("deadline.waived", instance=deadline, pme_id=deadline.pme_id, before=before, after={"reason": reason})
    return deadline


# --- Taux de conformité et dossier (Document 8, § 3 et § 6) ---------------------------------------------------


def required_document_types(pme: Pme) -> dict[str, list[str]]:
    """Types de documents exigés (critères applicables à preuve obligatoire) → critères concernés."""
    from pme360.scoring.models import ScoreSnapshot

    snapshot = ScoreSnapshot.objects.filter(pme=pme, is_frozen=True).order_by("-reference_date").first()
    if snapshot is None:
        return {}
    from pme360.diagnostic.models import Criterion

    applicable_codes = {c["code"] for c in snapshot.result.get("criteria", []) if c["status"] != "NON_APPLICABLE"}
    required: dict[str, list[str]] = {}
    for code, types in Criterion.objects.filter(
        framework_version=snapshot.framework_version, evidence_policy="REQUIRED", code__in=applicable_codes
    ).values_list("code", "evidence_document_types"):
        if types:
            # Un critère à plusieurs justificatifs possibles est satisfait par le premier (le principal).
            required.setdefault(types[0], []).append(code)
    return required


def _document_state(documents: list[Document], today: date) -> str:
    if not documents:
        return "MANQUANT"
    states = {d.status_display for d in documents}
    for state in ("CONFORME", "CONFORME_SOUS_RESERVE"):
        if state in states:
            return state
    if "EXPIRE" in states:
        return "EXPIRE"
    if states & {"A_VERIFIER", "EN_ANALYSE", "RECU"}:
        return "EN_VERIFICATION"
    return "NON_CONFORME"


def compliance_rate(pme: Pme, today: date | None = None) -> dict:
    """Taux = Σ points / éléments exigibles (CONFORME = 1 ; SOUS RÉSERVE = 0,5 ; autres = 0)."""
    today = today or timezone.localdate()
    counts = {
        "CONFORME": 0,
        "CONFORME_SOUS_RESERVE": 0,
        "MANQUANT": 0,
        "EXPIRE": 0,
        "EN_VERIFICATION": 0,
        "NON_CONFORME": 0,
    }
    points = 0.0
    eligible = 0
    deadlines = Deadline.objects.filter(pme=pme, due_date__lte=today, due_date__gt=today - timedelta(days=365)).exclude(
        status=Deadline.Status.DISPENSE
    )
    mapping = {
        Deadline.Status.CONFORME: "CONFORME",
        Deadline.Status.CONFORME_SOUS_RESERVE: "CONFORME_SOUS_RESERVE",
        Deadline.Status.EXPIRE: "EXPIRE",
        Deadline.Status.A_FOURNIR: "MANQUANT",
        Deadline.Status.EN_RETARD: "MANQUANT",
        Deadline.Status.RECU: "EN_VERIFICATION",
        Deadline.Status.EN_ANALYSE: "EN_VERIFICATION",
        Deadline.Status.VERIF_HUMAINE_REQUISE: "EN_VERIFICATION",
        Deadline.Status.EN_ATTENTE: "EN_VERIFICATION",
    }
    for deadline in deadlines:
        state = mapping.get(deadline.status, "NON_CONFORME")
        counts[state] += 1
        eligible += 1
    documents: dict[str, list[Document]] = {}
    for document in Document.objects.filter(pme=pme, deleted_at__isnull=True).select_related("document_type"):
        documents.setdefault(document.document_type.code, []).append(document)
    for type_code in required_document_types(pme):
        state = _document_state(documents.get(type_code, []), today)
        counts[state] += 1
        eligible += 1
    points = counts["CONFORME"] + 0.5 * counts["CONFORME_SOUS_RESERVE"]
    return {
        "rate": round(points / eligible, 3) if eligible else None,
        "eligible": eligible,
        "points": points,
        "counts": counts,
    }


def compliance_folder(pme: Pme) -> list[dict]:
    """Dossier numérique de conformité par catégorie (Document 8, § 3)."""
    today = timezone.localdate()
    required = required_document_types(pme)
    obligations = {
        o.template.document_type_id: o for o in PmeObligation.objects.filter(pme=pme).select_related("template")
    }
    documents: dict = {}
    for document in (
        Document.objects.filter(pme=pme, deleted_at__isnull=True)
        .select_related("document_type")
        .order_by("-created_at")
    ):
        documents.setdefault(document.document_type_id, []).append(document)
    categories: dict = {}
    for doc_type in DocumentType.objects.filter(is_active=True).select_related("category"):
        docs = documents.get(doc_type.pk, [])
        obligation = obligations.get(doc_type.pk)
        is_required = doc_type.code in required
        if not (docs or obligation or is_required):
            continue
        category = categories.setdefault(
            doc_type.category.code,
            {
                "code": doc_type.category.code,
                "name": doc_type.category.name,
                "order": doc_type.category.order,
                "items": [],
            },
        )
        category["items"].append(
            {
                "document_type": {
                    "id": doc_type.pk,
                    "code": doc_type.code,
                    "name": doc_type.name,
                    "guidance": doc_type.guidance,
                },
                "required": is_required,
                "criteria": required.get(doc_type.code, []),
                "obligation": obligation.template.name if obligation else None,
                "state": _document_state(docs, today) if (is_required or docs) else "MANQUANT",
                "documents": docs,
            }
        )
    return sorted(categories.values(), key=lambda c: c["order"])
