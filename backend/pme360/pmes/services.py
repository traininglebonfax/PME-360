"""Règles métier des PME : création, doublons, cycle de vie, dirigeants, assignations (Document 1, § 4 et § 7)."""

from __future__ import annotations

import re
import uuid
from decimal import Decimal

from django.contrib.postgres.search import TrigramSimilarity
from django.db import IntegrityError
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from pme360.accounts.access import AccessContext, active_membership_q
from pme360.accounts.catalog import ADVISOR_ROLE_CODES
from pme360.accounts.models import User, UserMembership
from pme360.audit import services as audit
from pme360.core import events
from pme360.core.exceptions import BusinessError, Conflict
from pme360.core.tenancy import current_org_id
from pme360.organizations.models import Cohort, Organization

from .models import Pme, PmeAssignment, PmeEnrollment, PmePerson

LIFECYCLE_TRANSITIONS: dict[str, set[str]] = {
    Pme.LifecycleStatus.PROSPECT: {Pme.LifecycleStatus.ONBOARDING, Pme.LifecycleStatus.SORTIE},
    Pme.LifecycleStatus.ONBOARDING: {Pme.LifecycleStatus.DIAGNOSTIC_EN_COURS, Pme.LifecycleStatus.SORTIE},
    Pme.LifecycleStatus.DIAGNOSTIC_EN_COURS: {Pme.LifecycleStatus.ACCOMPAGNEMENT_ACTIF, Pme.LifecycleStatus.SORTIE},
    Pme.LifecycleStatus.ACCOMPAGNEMENT_ACTIF: {Pme.LifecycleStatus.SUSPENDU, Pme.LifecycleStatus.SORTIE},
    Pme.LifecycleStatus.SUSPENDU: {Pme.LifecycleStatus.ACCOMPAGNEMENT_ACTIF, Pme.LifecycleStatus.SORTIE},
    Pme.LifecycleStatus.SORTIE: {Pme.LifecycleStatus.SUIVI_POST_PROGRAMME},
    Pme.LifecycleStatus.SUIVI_POST_PROGRAMME: set(),
}

# Champs modifiables par la PME elle-même (permission pme.update_identity) : coordonnées uniquement.
IDENTITY_FIELDS = {"trade_name", "phone", "email", "website", "address", "commune"}
AUDITED_FIELDS = [
    "legal_name",
    "trade_name",
    "legal_form",
    "rccm_number",
    "ncc",
    "cnps_employer_number",
    "creation_date",
    "sector",
    "region",
    "commune",
    "address",
    "phone",
    "email",
    "website",
    "headcount",
    "size_category",
]
PERSON_FIELDS = ["full_name", "role", "share_pct", "is_primary_contact", "phone", "email", "gender", "birth_year"]


# --- Identifiants et doublons ---------------------------------------------------------------------------------


def normalize_rccm(value: str) -> str:
    """« ci abj 2016 b 12345 » et « CI-ABJ-2016-B-12345 » → « CI-ABJ-2016-B-12345 »."""
    return re.sub(r"[\s\-_/.]+", "-", (value or "").strip().upper()).strip("-")


def normalize_compact(value: str) -> str:
    """NCC, n° CNPS : majuscules sans séparateurs."""
    return re.sub(r"[\s\-_/.]+", "", (value or "").strip().upper())


