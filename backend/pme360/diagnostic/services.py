"""Cycle de vie d'un diagnostic (Document 7, § 2.1) et questionnaire adaptatif (Document 5, § 6)."""

from __future__ import annotations

from datetime import date

from django.db import IntegrityError
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from pme360.accounts.access import AccessContext
from pme360.audit import services as audit
from pme360.core import events, jsonlogic
from pme360.core.exceptions import BusinessError, Conflict
from pme360.pmes import services as pme_services
from pme360.pmes.models import Pme
from pme360.scoring import services as scoring

from .models import (
    Answer,
    AnswerHistory,
    Criterion,
    CriterionAssessment,
    Diagnostic,
    Dimension,
    FrameworkVersion,
    Question,
)

SUBMIT_MIN_COMPLETION = 0.70  # Document 7, § 2.1 : ≥ 70 % des questions obligatoires renseignées
PROFILE_STEP = "PROFIL"


def published_version() -> FrameworkVersion:
    version = (
        FrameworkVersion.objects.filter(status=FrameworkVersion.Status.PUBLISHED)
        .select_related("framework")
        .order_by("-published_at")
        .first()
    )
    if version is None:
        raise BusinessError("Aucun référentiel de diagnostic publié dans l'organisation.", code="no_framework")
    return version


def _staff(access: AccessContext) -> bool:
    return not access.is_pme_user


def _answer_source(access: AccessContext) -> str:
    return Answer.Source.PME if access.is_pme_user else Answer.Source.CONSEILLER


def start_diagnostic(access: AccessContext, pme: Pme, diagnostic_type: str, reference_date: date | None = None):
    version = published_version()
    previous = Diagnostic.objects.filter(pme=pme, status=Diagnostic.Status.VALIDE).order_by("-reference_date").first()
    if diagnostic_type == Diagnostic.Type.INITIAL and previous:
        raise BusinessError(
            "Cette PME a déjà un diagnostic validé : lancez un diagnostic de suivi ou une réévaluation.",
            code="initial_exists",
        )
    if diagnostic_type != Diagnostic.Type.INITIAL and not previous:
        raise BusinessError(
            "Le premier diagnostic d'une PME est obligatoirement un diagnostic initial.", code="initial_required"
        )
    try:
        diagnostic = Diagnostic.objects.create(
            pme=pme,
            framework_version=version,
            type=diagnostic_type,
            reference_date=reference_date or timezone.localdate(),
            status=Diagnostic.Status.EN_COLLECTE,
            lead_advisor=access.user if _staff(access) else None,
            previous=previous,
            created_by=access.user,
        )
    except IntegrityError as exc:
        raise Conflict("Un diagnostic est déjà en cours pour cette PME.", code="diagnostic_open") from exc
    if previous and diagnostic_type in (Diagnostic.Type.SUIVI, Diagnostic.Type.CLOTURE):
        _prefill_from(previous, diagnostic, version)
    if pme.lifecycle_status in (Pme.LifecycleStatus.PROSPECT, Pme.LifecycleStatus.ONBOARDING):
        if pme.lifecycle_status == Pme.LifecycleStatus.PROSPECT:
            pme_services.transition(pme, Pme.LifecycleStatus.ONBOARDING, access.user, reason="Démarrage du diagnostic")
        pme_services.transition(
            pme, Pme.LifecycleStatus.DIAGNOSTIC_EN_COURS, access.user, reason="Démarrage du diagnostic"
        )
    audit.record(
        "diagnostic.started",
        instance=diagnostic,
        pme_id=pme.pk,
        after={
            "type": diagnostic_type,
            "framework_version": version.version,
            "reference_date": diagnostic.reference_date,
        },
    )
    return diagnostic


