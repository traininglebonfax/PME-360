"""Passerelle IA (Document 4, § 3) : point d'entrée UNIQUE de tout appel à un modèle.

1. Politique : IA externe seulement si le fournisseur est configuré, si le tenant l'autorise
   (``organization.ai_external_allowed``) et si le type de document n'est pas sensible ; sinon moteur local.
2. Pseudonymisation avant l'envoi, ré-injection au retour.
3. Routage des modèles par tâche (``PME360_AI_MODELS``).
4. Sortie validée par JSON Schema : une nouvelle tentative au plus, puis vérification humaine.
5. Traçabilité systématique (``AiAnalysis``).
6. Résilience : disjoncteur ; fournisseur indisponible → moteur local ou analyse différée.
7. Budget mensuel de jetons par tenant, alerte à 80 %.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from decimal import Decimal

import jsonschema
import structlog
from django.conf import settings
from django.core.cache import cache
from django.db.models import Sum
from django.utils import timezone

from pme360.core.tenancy import current_org_id

from . import prompts
from .models import AiAnalysis
from .providers.base import ProviderError, StructuredRequest
from .providers.local import LocalProvider
from .pseudonymize import Pseudonymizer

logger = structlog.get_logger(__name__)

TASK_TIER = {
    "CLASSIFICATION": "fast",
    "CONTROLE": "fast",
    "EXTRACTION": "standard",
    "ANALYSE_FINANCIERE": "reasoning",
    "PRE_DIAGNOSTIC": "reasoning",
    "ASK_AI": "reasoning",
}
BREAKER_KEY = "pme360:ai:breaker:{provider}"
BREAKER_THRESHOLD = 5
BREAKER_COOLDOWN = 300
BUDGET_WARNING_EVENT = "AI_BUDGET_WARNING"


@dataclass
class Outcome:
    status: str
    output: dict | None
    analysis: AiAnalysis
    provider: str
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == AiAnalysis.Status.SUCCES


def model_for(task: str) -> str:
    return settings.PME360_AI_MODELS[TASK_TIER[task]]


def external_provider():
    """Fournisseur externe configuré, ou ``None`` (moteur local uniquement)."""
    if settings.PME360_AI_PROVIDER == "anthropic" and settings.ANTHROPIC_API_KEY:
        from .providers.anthropic import AnthropicProvider

        return AnthropicProvider()
    return _test_provider


_test_provider = None  # remplacé par les tests (fournisseur scripté)


def set_test_provider(provider) -> None:
    global _test_provider
    _test_provider = provider


def breaker_open(provider_name: str) -> bool:
    return cache.get(BREAKER_KEY.format(provider=provider_name), 0) >= BREAKER_THRESHOLD


def _breaker_failure(provider_name: str) -> None:
    key = BREAKER_KEY.format(provider=provider_name)
    cache.set(key, cache.get(key, 0) + 1, BREAKER_COOLDOWN)


def _breaker_success(provider_name: str) -> None:
    cache.delete(BREAKER_KEY.format(provider=provider_name))


def month_usage(organization_id=None) -> dict:
    month_start = timezone.localdate().replace(day=1)
    queryset = AiAnalysis.objects.filter(created_at__date__gte=month_start).exclude(provider="local")
    if organization_id:
        queryset = queryset.filter(organization_id=organization_id)
    totals = queryset.aggregate(tokens_in=Sum("tokens_in"), tokens_out=Sum("tokens_out"), cost=Sum("cost_usd"))
    tokens = (totals["tokens_in"] or 0) + (totals["tokens_out"] or 0)
    return {"tokens": tokens, "cost_usd": float(totals["cost"] or 0), "since": month_start.isoformat()}


def _organization():
    from pme360.organizations.models import Organization

    return Organization.objects.get(pk=current_org_id())


def _cost(model: str, tokens_in: int, tokens_out: int) -> Decimal:
    price_in, price_out = settings.PME360_AI_PRICING.get(model, (0, 0))
    return Decimal(str(round((tokens_in * price_in + tokens_out * price_out) / 1_000_000, 6)))


def _hash(*parts) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part if isinstance(part, bytes) else json.dumps(part, sort_keys=True, default=str).encode())
    return digest.hexdigest()


def _check_budget_warning(organization) -> None:
    quota = organization.setting("ai_monthly_token_quota")
    usage = month_usage(organization.pk)["tokens"]
    if not quota or usage < 0.8 * quota:
        return
    from pme360.accounts.models import UserMembership
    from pme360.notifications import services as notifications
    from pme360.notifications.models import Notification

    month_start = timezone.localdate().replace(day=1)
    if Notification.objects.filter(event_code=BUDGET_WARNING_EVENT, created_at__date__gte=month_start).exists():
        return
    admins = [
        m.user for m in UserMembership.objects.filter(role__code="ADMIN_ORG", is_active=True).select_related("user")
    ]
    notifications.notify(
        admins,
        BUDGET_WARNING_EVENT,
        {"usage": f"{usage:,}".replace(",", " "), "quota": f"{quota:,}".replace(",", " ")},
        link="/ia",
    )


def run(
    *,
    prompt_code: str,
    content: str,
    schema: dict,
    context: dict | None = None,
    attachments: list[tuple[str, bytes]] | None = None,
    pme=None,
    document_version=None,
    diagnostic=None,
    input_refs: dict | None = None,
    sensitive: bool = False,
    pseudonymizer: Pseudonymizer | None = None,
    user=None,
    confidence_path: str | None = None,
) -> Outcome:
    prompt = prompts.get(prompt_code)
    attachments = list(attachments or [])
    context = context or {}
    organization = _organization()
    refs = dict(input_refs or {})
    notes: list[str] = []

    # 1. Politique et routage.
    provider, external = LocalProvider(), external_provider()
    if external is not None:
        reasons = []
        if not organization.ai_external_allowed:
            reasons.append("IA externe non autorisée par l'organisation")
        if sensitive:
            reasons.append("type de document sensible : jamais envoyé à une IA externe")
        if breaker_open(external.name):
            reasons.append("fournisseur indisponible (disjoncteur ouvert)")
        quota = organization.setting("ai_monthly_token_quota")
        if quota and month_usage(organization.pk)["tokens"] >= quota:
            reasons.append("budget mensuel de jetons épuisé")
        if not reasons and external.supports(prompt, bool(attachments)):
            provider = external
        else:
            notes.extend(reasons)
    if not provider.supports(prompt, bool(attachments)):
        status = AiAnalysis.Status.REFUSE_POLITIQUE if notes else AiAnalysis.Status.ECHEC
        error = "; ".join(notes) or "Lecture visuelle indisponible en local (ni OCR ni IA externe autorisée)."
        analysis = AiAnalysis.objects.create(
            task=prompt.task,
            status=status,
            pme=pme,
            document_version=document_version,
            diagnostic=diagnostic,
            provider=provider.name,
            model="-",
            prompt_code=prompt.code,
            prompt_version=prompt.version,
            input_refs={**refs, "routing": notes},
            input_hash=_hash(prompt.code, content),
            error=error[:500],
            attempts=0,
            requested_by=user,
        )
        return Outcome(status, None, analysis, provider.name, notes)
    refs["routing"] = notes

    # 2. Pseudonymisation (fournisseur externe uniquement).
    model = model_for(prompt.task) if provider.external else prompts.LOCAL_ENGINE_VERSION
    sent = content
    pseudonymized = False
    if provider.external:
        pseudonymizer = pseudonymizer or Pseudonymizer()
        sent = pseudonymizer.text(content)
        pseudonymized = bool(pseudonymizer.mapping)
        if attachments:
            refs["attachments"] = "pièce jointe transmise telle quelle (type non sensible, lecture visuelle)"
    input_hash = _hash(
        prompt.code, prompt.version, provider.name, model, content, context, *[a[1] for a in attachments]
    )

    # 3. Cache par empreinte des entrées (Document 4, § 13 : coût).
    cached = AiAnalysis.objects.filter(input_hash=input_hash, status=AiAnalysis.Status.SUCCES).first()
    if cached is not None:
        analysis = AiAnalysis.objects.create(
            task=prompt.task,
            status=AiAnalysis.Status.SUCCES,
            pme=pme,
            document_version=document_version,
            diagnostic=diagnostic,
            provider=cached.provider,
            model=cached.model,
            prompt_code=prompt.code,
            prompt_version=prompt.version,
            input_refs={**refs, "cache_of": str(cached.pk)},
            input_hash=input_hash,
            pseudonymized=cached.pseudonymized,
            output=cached.output,
            confidence=cached.confidence,
            attempts=0,
            requested_by=user,
        )
        return Outcome(analysis.status, cached.output, analysis, cached.provider, notes)

    # 4. Appel, validation par schéma (1 nouvelle tentative), repli local si le fournisseur est indisponible.
    request = StructuredRequest(
        prompt=prompt, model=model, content=sent, schema=schema, context=context, attachments=attachments
    )
    validator = jsonschema.Draft202012Validator(schema)
    started = time.monotonic()
    tokens_in = tokens_out = attempts = 0
    output, status, error, used_model = None, AiAnalysis.Status.ECHEC, "", model
    while attempts < 2:
        attempts += 1
        try:
            result = provider.structured(request)
        except ProviderError as exc:
            error = str(exc)
            logger.warning("ai.provider_error", provider=provider.name, error=error, transient=exc.transient)
            if provider.external:
                _breaker_failure(provider.name)
                local = LocalProvider()
                if exc.transient and local.supports(prompt, bool(attachments)):
                    notes.append("fournisseur externe indisponible : moteur local utilisé")
                    provider, request.model, request.content = local, prompts.LOCAL_ENGINE_VERSION, content
                    used_model, attempts = prompts.LOCAL_ENGINE_VERSION, 0
                    input_hash = _hash(prompt.code, prompt.version, local.name, used_model, content, context)
                    continue
                status = AiAnalysis.Status.DIFFERE if exc.transient else AiAnalysis.Status.ECHEC
            break
        tokens_in += result.tokens_in
        tokens_out += result.tokens_out
        used_model = result.model
        errors = sorted(validator.iter_errors(result.output), key=lambda e: e.path)
        if not errors:
            output, status, error = result.output, AiAnalysis.Status.SUCCES, ""
            if provider.external:
                _breaker_success(provider.name)
            break
        error = f"Sortie non conforme au schéma : {errors[0].message[:200]}"
        status = AiAnalysis.Status.SORTIE_INVALIDE
    if output is not None and provider.external and pseudonymizer is not None:
        output = pseudonymizer.restore(output)

    confidence = None
    if output is not None and confidence_path:
        value = output.get(confidence_path)
        confidence = Decimal(str(round(float(value), 3))) if isinstance(value, int | float) else None
    analysis = AiAnalysis.objects.create(
        task=prompt.task,
        status=status,
        pme=pme,
        document_version=document_version,
        diagnostic=diagnostic,
        provider=provider.name,
        model=used_model,
        prompt_code=prompt.code,
        prompt_version=prompt.version,
        input_refs={**refs, "routing": notes},
        input_hash=input_hash,
        pseudonymized=pseudonymized and provider.external,
        output=output,
        confidence=confidence,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=_cost(used_model, tokens_in, tokens_out),
        latency_ms=int((time.monotonic() - started) * 1000),
        attempts=attempts,
        error=error[:500],
        requested_by=user,
    )
    if provider.external:
        _check_budget_warning(organization)
    return Outcome(status, output, analysis, provider.name, notes)


def record(
    *,
    task: str,
    prompt_code: str,
    provider: str,
    model: str,
    output: dict | None,
    status: str = AiAnalysis.Status.SUCCES,
    tokens_in: int = 0,
    tokens_out: int = 0,
    latency_ms: int = 0,
    pme=None,
    input_refs: dict | None = None,
    user=None,
    pseudonymized: bool = False,
    error: str = "",
) -> AiAnalysis:
    """Trace d'un échange conduit hors de ``run`` (boucle agentique Ask AI) : même journal, même coût."""
    prompt = prompts.get(prompt_code)
    return AiAnalysis.objects.create(
        task=task,
        status=status,
        pme=pme,
        provider=provider,
        model=model,
        prompt_code=prompt.code,
        prompt_version=prompt.version,
        input_refs=input_refs or {},
        input_hash=_hash(prompt.code, input_refs or {}, time.time()),
        pseudonymized=pseudonymized,
        output=output,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=_cost(model, tokens_in, tokens_out),
        latency_ms=latency_ms,
        error=error[:500],
        requested_by=user,
    )