def find_duplicates(
    *,
    legal_name: str = "",
    rccm_number: str = "",
    ncc: str = "",
    exclude_id: uuid.UUID | None = None,
    access: AccessContext | None = None,
) -> list[dict]:
    """Doublons potentiels dans toute l'organisation : identifiant identique ou raison sociale approchante."""
    organization = Organization.objects.get(pk=current_org_id())
    threshold = organization.setting("duplicate_name_similarity")
    candidates: dict[uuid.UUID, dict] = {}

    def add(pme: Pme, reason: str, similarity: float | None = None) -> None:
        entry = candidates.setdefault(
            pme.pk, {"id": pme.pk, "legal_name": pme.legal_name, "rccm_number": pme.rccm_number, "reasons": []}
        )
        entry["reasons"].append(reason)
        if similarity is not None:
            entry["similarity"] = round(similarity, 2)

    base = Pme.objects.exclude(pk=exclude_id) if exclude_id else Pme.objects.all()
    if rccm_number:
        for pme in base.filter(rccm_number=normalize_rccm(rccm_number)):
            add(pme, "rccm")
    if ncc:
        for pme in base.filter(ncc=normalize_compact(ncc)):
            add(pme, "ncc")
    if legal_name and len(legal_name.strip()) >= 3:
        similar = (
            base.annotate(similarity=TrigramSimilarity("legal_name", legal_name.strip()))
            .filter(similarity__gte=threshold)
            .order_by("-similarity")[:10]
        )
        for pme in similar:
            add(pme, "name", pme.similarity)

    visible = set()
    if access is not None and candidates:
        visible = set(access.pme_queryset(Pme.objects.filter(pk__in=candidates)).values_list("pk", flat=True))
    for entry in candidates.values():
        entry["accessible"] = entry["id"] in visible
    return list(candidates.values())


# --- Création / modification ----------------------------------------------------------------------------------


def _check_advisor(user_id: uuid.UUID) -> User:
    advisor = User.objects.filter(
        pk=user_id,
        is_active=True,
        memberships__in=UserMembership.objects.filter(active_membership_q(), role__code__in=ADVISOR_ROLE_CODES),
    ).first()
    if advisor is None:
        raise ValidationError({"advisor_id": ["Cet utilisateur ne peut pas suivre de PME dans l'organisation."]})
    return advisor


def touch(pme: Pme) -> None:
    Pme.objects.filter(pk=pme.pk).update(last_activity_at=timezone.now())


def create_pme(
    access: AccessContext,
    data: dict,
    *,
    primary_person: dict | None = None,
    advisor_id: uuid.UUID | None = None,
    cohort_id: uuid.UUID | None = None,
    confirm_duplicates: bool = False,
    start_onboarding: bool = False,
) -> Pme:
    user = access.user
    data = {**data}
    data["rccm_number"] = normalize_rccm(data.get("rccm_number", ""))
    data["ncc"] = normalize_compact(data.get("ncc", ""))
    data["cnps_employer_number"] = normalize_compact(data.get("cnps_employer_number", ""))

    duplicates = find_duplicates(
        legal_name=data["legal_name"], rccm_number=data["rccm_number"], ncc=data["ncc"], access=access
    )
    blocking = [d for d in duplicates if {"rccm", "ncc"} & set(d["reasons"])]
    if blocking:
        raise Conflict(
            "Une PME portant le même numéro RCCM ou NCC existe déjà dans l'organisation.",
            code="duplicate_identifier",
            duplicates=_json(blocking),
        )
    if duplicates and not confirm_duplicates:
        raise Conflict(
            "Des PME à la raison sociale proche existent déjà. Vérifiez puis confirmez la création.",
            code="possible_duplicates",
            duplicates=_json(duplicates),
        )

    advisor = None
    if advisor_id and advisor_id != user.pk:
        if not access.has("pme.assign"):
            raise PermissionDenied("Vous ne pouvez pas assigner un autre conseiller.")
        advisor = _check_advisor(advisor_id)
    elif advisor_id == user.pk or "CONSEILLER" in access.role_codes:
        # Un conseiller qui crée une PME la suit : sinon elle sortirait immédiatement de son portefeuille.
        advisor = _check_advisor(user.pk)

    cohort = Cohort.objects.filter(pk=cohort_id).first() if cohort_id else None
    if cohort_id and cohort is None:
        raise ValidationError({"cohort_id": ["Cohorte introuvable."]})

    now = timezone.now()
    try:
        pme = Pme.objects.create(**data, created_by=user, updated_by=user, last_activity_at=now)
    except IntegrityError as exc:  # course entre deux créations simultanées
        raise Conflict("Une PME portant le même identifiant existe déjà.", code="duplicate_identifier") from exc
    audit.record("pme.created", instance=pme, pme_id=pme.pk, after=audit.snapshot(pme, AUDITED_FIELDS))

    if primary_person:
        add_person(pme, {**primary_person, "is_primary_contact": True}, user)
    if advisor:
        assign(pme, advisor, PmeAssignment.RoleInPme.CONSEILLER_PRINCIPAL, user)
    if cohort:
        enrollment = PmeEnrollment.objects.create(
            pme=pme, cohort=cohort, enrolled_at=timezone.localdate(), created_by=user
        )
        audit.record("pme.enrolled", instance=enrollment, pme_id=pme.pk, after={"cohort": str(cohort)})
    if start_onboarding:
        transition(pme, Pme.LifecycleStatus.ONBOARDING, user)
    events.emit("pme.created", pme_id=str(pme.pk))
    return pme