def _prefill_from(previous: Diagnostic, diagnostic: Diagnostic, version: FrameworkVersion) -> None:
    """Diagnostic de suivi pré-rempli : la PME confirme ou modifie (Document 7, § 6)."""
    questions = {q.code: q for q in Question.objects.filter(framework_version=version)}
    now = timezone.now()
    Answer.objects.bulk_create(
        [
            Answer(
                diagnostic=diagnostic,
                question=questions[a.question.code],
                value=a.value,
                answered_by=a.answered_by,
                answered_at=now,
                source=Answer.Source.REPRISE,
            )
            for a in Answer.objects.filter(diagnostic=previous).select_related("question")
            if a.question.code in questions
        ]
    )


# --- Questionnaire ------------------------------------------------------------------------------------------


def questionnaire(diagnostic: Diagnostic, access: AccessContext) -> dict:
    version = diagnostic.framework_version
    _, metas = scoring.load_framework(version)
    answers = scoring.answers_by_code(diagnostic)
    profile = scoring.build_profile(diagnostic, answers, metas)
    context = {**profile, "answers": {code: a.value for code, a in answers.items()}}
    show_levels = _staff(access)
    audiences = {"PME", "LES_DEUX"} if access.is_pme_user else {"PME", "CONSEILLER", "LES_DEUX"}

    criteria = {c.pk: c for c in Criterion.objects.filter(framework_version=version)}
    dimensions = list(Dimension.objects.filter(framework_version=version).order_by("order"))
    questions = list(Question.objects.filter(framework_version=version).order_by("order"))

    def applicable(criterion: Criterion | None) -> bool:
        if criterion is None:
            return True
        if criterion.sector_module and criterion.sector_module != profile.get("sector"):
            return False
        return not criterion.applicability or bool(jsonlogic.evaluate(criterion.applicability, profile))

    steps: dict[str, dict] = {
        PROFILE_STEP: {
            "code": PROFILE_STEP,
            "title": "Votre entreprise",
            "description": "Quelques informations pour adapter le questionnaire.",
            "questions": [],
        }
    }
    for dimension in dimensions:
        steps[dimension.code] = {
            "code": dimension.code,
            "title": dimension.name,
            "description": dimension.description,
            "questions": [],
        }
    dimension_codes = {d.pk: d.code for d in dimensions}
    required = answered_required = answered_total = 0
    for question in questions:
        criterion = criteria.get(question.criterion_id)
        if question.target_audience not in audiences or not applicable(criterion):
            continue
        if question.visibility and not jsonlogic.evaluate(question.visibility, context):
            continue
        answer = answers.get(question.code)
        value = answer.value if answer else None
        if question.feeds.startswith("profile.") and value is None:
            value = profile.get(question.feeds.split(".", 1)[1])  # valeur connue de la fiche PME, à confirmer
        if question.is_required:
            required += 1
            answered_required += answer is not None and answer.value is not None
        answered_total += answer is not None and answer.value is not None
        step = (
            PROFILE_STEP
            if question.feeds.startswith("profile.")
            else dimension_codes[criterion.dimension_id if criterion else question.dimension_id]
        )
        steps[step]["questions"].append(
            {
                "id": question.pk,
                "code": question.code,
                "text": question.text,
                "help_text": question.help_text,
                "why_text": question.why_text,
                "type": question.type,
                "required": question.is_required,
                "options": [
                    {"value": o["value"], "label": o["label"], **({"level": o["level"]} if show_levels else {})}
                    for o in question.options
                ],
                "value": value,
                "answered": answer is not None and answer.value is not None,
                "source": answer.source if answer else None,
                "evidence_hint": question.evidence_hint,
                "criterion": criterion.code if criterion else None,
                "is_critical": bool(criterion and criterion.is_critical),
            }
        )
    return {
        "diagnostic": diagnostic,
        "editable": can_edit_answers(diagnostic, access),
        "progress": {
            "required": required,
            "required_answered": answered_required,
            "answered": answered_total,
            "completion": round(answered_required / required, 3) if required else 1.0,
            "submit_threshold": SUBMIT_MIN_COMPLETION,
        },
        "steps": [step for step in steps.values() if step["questions"]],
    }


