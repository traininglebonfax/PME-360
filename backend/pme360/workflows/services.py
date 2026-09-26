"""Résolution et administration des workflows configurables (V1).

``action_workflow()`` renvoie la définition active de l'organisation, ou le workflow par défaut si aucune n'a été
activée. Le moteur des actions (``plans.services``) ne connaît plus de table de transitions en dur.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from pme360.audit import services as audit
from pme360.core.exceptions import BusinessError

from . import defaults
from .models import WorkflowDefinition

ACTION = WorkflowDefinition.TargetType.ACTION
LABEL_MAX = 60


@dataclass
class Workflow:
    version: int
    states: dict
    transitions: list[dict]

    def find(self, source: str, target: str) -> dict | None:
        return next((t for t in self.transitions if t["from"] == source and t["to"] == target), None)

    def allowed(self, source: str, actor: str) -> list[dict]:
        return [t for t in self.transitions if t["from"] == source and actor in t["actors"]]

    def label(self, state: str, pme: bool = False) -> str:
        item = self.states.get(state, {})
        return item.get("pme_label" if pme else "label") or state


def default_action_workflow() -> Workflow:
    return Workflow(
        0, {k: dict(v) for k, v in defaults.ACTION_STATES.items()}, [dict(t) for t in defaults.ACTION_TRANSITIONS]
    )


def action_workflow() -> Workflow:
    active = WorkflowDefinition.objects.filter(target_type=ACTION, status=WorkflowDefinition.Status.ACTIVE).first()
    if active is None:
        return default_action_workflow()
    return Workflow(active.version, active.states, active.transitions)


# --- Contrôles ------------------------------------------------------------------------------------------------


def check(states: dict, transitions: list[dict]) -> tuple[list[str], list[str]]:
    """Anomalies bloquantes et avertissements d'une définition d'action."""
    errors: list[str] = []
    warnings: list[str] = []
    codes = set(defaults.ACTION_STATES)
    if set(states) != codes:
        errors.append("Les états sont fixés par le moteur : ni ajout ni suppression.")
    for code in codes & set(states):
        for field, name in (("label", "libellé"), ("pme_label", "libellé côté PME")):
            value = str(states[code].get(field, "")).strip()
            if not value or len(value) > LABEL_MAX:
                errors.append(f"{code} : {name} obligatoire ({LABEL_MAX} caractères au plus).")
    seen = set()
    for t in transitions:
        source, target = t.get("from"), t.get("to")
        name = f"{states.get(source, {}).get('label', source)} → {states.get(target, {}).get('label', target)}"
        if source not in codes or target not in codes or source == target:
            errors.append(f"Transition invalide : {source} → {target}.")
            continue
        if (source, target) in seen:
            errors.append(f"{name} : transition en double.")
        seen.add((source, target))
        if source in defaults.TERMINAL:
            errors.append(f"{name} : on ne sort pas d'un état final (terminée ou abandonnée).")
        if target in defaults.SYSTEM_ONLY_TARGETS:
            errors.append(f"{name} : cet état est atteint automatiquement par le moteur, pas manuellement.")
        actors = set(t.get("actors") or [])
        if not actors or not actors <= {defaults.STAFF, defaults.PME}:
            errors.append(f"{name} : indiquez qui peut déclencher cette transition.")
        if defaults.PME in actors and target not in defaults.PME_TARGETS:
            errors.append(
                f"{name} : la PME ne peut que démarrer ou reprendre une action, "
                "ou signaler qu'elle attend son conseiller."
            )
        for field in ("button", "pme_button"):
            if len(str(t.get(field, ""))) > LABEL_MAX:
                errors.append(f"{name} : libellé de bouton trop long ({LABEL_MAX} caractères au plus).")
        if not str(t.get("button", "")).strip():
            errors.append(f"{name} : libellé du bouton obligatoire.")
    # Garde-fou : toute action non terminée peut être abandonnée par l'équipe, avec motif (Document 7, § 2.2).
    for code in sorted(codes - defaults.TERMINAL):
        abandon = next((t for t in transitions if t.get("from") == code and t.get("to") == defaults.ABANDON), None)
        if abandon is None or defaults.STAFF not in (abandon.get("actors") or []) or not abandon.get("reason_required"):
            errors.append(
                f"{states.get(code, {}).get('label', code)} : l'abandon par l'équipe avec motif doit rester possible."
            )
    # Accessibilité : une action démarrée doit pouvoir être terminée.
    graph: dict[str, set[str]] = {}
    for t in [*transitions, *defaults.SYSTEM_TRANSITIONS]:
        graph.setdefault(t.get("from"), set()).add(t.get("to"))

    def reaches_end(start: str) -> bool:
        queue, visited = deque([start]), {start}
        while queue:
            state = queue.popleft()
            if state == "TERMINE":
                return True
            for nxt in graph.get(state, ()):
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append(nxt)
        return False

    if not reaches_end("NON_COMMENCE"):
        errors.append(
            "Une action non commencée ne peut plus jamais être terminée : ajoutez un chemin vers « Terminée »."
        )
    for code in sorted(codes - defaults.TERMINAL - {"NON_COMMENCE"}):
        if code in states and not reaches_end(code):
            warnings.append(f"Depuis « {states[code].get('label', code)} », l'action ne peut plus qu'être abandonnée.")
    for code in ("EN_ATTENTE_PME", "EN_ATTENTE_GUDE"):
        if code in states and not any(t.get("to") == code for t in transitions):
            warnings.append(f"« {states[code].get('label', code)} » n'est plus jamais utilisé.")
    return errors, warnings


# --- Administration -------------------------------------------------------------------------------------------


def _require(access) -> None:
    if not access.has("org.configure") or access.is_pme_user:
        raise PermissionDenied()


def _normalize(transitions: list[dict]) -> list[dict]:
    return [
        {
            "from": t.get("from"),
            "to": t.get("to"),
            "actors": sorted(set(t.get("actors") or [])),
            "reason_required": bool(t.get("reason_required")),
            "button": str(t.get("button", "")).strip(),
            "pme_button": str(t.get("pme_button", "")).strip(),
        }
        for t in transitions
    ]


def current_draft() -> WorkflowDefinition | None:
    return WorkflowDefinition.objects.filter(target_type=ACTION, status=WorkflowDefinition.Status.DRAFT).first()


@transaction.atomic
def create_draft(access) -> WorkflowDefinition:
    _require(access)
    if current_draft():
        raise BusinessError("Un brouillon existe déjà : modifiez-le ou supprimez-le.", code="draft_exists")
    base = action_workflow()
    last = WorkflowDefinition.objects.filter(target_type=ACTION).aggregate(v=Max("version"))["v"] or 0
    draft = WorkflowDefinition.objects.create(
        target_type=ACTION,
        version=last + 1,
        states=base.states,
        transitions=base.transitions,
        notes=f"Brouillon créé à partir de la version {base.version or 'par défaut'}.",
    )
    audit.record("workflow.draft_created", instance=draft, after={"version": draft.version, "from": base.version})
    return draft


def update_draft(access, draft: WorkflowDefinition, data: dict) -> WorkflowDefinition:
    _require(access)
    if draft.status != WorkflowDefinition.Status.DRAFT:
        raise BusinessError("Une version active ou retirée ne se modifie pas.", code="workflow_not_draft")
    before = {"states": draft.states, "transitions": draft.transitions, "notes": draft.notes}
    if "states" in data:
        states = {
            code: {"label": str(v.get("label", "")).strip(), "pme_label": str(v.get("pme_label", "")).strip()}
            for code, v in (data["states"] or {}).items()
        }
        if set(states) != set(defaults.ACTION_STATES):
            raise ValidationError({"states": ["Les états sont fixés par le moteur : ni ajout ni suppression."]})
        draft.states = states
    if "transitions" in data:
        draft.transitions = _normalize(data["transitions"] or [])
    if "notes" in data:
        draft.notes = (data["notes"] or "").strip()
    draft.save()
    audit.record(
        "workflow.draft_updated",
        instance=draft,
        before=before,
        after={"states": draft.states, "transitions": draft.transitions, "notes": draft.notes},
    )
    return draft


@transaction.atomic
def activate(access, draft: WorkflowDefinition) -> WorkflowDefinition:
    _require(access)
    if draft.status != WorkflowDefinition.Status.DRAFT:
        raise BusinessError("Seul un brouillon peut être activé.", code="workflow_not_draft")
    errors, _ = check(draft.states, draft.transitions)
    if errors:
        raise ValidationError({"workflow": errors})
    WorkflowDefinition.objects.filter(target_type=ACTION, status=WorkflowDefinition.Status.ACTIVE).update(
        status=WorkflowDefinition.Status.RETIRED
    )
    draft.status = WorkflowDefinition.Status.ACTIVE
    draft.activated_at = timezone.now()
    draft.activated_by = access.user
    draft.save()
    audit.record("workflow.activated", instance=draft, after={"version": draft.version})
    return draft


def delete_draft(access, draft: WorkflowDefinition) -> None:
    _require(access)
    if draft.status != WorkflowDefinition.Status.DRAFT:
        raise BusinessError("Seul un brouillon peut être supprimé.", code="workflow_not_draft")
    audit.record("workflow.draft_deleted", instance=draft, before={"version": draft.version})
    draft.delete()