def update_pme(access: AccessContext, pme: Pme, data: dict) -> Pme:
    if not access.has("pme.update"):
        forbidden = set(data) - IDENTITY_FIELDS
        if not access.has("pme.update_identity") or forbidden:
            raise PermissionDenied(
                "Vous pouvez seulement modifier les coordonnées de l'entreprise."
                if access.has("pme.update_identity")
                else None
            )
    if "rccm_number" in data:
        data["rccm_number"] = normalize_rccm(data["rccm_number"])
    if "ncc" in data:
        data["ncc"] = normalize_compact(data["ncc"])
    if "cnps_employer_number" in data:
        data["cnps_employer_number"] = normalize_compact(data["cnps_employer_number"])
    if data.get("rccm_number") or data.get("ncc"):
        blocking = [
            d
            for d in find_duplicates(
                rccm_number=data.get("rccm_number", ""), ncc=data.get("ncc", ""), exclude_id=pme.pk
            )
            if {"rccm", "ncc"} & set(d["reasons"])
        ]
        if blocking:
            raise Conflict(
                "Ce numéro est déjà utilisé par une autre PME.", code="duplicate_identifier", duplicates=_json(blocking)
            )

    before = audit.snapshot(pme, AUDITED_FIELDS)
    for field, value in data.items():
        setattr(pme, field, value)
    pme.updated_by = access.user
    pme.last_activity_at = timezone.now()
    pme.save()
    changed_before, changed_after = audit.diff(before, audit.snapshot(pme, AUDITED_FIELDS))
    if changed_after:
        audit.record("pme.updated", instance=pme, pme_id=pme.pk, before=changed_before, after=changed_after)
    return pme


def transition(pme: Pme, to_status: str, user, *, reason: str = "", exit_reason: str = "") -> Pme:
    allowed = LIFECYCLE_TRANSITIONS.get(pme.lifecycle_status, set())
    if to_status not in allowed:
        raise BusinessError(
            f"Transition impossible : {pme.get_lifecycle_status_display()} → {Pme.LifecycleStatus(to_status).label}.",
            code="invalid_transition",
            allowed=sorted(allowed),
        )
    if to_status == Pme.LifecycleStatus.SORTIE and not exit_reason:
        raise ValidationError({"exit_reason": ["Motif de sortie obligatoire."]})
    before = {"lifecycle_status": pme.lifecycle_status}
    now = timezone.now()
    pme.lifecycle_status = to_status
    if to_status == Pme.LifecycleStatus.ONBOARDING and pme.onboarding_started_at is None:
        pme.onboarding_started_at = now
    if to_status == Pme.LifecycleStatus.SORTIE:
        pme.exited_at = now
        pme.exit_reason = exit_reason
        PmeEnrollment.objects.filter(pme=pme, exited_at__isnull=True).update(
            exited_at=timezone.localdate(), exit_reason=Pme.ExitReason(exit_reason).label
        )
    pme.last_activity_at = now
    pme.updated_by = user
    pme.save()
    audit.record(
        "pme.lifecycle_changed",
        instance=pme,
        pme_id=pme.pk,
        before=before,
        after={"lifecycle_status": to_status, "reason": reason, "exit_reason": exit_reason},
    )
    events.emit(
        "pme.lifecycle_changed", pme_id=str(pme.pk), from_status=before["lifecycle_status"], to_status=to_status
    )
    # Échéances documentaires ouvertes tout de suite : la PME peut déposer ses justificatifs dès le diagnostic.
    from pme360.compliance import services as compliance

    compliance.provision_obligations(pme, timezone.localdate())
    return pme


# --- Dirigeants -----------------------------------------------------------------------------------------------