def can_edit_answers(diagnostic: Diagnostic, access: AccessContext) -> bool:
    if not access.has("diagnostic.answer"):
        return False
    if diagnostic.status == Diagnostic.Status.EN_COLLECTE:
        return True
    return diagnostic.status == Diagnostic.Status.EN_REVUE and _staff(access)


def _clean_value(question: Question, value):
    if value is None or value == "":
        return None
    kind = question.type
    if kind == Question.Type.SINGLE:
        allowed = {str(o["value"]) for o in question.options}
        if str(value) not in allowed:
            raise ValidationError({question.code: ["Réponse non proposée."]})
        return str(value)
    if kind == Question.Type.BOOLEAN:
        if not isinstance(value, bool):
            raise ValidationError({question.code: ["Répondez par oui ou par non."]})
        return value
    if kind in (Question.Type.NUMBER, Question.Type.AMOUNT, Question.Type.PERCENT):
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValidationError({question.code: ["Un nombre est attendu."]})
        if kind == Question.Type.NUMBER and value < 0:
            raise ValidationError({question.code: ["La valeur ne peut pas être négative."]})
        if kind == Question.Type.PERCENT and not 0 <= value <= 100:
            raise ValidationError({question.code: ["Un pourcentage entre 0 et 100 est attendu."]})
        if abs(value) > 1e15:
            raise ValidationError({question.code: ["Montant hors limites."]})
        return value
    text = str(value).strip()
    if len(text) > 2000:
        raise ValidationError({question.code: ["2 000 caractères au maximum."]})
    return text


def save_answers(diagnostic: Diagnostic, access: AccessContext, items: list[dict]) -> int:
    """Enregistre un lot de réponses (sauvegarde automatique) ; l'historique conserve les valeurs précédentes."""
    if not can_edit_answers(diagnostic, access):
        raise PermissionDenied("Le questionnaire n'est pas modifiable dans l'état actuel du diagnostic.")
    codes = [item["question"] for item in items]
    questions = {
        q.code: q for q in Question.objects.filter(framework_version=diagnostic.framework_version, code__in=codes)
    }
    existing = {
        a.question.code: a
        for a in Answer.objects.filter(diagnostic=diagnostic, question__code__in=codes).select_related("question")
    }
    now = timezone.now()
    source = _answer_source(access)
    changed = 0
    for item in items:
        question = questions.get(item["question"])
        if question is None:
            raise ValidationError({item["question"]: ["Question inconnue pour ce référentiel."]})
        if access.is_pme_user and question.target_audience == Question.Audience.CONSEILLER:
            raise PermissionDenied("Cette question est réservée au conseiller.")
        value = _clean_value(question, item.get("value"))
        answer = existing.get(question.code)
        if answer is None:
            if value is None:
                continue
            Answer.objects.create(
                diagnostic=diagnostic,
                question=question,
                value=value,
                answered_by=access.user,
                answered_at=now,
                source=source,
            )
            changed += 1
        elif answer.value != value or answer.source != source:
            AnswerHistory.objects.create(
                answer=answer,
                value=answer.value,
                answered_by=answer.answered_by,
                answered_at=answer.answered_at,
                source=answer.source,
            )
            answer.value, answer.answered_by, answer.answered_at, answer.source = value, access.user, now, source
            answer.save(update_fields=["value", "answered_by", "answered_at", "source", "updated_at"])
            changed += 1
    if changed:
        pme_services.touch(diagnostic.pme)
    return changed


