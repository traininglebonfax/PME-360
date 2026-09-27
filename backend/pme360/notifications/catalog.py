"""Modèles de notification modifiables par l'organisation (Document 7, § 8.3 ; Document 10, V1).

Chaque événement déclare ses variables (libellé + exemple pour l'aperçu). Le rendu est une simple substitution de
``{variable}`` : pas d'accès aux attributs ni de format Python, un modèle saisi par un administrateur ne peut donc
rien exposer d'autre que les valeurs prévues. ``{{`` et ``}}`` produisent des accolades littérales.
"""

from __future__ import annotations

import re

from django.conf import settings
from rest_framework.exceptions import PermissionDenied, ValidationError

from pme360.audit import services as audit
from pme360.compliance.defaults import MANDATORY_EVENTS, NOTIFICATION_TEMPLATES

from .models import NotificationTemplate

TOKEN = re.compile(r"\{\{|\}\}|\{([a-z_]+)\}")
SUBJECT_MAX = 200
BODY_MAX = 2000

PME = ("pme", "Raison sociale de la PME", "Boutik Plus SARL")
DOCUMENT = ("document", "Document concerné", "Attestation de régularité CNPS")
PERIOD = ("period", "Période concernée", "Août 2026")
DUE_DATE = ("due_date", "Date limite", "15/09/2026")
ACTION = ("action", "Titre de l'action", "Mettre en place une comptabilité mensuelle")

EVENTS: dict[str, dict] = {
    "DOCUMENT_TO_VERIFY": {
        "label": "Document déposé à vérifier",
        "audience": "Conseiller principal",
        "variables": [DOCUMENT, PME],
    },
    "DOCUMENT_DECISION": {
        "label": "Décision sur un document",
        "audience": "PME",
        "variables": [DOCUMENT, ("decision", "Décision", "Validé"), ("reason", "Motif du conseiller", "")],
    },
    "DOCUMENT_REJECTED_SECURITY": {
        "label": "Fichier bloqué par l'antivirus",
        "audience": "Conseiller principal et auteur du dépôt",
        "variables": [("filename", "Nom du fichier", "releve-aout.pdf"), PME],
    },
    "DEADLINE_REMINDER": {
        "label": "Rappel d'échéance",
        "audience": "PME",
        "variables": [DOCUMENT, PERIOD, DUE_DATE, PME],
    },
    "DEADLINE_DUE_TODAY": {
        "label": "Échéance du jour",
        "audience": "PME",
        "variables": [DOCUMENT, PERIOD, DUE_DATE, PME],
    },
    "DEADLINE_OVERDUE": {
        "label": "Échéance dépassée",
        "audience": "PME ; conseiller à partir de 15 jours de retard",
        "variables": [DOCUMENT, PERIOD, DUE_DATE, PME, ("days", "Jours de retard", "7")],
    },
    "DEADLINE_ESCALATION": {
        "label": "Obligation critique en retard (escalade)",
        "audience": "Responsable de programme",
        "variables": [DOCUMENT, PERIOD, DUE_DATE, PME, ("days", "Jours de retard", "30")],
    },
    "ALERT_RAISED": {
        "label": "Nouvelle alerte",
        "audience": "Destinataires de la règle d'alerte",
        "variables": [
            ("severity", "Sévérité", "élevée"),
            ("title", "Titre de l'alerte", "Score en baisse"),
            ("message", "Message de l'alerte", "Le score a baissé de 12 points depuis le dernier diagnostic."),
            PME,
        ],
    },
    "AI_BUDGET_WARNING": {
        "label": "Budget IA (80 %)",
        "audience": "Administrateurs de l'organisation",
        "variables": [("usage", "Jetons consommés", "800 000"), ("quota", "Quota mensuel", "1 000 000")],
    },
    "PREDIAGNOSTIC_READY": {
        "label": "Pré-diagnostic IA prêt",
        "audience": "Conseiller principal",
        "variables": [PME, ("count", "Nombre de critères proposés", "18")],
    },
    "PLAN_TO_ACCEPT": {
        "label": "Plan d'accompagnement à accepter",
        "audience": "PME",
        "variables": [PME, ("actions", "Nombre d'actions", "6")],
    },
    "PLAN_ACCEPTED": {"label": "Plan accepté par la PME", "audience": "Conseiller principal", "variables": [PME]},
    "ACTION_DOCUMENT_REQUESTED": {
        "label": "Document attendu pour une action",
        "audience": "PME",
        "variables": [ACTION, ("documents", "Documents attendus", "Grille de trésorerie, Journal de caisse")],
    },
    "ACTION_DELIVERABLE_REJECTED": {
        "label": "Livrable à reprendre",
        "audience": "PME",
        "variables": [ACTION, ("reason", "Motif du conseiller", "Le mois de juillet manque.")],
    },
    "ACTION_UNBLOCKED": {"label": "Action débloquée", "audience": "PME", "variables": [ACTION]},
    "ACTION_COMMENTED": {
        "label": "Message sur une action",
        "audience": "PME ou conseiller (l'autre partie)",
        "variables": [
            ACTION,
            ("author", "Auteur du message", "Konan Yao"),
            ("excerpt", "Début du message", "Pouvez-vous préciser le format attendu ?"),
        ],
    },
    "REPORT_READY": {
        "label": "Rapport disponible",
        "audience": "PME et conseiller principal",
        "variables": [PME, ("report", "Nature du rapport", "rapport de suivi"), ("version", "Version du rapport", "2")],
    },
}
assert set(EVENTS) == set(NOTIFICATION_TEMPLATES), "chaque événement doit être décrit"