def _check_shares(pme: Pme, share_pct: Decimal | None, exclude_id: uuid.UUID | None = None) -> None:
    if share_pct is None:
        return
    share_pct = Decimal(str(share_pct))
    others = PmePerson.objects.filter(pme=pme).exclude(pk=exclude_id).aggregate(total=Sum("share_pct"))["total"] or 0
    if others + share_pct > 100:
        raise ValidationError({"share_pct": [f"La somme des parts dépasserait 100 % (déjà attribué : {others} %)."]})


def _set_primary(pme: Pme, person_id: uuid.UUID | None) -> None:
    PmePerson.objects.filter(pme=pme, is_primary_contact=True).exclude(pk=person_id).update(is_primary_contact=False)


def add_person(pme: Pme, data: dict, user) -> PmePerson:
    if data.get("share_pct") is not None:
        data = {**data, "share_pct": Decimal(str(data["share_pct"]))}
    _check_shares(pme, data.get("share_pct"))
    if data.get("is_primary_contact"):
        _set_primary(pme, None)
    person = PmePerson.objects.create(pme=pme, created_by=user, updated_by=user, **data)
    audit.record("pme.person_added", instance=person, pme_id=pme.pk, after=audit.snapshot(person, PERSON_FIELDS))
    touch(pme)
    return person


def update_person(person: PmePerson, data: dict, user) -> PmePerson:
    _check_shares(person.pme, data.get("share_pct", person.share_pct), exclude_id=person.pk)
    if data.get("is_primary_contact"):
        _set_primary(person.pme, person.pk)
    before = audit.snapshot(person, PERSON_FIELDS)
    for field, value in data.items():
        setattr(person, field, value)
    person.updated_by = user
    person.save()
    changed_before, changed_after = audit.diff(before, audit.snapshot(person, PERSON_FIELDS))
    audit.record(
        "pme.person_updated", instance=person, pme_id=person.pme_id, before=changed_before, after=changed_after
    )
    touch(person.pme)
    return person


def remove_person(person: PmePerson) -> None:
    audit.record(
        "pme.person_removed", instance=person, pme_id=person.pme_id, before=audit.snapshot(person, PERSON_FIELDS)
    )
    pme = person.pme
    person.delete()
    touch(pme)


# --- Assignations ---------------------------------------------------------------------------------------------


def assign(pme: Pme, advisor: User, role_in_pme: str, user) -> PmeAssignment:
    today = timezone.localdate()
    active = PmeAssignment.objects.filter(pme=pme, end_date__isnull=True)
    if active.filter(user=advisor, role_in_pme=role_in_pme).exists():
        raise Conflict("Cet utilisateur suit déjà cette PME avec ce rôle.", code="already_assigned")
    if role_in_pme == PmeAssignment.RoleInPme.CONSEILLER_PRINCIPAL:
        for previous in active.filter(role_in_pme=role_in_pme):
            end_assignment(previous, user)
    assignment = PmeAssignment.objects.create(
        pme=pme, user=advisor, role_in_pme=role_in_pme, start_date=today, created_by=user
    )
    audit.record(
        "pme.assigned",
        instance=assignment,
        pme_id=pme.pk,
        after={"user_id": advisor.pk, "user": advisor.full_name, "role_in_pme": role_in_pme},
    )
    touch(pme)
    return assignment


def assign_by_id(pme: Pme, user_id: uuid.UUID, role_in_pme: str, user) -> PmeAssignment:
    return assign(pme, _check_advisor(user_id), role_in_pme, user)


def end_assignment(assignment: PmeAssignment, user) -> PmeAssignment:
    if assignment.end_date is not None:
        raise Conflict("Cette assignation est déjà terminée.", code="assignment_ended")
    assignment.end_date = timezone.localdate()
    assignment.updated_by = user
    assignment.save(update_fields=["end_date", "updated_by", "updated_at"])
    audit.record(
        "pme.unassigned",
        instance=assignment,
        pme_id=assignment.pme_id,
        after={"user_id": assignment.user_id, "role_in_pme": assignment.role_in_pme},
    )
    return assignment


def _json(value):
    return audit.to_json(value)