def submit(diagnostic: Diagnostic, access: AccessContext) -> Diagnostic:
    if diagnostic.status != Diagnostic.Status.EN_COLLECTE:
        raise BusinessError("Seul un diagnostic en collecte peut être soumis.", code="invalid_status")
    progress = questionnaire(diagnostic, access)["progress"]
    staff_progress = progress if _staff(access) else None
    if progress["completion"] < SUBMIT_MIN_COMPLETION:
        raise BusinessError(
            f"Complétez au moins {round(SUBMIT_MIN_COMPLETION * 100)} % des questions obligatoires avant de soumettre.",
            code="incomplete",
            completion=progress["completion"],
        )
    # Phase 4 : ANALYSE_IA (pré-diagnostic). Sans IA active, passage direct en revue (Document 7, § 2.1).
    diagnostic.status = Diagnostic.Status.EN_REVUE
    diagnostic.submitted_at = timezone.now()
    diagnostic.save(update_fields=["status", "submitted_at", "updated_at"])
    audit.record(
        "diagnostic.submitted",
        instance=diagnostic,
        pme_id=diagnostic.pme_id,
        after={"completion": progress["completion"], "by_staff": staff_progress is not None},
    )
    events.emit("diagnostic.submitted", pme_id=str(diagnostic.pme_id), diagnostic_id=str(diagnostic.pk))
    return diagnostic


def reopen(diagnostic: Diagnostic, access: AccessContext, reason: str) -> Diagnostic:
    if diagnostic.status != Diagnostic.Status.EN_REVUE:
        raise BusinessError("Seul un diagnostic en revue peut être renvoyé en collecte.", code="invalid_status")
    if not reason.strip():
        raise ValidationError({"reason": ["Motif obligatoire (informations manquantes)."]})
    diagnostic.status = Diagnostic.Status.EN_COLLECTE
    diagnostic.save(update_fields=["status", "updated_at"])
    audit.record("diagnostic.reopened", instance=diagnostic, pme_id=diagnostic.pme_id, after={"reason": reason})
    return diagnostic


# --- Revue et validation ------------------------------------------------------------------------------------


def review_criterion(
    diagnostic: Diagnostic,
    access: AccessContext,
    criterion_code: str,
    *,
    status: str,
    level_final: int | None,
    comment: str,
    corroborated: bool,
) -> CriterionAssessment:
    if diagnostic.status != Diagnostic.Status.EN_REVUE:
        raise BusinessError("La revue n'est possible que pour un diagnostic soumis.", code="invalid_status")
    criterion = Criterion.objects.filter(framework_version=diagnostic.framework_version, code=criterion_code).first()
    if criterion is None:
        raise ValidationError({"criterion": ["Critère inconnu."]})
    _, data = scoring.build_input(diagnostic, context={})
    declared_item = data.declared.get(criterion_code)
    declared = declared_item.level if declared_item else None
    existing = CriterionAssessment.objects.filter(diagnostic=diagnostic, criterion=criterion).first()
    comment = comment.strip()
    if status == CriterionAssessment.Status.VALIDE:
        if criterion.metrics.exists():
            level_final = None
        elif declared is None:
            raise ValidationError({"level_final": ["Aucun niveau déclaré : choisissez un niveau (modification)."]})
        else:
            level_final = declared
    elif status == CriterionAssessment.Status.MODIFIE:
        if level_final is None or not 0 <= level_final <= 4:
            raise ValidationError({"level_final": ["Niveau entre 0 et 4 attendu."]})
        if not comment:
            raise ValidationError({"comment": ["Toute modification doit être justifiée (RM-06)."]})
    elif status == CriterionAssessment.Status.NON_APPLICABLE:
        if not comment:
            raise ValidationError({"comment": ["Justifiez la non-applicabilité."]})
        level_final = None
    before = None
    if existing:
        before = {"status": existing.status, "level_final": existing.level_final, "comment": existing.comment}
    assessment, _ = CriterionAssessment.objects.update_or_create(
        diagnostic=diagnostic,
        criterion=criterion,
        defaults={
            "status": status,
            "level_declared": declared,
            "level_final": level_final,
            "comment": comment,
            "corroborated": corroborated,
            "reviewer": access.user,
            "reviewed_at": timezone.now(),
        },
    )
    audit.record(
        "diagnostic.criterion_reviewed",
        instance=assessment,
        pme_id=diagnostic.pme_id,
        before=before,
        after={
            "criterion": criterion_code,
            "status": status,
            "level_declared": declared,
            "level_final": level_final,
            "comment": comment,
            "corroborated": corroborated,
        },
    )
    return assessment


