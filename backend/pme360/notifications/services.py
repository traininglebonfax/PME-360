"""Envoi des notifications (in-app + e-mail) selon les modèles et les préférences (Document 7, § 8.3)."""

from __future__ import annotations

import structlog
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from pme360.accounts.access import active_membership_q
from pme360.accounts.models import Scope, User, UserMembership
from pme360.compliance.defaults import MANDATORY_EVENTS, NOTIFICATION_TEMPLATES
from pme360.pmes.models import Pme, PmeAssignment

from .models import Notification, NotificationPreference, NotificationTemplate

logger = structlog.get_logger(__name__)


class _SafeDict(dict):
    def __missing__(self, key):  # une variable absente ne casse pas le message
        return ""


# --- Destinataires --------------------------------------------------------------------------------------------


def pme_users(pme: Pme) -> list[User]:
    return list(
        User.objects.filter(
            is_active=True,
            memberships__in=UserMembership.objects.filter(active_membership_q(), scope=Scope.PME, scope_ref_id=pme.pk),
        ).distinct()
    )


def advisors(pme: Pme, *, experts: bool = False) -> list[User]:
    roles = [PmeAssignment.RoleInPme.CONSEILLER_PRINCIPAL] + ([PmeAssignment.RoleInPme.EXPERT] if experts else [])
    return list(
        User.objects.filter(
            is_active=True,
            pme_assignments__in=PmeAssignment.objects.filter(pme=pme, end_date__isnull=True, role_in_pme__in=roles),
        ).distinct()
    )


def programme_managers(pme: Pme) -> list[User]:
    programmes = pme.enrollments.filter(exited_at__isnull=True).values("cohort__programme_id")
    return list(
        User.objects.filter(
            is_active=True,
            memberships__in=UserMembership.objects.filter(
                active_membership_q(),
                role__code="RESPONSABLE_PROGRAMME",
                scope=Scope.PROGRAMME,
                scope_ref_id__in=programmes,
            ),
        ).distinct()
    )


def recipients(pme: Pme, kinds: list[str]) -> list[User]:
    users: dict = {}
    for kind in kinds:
        found = {
            "PME": lambda: pme_users(pme),
            "CONSEILLER": lambda: advisors(pme),
            "EXPERT": lambda: [u for u in advisors(pme, experts=True)],
            "RESPONSABLE_PROGRAMME": lambda: programme_managers(pme),
        }.get(kind, list)()
        for user in found:
            users[user.pk] = user
    return list(users.values())


# --- Envoi ----------------------------------------------------------------------------------------------------


def _template(event_code: str) -> tuple[str, str]:
    template = NotificationTemplate.objects.filter(event_code=event_code).first()
    if template:
        return template.subject, template.body
    return NOTIFICATION_TEMPLATES[event_code]


def notify(
    users: list[User], event_code: str, context: dict, *, link: str = "", pme: Pme | None = None, severity: str = "INFO"
) -> list[Notification]:
    """Notifie chaque utilisateur selon ses préférences ; les événements obligatoires ignorent les préférences."""
    subject_template, body_template = _template(event_code)
    values = _SafeDict({key: ("" if value is None else value) for key, value in context.items()})
    subject = subject_template.format_map(values)
    body = body_template.format_map(values).strip()
    mandatory = event_code in MANDATORY_EVENTS
    preferences = {p.user_id: p for p in NotificationPreference.objects.filter(user__in=users, event_code=event_code)}
    created = []
    for user in users:
        preference = preferences.get(user.pk)
        in_app = mandatory or preference is None or preference.in_app
        email = mandatory or preference is None or preference.email
        if not (in_app or email):
            continue
        notification = Notification.objects.create(
            user=user,
            pme=pme,
            event_code=event_code,
            title=subject,
            body=body,
            link=link,
            severity=severity,
            read_at=None if in_app else timezone.now(),
        )
        if email:
            try:
                url = f"{settings.FRONTEND_URL}{link}" if link else settings.FRONTEND_URL
                send_mail(
                    subject, f"Bonjour {user.full_name},\n\n{body}\n\n{url}\n\nL'équipe PME360", None, [user.email]
                )
                notification.emailed_at = timezone.now()
                notification.save(update_fields=["emailed_at"])
            except Exception:  # l'échec d'un e-mail ne doit pas bloquer le traitement métier
                logger.exception("notification.email_failed", user_id=str(user.pk), event=event_code)
        created.append(notification)
    return created


EVENT_LABELS = {
    "DOCUMENT_TO_VERIFY": "Document déposé à vérifier",
    "DOCUMENT_DECISION": "Décision sur un document",
    "DOCUMENT_REJECTED_SECURITY": "Fichier bloqué par l'antivirus",
    "DEADLINE_REMINDER": "Rappel d'échéance",
    "DEADLINE_DUE_TODAY": "Échéance du jour",
    "DEADLINE_OVERDUE": "Échéance dépassée",
    "DEADLINE_ESCALATION": "Obligation critique en retard (escalade)",
    "ALERT_RAISED": "Nouvelle alerte",
    "AI_BUDGET_WARNING": "Budget IA (80 %)",
    "PREDIAGNOSTIC_READY": "Pré-diagnostic IA prêt",
}
