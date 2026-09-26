"""Pré-diagnostic (Document 4, fonction F) : niveau proposé par critère + justification + sources.

Lancé à la soumission d'un diagnostic ; les propositions s'affichent dans l'écran de revue et ne deviennent
jamais une décision sans le conseiller (RM-05). L'issue de chaque revue est conservée (acceptée, modifiée,
écartée) : c'est la mesure de l'écart IA / humain (Document 4, § 7 et § 13).
"""

from __future__ import annotations

import json
from decimal import Decimal

from django.utils import timezone

from pme360.diagnostic.models import Answer, Criterion, Diagnostic
from pme360.documents.models import Document

from . import gateway
from .financials import display
from .models import CriterionSuggestion
from .pseudonymize import for_pme
from .schemas import PREDIAGNOSTIC_SCHEMA


def _answers(diagnostic: Diagnostic) -> dict[str, list[dict]]:
    items: dict[str, list[dict]] = {}
    for answer in Answer.objects.filter(diagnostic=diagnostic, value__isnull=False).select_related(
        "question__criterion"
    ):
        question = answer.question
        if not question.criterion_id:
            continue
        label = next((o["label"] for o in question.options if str(o["value"]) == str(answer.value)), answer.value)
        items.setdefault(question.criterion.code, []).append(
            {
                "question": question.text,
                "code": question.code,
                "answer": str(label),
                "source": answer.get_source_display(),
                "date": timezone.localtime(answer.answered_at).date().strftime("%d/%m/%Y"),
            }
        )
    return items


def criteria_payload(diagnostic: Diagnostic) -> list[dict]:
    from pme360.scoring import services as scoring

    spec, data = scoring.build_input(diagnostic, context={})
    data.reviews = {}
    result = scoring.engine.compute(spec, data)
    by_code = {c["code"]: c for c in result["criteria"]}
    metrics = {m["code"]: m for m in result["metrics"]}
    answers = _answers(diagnostic)
    rejected = set(
        Document.objects.filter(pme=diagnostic.pme, conformity_status__in=["NON_CONFORME", "INCOHERENT"]).values_list(
            "document_type__code", flat=True
        )
    )
    verified_types = {}
    for document in Document.objects.filter(
        pme=diagnostic.pme, verification_status=Document.Verification.VERIFIE_HUMAIN
    ).select_related("document_type"):
        verified_types[document.document_type.code] = document.document_type.name
    payload = []
    for criterion in Criterion.objects.filter(framework_version=diagnostic.framework_version).order_by("order"):
        computed = by_code.get(criterion.code)
        if computed is None or computed["status"] == "NON_APPLICABLE":
            continue
        criterion_metrics = [
            {**metrics[m.code], "display": display(metrics[m.code]["value"], metrics[m.code]["unit"])}
            for m in criterion.metrics.all()
            if m.code in metrics
        ]
        declared = data.declared.get(criterion.code)
        evidence = data.evidence.get(criterion.code)
        if not answers.get(criterion.code) and not criterion_metrics and evidence is None:
            continue
        expected = list(criterion.evidence_document_types or [])
        inconsistencies = [
            f"un justificatif attendu ({code}) a été refusé ou jugé incohérent" for code in expected if code in rejected
        ]
        payload.append(
            {
                "code": criterion.code,
                "name": criterion.name,
                "dimension": criterion.dimension.name,
                "rubric": list(criterion.rubric),
                "evidence_policy": criterion.evidence_policy,
                "cap": criterion.declarative_cap_level,
                "declared_level": declared.level if declared else None,
                "source": declared.source if declared else "DECLARATIF",
                "evidence_level": evidence.level if evidence else None,
                "evidence": [verified_types[t] for t in expected if t in verified_types],
                "expected_documents": expected,
                "answers": answers.get(criterion.code, []),
                "metrics": criterion_metrics,
                "inconsistencies": inconsistencies,
            }
        )
    return payload


def run(diagnostic: Diagnostic, user=None) -> int:
    """Calcule (ou recalcule) les propositions ; ne touche jamais une proposition déjà revue."""
    payload = criteria_payload(diagnostic)
    reviewed = set(
        CriterionSuggestion.objects.filter(diagnostic=diagnostic)
        .exclude(status=CriterionSuggestion.Status.PROPOSEE)
        .values_list("criterion_code", flat=True)
    )
    batches: dict[str, list[dict]] = {}
    for item in payload:
        if item["code"] not in reviewed:
            batches.setdefault(item["dimension"], []).append(item)
    pseudonymizer = for_pme(diagnostic.pme)
    created = 0
    for dimension, items in batches.items():
        codes = {item["code"] for item in items}
        public = json.dumps(
            [{k: v for k, v in item.items() if k != "dimension"} for item in items], ensure_ascii=False, default=str
        )
        outcome = gateway.run(
            prompt_code="diagnostic.prediagnostic",
            content=f"Dimension : {dimension}\n<donnees>\n{public}\n</donnees>",
            schema=PREDIAGNOSTIC_SCHEMA,
            context={"criteria": items},
            pme=diagnostic.pme,
            diagnostic=diagnostic,
            input_refs={"diagnostic": str(diagnostic.pk), "dimension": dimension, "criteria": sorted(codes)},
            pseudonymizer=pseudonymizer,
            user=user,
        )
        if not outcome.ok:
            continue
        for proposal in outcome.output["criteria"]:
            if proposal["code"] not in codes:
                continue  # jamais un critère non demandé
            CriterionSuggestion.objects.update_or_create(
                diagnostic=diagnostic,
                criterion_code=proposal["code"],
                defaults={
                    "proposed_level": proposal["proposed_level"],
                    "justification": proposal["justification"][:4000],
                    "sources": proposal["sources"][:20],
                    "confidence": Decimal(str(round(float(proposal["confidence"]), 3))),
                    "status": CriterionSuggestion.Status.PROPOSEE,
                    "analysis": outcome.analysis,
                },
            )
            created += 1
    return created


def record_review(diagnostic: Diagnostic, criterion_code: str, status: str, level_final: int | None) -> None:
    """Issue de la revue humaine d'une proposition (appelée par ``diagnostic.services``)."""
    suggestion = CriterionSuggestion.objects.filter(diagnostic=diagnostic, criterion_code=criterion_code).first()
    if suggestion is None:
        return
    if status == "NON_APPLICABLE":
        outcome = CriterionSuggestion.Status.ECARTEE
    elif level_final == suggestion.proposed_level:
        outcome = CriterionSuggestion.Status.ACCEPTEE
    else:
        outcome = CriterionSuggestion.Status.MODIFIEE
    suggestion.status = outcome
    suggestion.save(update_fields=["status", "updated_at"])