def accept_remaining(diagnostic: Diagnostic, access: AccessContext) -> int:
    """Validation en lot des critères évalués non encore revus (confirmation explicite côté interface)."""
    if diagnostic.status != Diagnostic.Status.EN_REVUE:
        raise BusinessError("La revue n'est possible que pour un diagnostic soumis.", code="invalid_status")
    result = scoring.compute(diagnostic)
    reviewed = set(CriterionAssessment.objects.filter(diagnostic=diagnostic).values_list("criterion__code", flat=True))
    criteria = {c.code: c for c in Criterion.objects.filter(framework_version=diagnostic.framework_version)}
    now = timezone.now()
    created = [
        CriterionAssessment(
            diagnostic=diagnostic,
            criterion=criteria[c["code"]],
            status=CriterionAssessment.Status.VALIDE,
            level_declared=c["level_uncapped"],
            level_final=c["level_uncapped"],
            reviewer=access.user,
            reviewed_at=now,
        )
        for c in result["criteria"]
        if c["status"] == "EVALUE" and c["code"] not in reviewed
    ]
    CriterionAssessment.objects.bulk_create(created)
    if created:
        audit.record(
            "diagnostic.bulk_accepted",
            instance=diagnostic,
            pme_id=diagnostic.pme_id,
            after={"criteria": [a.criterion.code for a in created]},
        )
    return len(created)


def review_status(diagnostic: Diagnostic, result: dict | None = None) -> dict:
    result = result or scoring.compute(diagnostic)
    reviewed = set(CriterionAssessment.objects.filter(diagnostic=diagnostic).values_list("criterion__code", flat=True))
    to_review = [c["code"] for c in result["criteria"] if c["status"] == "EVALUE" and c["code"] not in reviewed]
    return {"reviewed": len(reviewed), "pending": to_review}


def validate(diagnostic: Diagnostic, access: AccessContext):
    """Validation du diagnostic → snapshot figé (RM-04, RM-05)."""
    if diagnostic.status != Diagnostic.Status.EN_REVUE:
        raise BusinessError("Seul un diagnostic en revue peut être validé.", code="invalid_status")
    status = review_status(diagnostic)
    if status["pending"]:
        raise BusinessError(
            "Tous les critères évalués doivent être revus (ou acceptés en lot) avant la validation.",
            code="review_incomplete",
            pending=status["pending"],
        )
    diagnostic.status = Diagnostic.Status.VALIDE
    diagnostic.validated_at = timezone.now()
    diagnostic.validated_by = access.user
    diagnostic.save(update_fields=["status", "validated_at", "validated_by", "updated_at"])
    snapshot = scoring.freeze(diagnostic)
    audit.record(
        "diagnostic.validated",
        instance=diagnostic,
        pme_id=diagnostic.pme_id,
        after={"snapshot": str(snapshot.pk), "global_score": snapshot.result["global_score"]},
    )
    events.emit("diagnostic.validated", pme_id=str(diagnostic.pme_id), diagnostic_id=str(diagnostic.pk))
    pme_services.touch(diagnostic.pme)
    return snapshot


def cancel(diagnostic: Diagnostic, reason: str) -> Diagnostic:
    if not diagnostic.is_open:
        raise BusinessError("Ce diagnostic est déjà clos.", code="invalid_status")
    if not reason.strip():
        raise ValidationError({"reason": ["Motif obligatoire."]})
    diagnostic.status = Diagnostic.Status.ANNULE
    diagnostic.cancel_reason = reason.strip()
    diagnostic.save(update_fields=["status", "cancel_reason", "updated_at"])
    audit.record("diagnostic.cancelled", instance=diagnostic, pme_id=diagnostic.pme_id, after={"reason": reason})
    return diagnostic