def variables(event_code: str) -> list[dict]:
    return [{"name": n, "label": label, "example": example} for n, label, example in EVENTS[event_code]["variables"]]


def examples(event_code: str) -> dict:
    return {n: example for n, _, example in EVENTS[event_code]["variables"]}


def render(text: str, values: dict) -> str:
    """Remplace ``{variable}`` ; une variable absente donne une chaîne vide."""

    def substitute(match: re.Match) -> str:
        token = match.group(0)
        if token in ("{{", "}}"):
            return token[0]
        value = values.get(match.group(1))
        return "" if value is None else str(value)

    return TOKEN.sub(substitute, text)


def check(text: str, event_code: str) -> list[str]:
    """Erreurs d'un modèle : accolade isolée, variable inconnue pour cet événement."""
    allowed = {n for n, _, _ in EVENTS[event_code]["variables"]}
    errors = []
    unknown = sorted({m.group(1) for m in TOKEN.finditer(text) if m.group(1) and m.group(1) not in allowed})
    if unknown:
        errors.append(
            "Variable(s) inconnue(s) pour cet événement : "
            + ", ".join("{" + name + "}" for name in unknown)
            + ". Disponibles : "
            + ", ".join("{" + name + "}" for name in sorted(allowed))
            + "."
        )
    leftover = TOKEN.sub("", text)
    if "{" in leftover or "}" in leftover:
        errors.append("Accolade isolée : écrivez {variable}, ou {{ et }} pour une accolade littérale.")
    return errors


def email_text(full_name: str, body: str, link: str = "") -> str:
    url = f"{settings.FRONTEND_URL}{link}" if link else settings.FRONTEND_URL
    from pme360.organizations.branding import current_brand

    return f"Bonjour {full_name},\n\n{body}\n\n{url}\n\nL'équipe {current_brand()['short_name']}"


# --- Administration -----------------------------------------------------------------------------------------------


def _require(access) -> None:
    if not access.has("org.configure") or access.is_pme_user:
        raise PermissionDenied()


def entries() -> list[dict]:
    stored = {t.event_code: t for t in NotificationTemplate.objects.all()}
    items = []
    for code, meta in EVENTS.items():
        default_subject, default_body = NOTIFICATION_TEMPLATES[code]
        template = stored.get(code)
        subject = template.subject if template else default_subject
        body = template.body if template else default_body
        items.append(
            {
                "event_code": code,
                "label": meta["label"],
                "audience": meta["audience"],
                "mandatory": code in MANDATORY_EVENTS,
                "subject": subject,
                "body": body,
                "default_subject": default_subject,
                "default_body": default_body,
                "is_default": subject == default_subject and body == default_body,
                "variables": variables(code),
                "updated_at": template.updated_at if template else None,
            }
        )
    return items


def validate(event_code: str, subject: str, body: str) -> tuple[str, str]:
    subject, body = (subject or "").strip(), (body or "").strip()
    errors: dict[str, list[str]] = {}
    if not subject:
        errors["subject"] = ["Objet obligatoire."]
    elif len(subject) > SUBJECT_MAX or "\n" in subject:
        errors["subject"] = [f"Objet sur une ligne, {SUBJECT_MAX} caractères au plus."]
    elif problems := check(subject, event_code):
        errors["subject"] = problems
    if not body:
        errors["body"] = ["Message obligatoire."]
    elif len(body) > BODY_MAX:
        errors["body"] = [f"{BODY_MAX} caractères au plus."]
    elif problems := check(body, event_code):
        errors["body"] = problems
    if errors:
        raise ValidationError(errors)
    return subject, body


def save(access, event_code: str, subject: str, body: str, *, action: str = "updated") -> NotificationTemplate:
    _require(access)
    subject, body = validate(event_code, subject, body)
    template = NotificationTemplate.objects.filter(event_code=event_code).first()
    previous = (template.subject, template.body) if template else NOTIFICATION_TEMPLATES[event_code]
    before = {"subject": previous[0], "body": previous[1]}
    if template is None:
        template = NotificationTemplate(event_code=event_code)
    template.subject, template.body = subject, body
    template.save()
    audit.record(
        f"notification_template.{action}", instance=template, before=before, after={"subject": subject, "body": body}
    )
    return template


def reset(access, event_code: str) -> NotificationTemplate:
    subject, body = NOTIFICATION_TEMPLATES[event_code]
    return save(access, event_code, subject, body, action="reset")
