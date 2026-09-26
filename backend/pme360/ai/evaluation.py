"""Évaluation de l'IA documentaire (Document 4, § 12) sur le jeu FICTIF ``seeds.ai_eval_dataset``.

Métriques : exactitude de classification, exactitude par champ (tous champs et champs financiers clés),
calibration de la confiance (ECE, 10 classes), taux de faux positifs du contrôle d'équilibre du bilan.
Critères d'activation : ≥ 97 % de classification, ≥ 95 % sur les champs financiers clés. Toute nouvelle version
de prompt ou de modèle est rejouée ici avant activation.
"""

from __future__ import annotations

from django.conf import settings

from seeds import ai_eval_dataset

from . import prompts
from .models import EvaluationRun
from .providers.base import ProviderError, StructuredRequest
from .providers.local import LocalProvider
from .rules import fold
from .schemas import AUTRE, CLASSIFIABLE_TYPES, CLASSIFICATION_SCHEMA, EXTRACTION_SCHEMAS, KEY_FINANCIAL_FIELDS

THRESHOLDS = {"classification_accuracy": 0.97, "key_financial_accuracy": 0.95}


def _same(expected, actual) -> bool:
    if isinstance(expected, float | int) and not isinstance(expected, bool):
        return isinstance(actual, int | float) and not isinstance(actual, bool) and abs(float(actual) - expected) < 0.5
    if isinstance(expected, str):
        return isinstance(actual, str) and fold(actual).strip() == fold(expected).strip()
    return expected == actual


def _provider(name: str):
    if name == "anthropic":
        if not settings.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY absente : évaluation externe impossible.")
        from .providers.anthropic import AnthropicProvider

        return AnthropicProvider()
    return LocalProvider()


def _model(provider, task: str) -> str:
    from .gateway import model_for

    return model_for(task) if provider.external else prompts.LOCAL_ENGINE_VERSION


def ece(pairs: list[tuple[float, bool]], bins: int = 10) -> float | None:
    """Expected Calibration Error : écart moyen pondéré entre confiance annoncée et exactitude observée."""
    if not pairs:
        return None
    total, error = len(pairs), 0.0
    for index in range(bins):
        low, high = index / bins, (index + 1) / bins
        bucket = [(c, ok) for c, ok in pairs if low <= c < high or (index == bins - 1 and c == 1.0)]
        if bucket:
            confidence = sum(c for c, _ in bucket) / len(bucket)
            accuracy = sum(ok for _, ok in bucket) / len(bucket)
            error += len(bucket) / total * abs(confidence - accuracy)
    return round(error, 4)


def evaluate(provider: str = "local", per_type: int = 12, seed: int = 2026, save: bool = True) -> EvaluationRun:
    engine = _provider(provider)
    samples = ai_eval_dataset.build(per_type=per_type, seed=seed)
    classify_prompt, extract_prompt = prompts.get("doc.classify"), prompts.get("doc.extract")
    correct_class = 0
    field_total = field_ok = key_total = key_ok = 0
    calibration: list[tuple[float, bool]] = []
    balance_checks = balance_false_positive = 0
    details = []
    types_list = (
        "; ".join(f"{code} = {label}" for code, label in CLASSIFIABLE_TYPES.items()) + f"; {AUTRE} = autre document."
    )
    for index, sample in enumerate(samples):
        content = f"Types possibles : {types_list}\n<donnees>\n{sample.text}\n</donnees>"
        try:
            classified = engine.structured(
                StructuredRequest(
                    prompt=classify_prompt,
                    model=_model(engine, "CLASSIFICATION"),
                    content=content,
                    schema=CLASSIFICATION_SCHEMA,
                    context={"text": sample.text},
                )
            ).output
        except ProviderError as exc:
            details.append({"sample": index, "type": sample.document_type, "error": str(exc)})
            continue
        ok = classified["document_type"] == sample.document_type
        correct_class += ok
        entry = {
            "sample": index,
            "type": sample.document_type,
            "classified": classified["document_type"],
            "ok": ok,
            "fields": {},
        }
        schema = EXTRACTION_SCHEMAS.get(sample.document_type)
        if schema and sample.expected:
            fields_list = "\n".join(f"- {f.name} : {f.label} ({f.type})" for f in schema.fields)
            output = engine.structured(
                StructuredRequest(
                    prompt=extract_prompt,
                    model=_model(engine, "EXTRACTION"),
                    content=f"Champs à extraire :\n{fields_list}\n<donnees>\n{sample.text}\n</donnees>",
                    schema=schema.json_schema(),
                    context={"text": sample.text, "document_type": sample.document_type},
                )
            ).output
            values, confidences = output["fields"], output.get("field_confidence", {})
            for name, expected in sample.expected.items():
                good = _same(expected, values.get(name))
                field_total += 1
                field_ok += good
                if name in KEY_FINANCIAL_FIELDS:
                    key_total += 1
                    key_ok += good
                confidence = confidences.get(name)
                if isinstance(confidence, int | float):
                    calibration.append((float(confidence), good))
                if not good:
                    entry["fields"][name] = {"expected": expected, "got": values.get(name)}
            if sample.document_type == "ETATS_FIN_SYSCOHADA":
                assets, liabilities = values.get("total_actif"), values.get("total_passif")
                if assets and liabilities:
                    balance_checks += 1
                    balance_false_positive += abs(assets - liabilities) / max(abs(assets), abs(liabilities)) > 0.005
        if not ok or entry["fields"]:
            details.append(entry)
    metrics = {
        "samples": len(samples),
        "classification_accuracy": round(correct_class / len(samples), 4),
        "field_accuracy": round(field_ok / field_total, 4) if field_total else None,
        "key_financial_accuracy": round(key_ok / key_total, 4) if key_total else None,
        "ece": ece(calibration),
        "balance_false_positive_rate": round(balance_false_positive / balance_checks, 4) if balance_checks else None,
    }
    passed = all((metrics[name] or 0) >= threshold for name, threshold in THRESHOLDS.items())
    run = EvaluationRun(
        dataset=f"{ai_eval_dataset.NAME} (graine {seed}, {per_type}/type)",
        provider=engine.name,
        models_used={"classification": _model(engine, "CLASSIFICATION"), "extraction": _model(engine, "EXTRACTION")},
        prompt_versions={code: prompts.get(code).version for code in ("doc.classify", "doc.extract")},
        metrics=metrics,
        thresholds=THRESHOLDS,
        passed=passed,
        details=details[:200],
    )
    if save:
        run.save()
    return run
