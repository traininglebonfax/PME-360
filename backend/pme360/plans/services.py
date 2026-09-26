"""Du diagnostic au plan, puis au score mis à jour (Document 7, § 1 à 5).

Règles → recommandations notées → revue du conseiller → plan versionné → actions (dépendances, livrables,
horizons) → validation GUDE puis acceptation PME → exécution → livrables vérifiés → action terminée → progrès
vérifié → score courant recalculé → actions dépendantes débloquées. Chaque effet automatique est journalisé.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from pme360.audit import services as audit
from pme360.core.exceptions import BusinessError
from pme360.diagnostic.models import Diagnostic
from pme360.notifications import services as notifications
from pme360.pmes.models import Pme

from . import priority, rules
from .defaults import DELIVERABLE_TEMPLATES, RECOMMENDATION_RULES, SUPPORT_OFFERS
from .models import (
    Action,
    ActionDependency,
    ActionPlan,
    ActionTransition,
    CriterionProgress,
    Deliverable,
    DeliverableTemplate,
    Recommendation,
    RecommendationRule,
    SupportOffer,
)

S = Action.Status
OPEN_PLAN = (
    ActionPlan.Status.BROUILLON,
    ActionPlan.Status.EN_VALIDATION,
    ActionPlan.Status.VALIDE,
    ActionPlan.Status.EN_COURS,
)
LIVE_PLAN = (ActionPlan.Status.VALIDE, ActionPlan.Status.EN_COURS)


# --- Installation du catalogue -------------------------------------------------------------------------------


def install_plans(organization) -> None:
    """Catalogue par défaut (idempotent) : livrables, offres, règles v1 actives."""
    templates = {}
    for code, title, category, fmt, doc_type, instructions, checks in DELIVERABLE_TEMPLATES:
        templates[code], _ = DeliverableTemplate.objects.get_or_create(
            organization=organization,
            code=code,
            defaults={
                "title": title,
                "category": category,
                "format": fmt,
                "document_type_code": doc_type,
                "instructions": instructions,
                "verification_criteria": checks,
            },
        )
    offers = {}
    for item in SUPPORT_OFFERS:
        cost_min, cost_max = item.get("cost", (0, 0))
        offer, _ = SupportOffer.objects.get_or_create(
            organization=organization,
            code=item["code"],
            defaults={
                "title": item["title"],
                "dimension_code": item["dimension"],
                "objective": item["objective"],
                "typical_duration_days": item["duration"],
                "effort": item["effort"],
                "target_criteria": item["criteria"],
                "target_level": item["level"],
                "required_document_types": item.get("required", []),
                "sub_actions": item["steps"],
                "depends_on": item.get("depends", []),
                "estimated_cost_min": cost_min,
                "estimated_cost_max": cost_max,
                "is_growth": item.get("growth", False),
                "deliverables": item["deliverables"],
            },
        )
        offers[item["code"]] = offer
    for code, name, condition, offer_code, problem, rationale in RECOMMENDATION_RULES:
        if not RecommendationRule.objects.filter(organization=organization, code=code).exists():
            RecommendationRule.objects.create(
                organization=organization,
                code=code,
                version=1,
                name=name,
                condition=condition,
                offer=offers[offer_code],
                problem_template=problem,
                rationale_template=rationale,
                status=RecommendationRule.Status.ACTIVE,
            )


# --- Contexte d'évaluation -------------------------------------------------------------------------------------


def _staff(access) -> None:
    if access.is_pme_user:
        raise PermissionDenied("Réservé aux équipes d'accompagnement.")


def current_result(diagnostic: Diagnostic) -> dict:
    """Score courant de la PME (preuves et progrès vérifiés inclus) sur la base du diagnostic validé."""
    from pme360.scoring import services as scoring
    from pme360.scoring.models import ScoreSnapshot

    live = ScoreSnapshot.objects.filter(pme=diagnostic.pme, kind=ScoreSnapshot.Kind.LIVE).first()
    if live and live.result.get("source_diagnostic") == str(diagnostic.pk):
        return live.result
    return scoring.compute(diagnostic)


def reference_diagnostic(pme: Pme) -> Diagnostic:
    diagnostic = Diagnostic.objects.filter(pme=pme, status=Diagnostic.Status.VALIDE).order_by("-reference_date").first()
    if diagnostic is None:
        raise BusinessError(
            "Les recommandations s'appuient sur un diagnostic validé : validez d'abord le diagnostic.",
            code="no_validated_diagnostic",
        )
    return diagnostic


def _covered_offers(pme: Pme) -> set[int]:
    """Offres déjà traitées (action terminée) ou en cours dans un plan soumis : pas de nouvelle recommandation."""
    done = Action.objects.filter(pme=pme, status=S.TERMINE, offer__isnull=False).values_list("offer_id", flat=True)
    running = (
        Action.objects.filter(
            pme=pme, offer__isnull=False, plan__status__in=[*LIVE_PLAN, ActionPlan.Status.EN_VALIDATION]
        )
        .exclude(status__in=Action.TERMINAL)
        .values_list("offer_id", flat=True)
    )
    return set(done) | set(running)


# --- Recommandations -------------------------------------------------------------------------------------------


def _decimal(value: float) -> Decimal:
    return Decimal(str(round(value, 1)))


def ensure_catalog(organization) -> None:
    """Organisation créée avant la phase 5 : catalogue par défaut installé à la première utilisation."""
    if not SupportOffer.objects.exists():
        install_plans(organization)


def evaluate_rules(pme: Pme, result: dict, rule_queryset=None) -> dict[str, dict]:
    """Offre → candidats (règles déclenchées) pour la PME ; ne modifie rien (utilisé aussi par « Tester »)."""
    data = rules.variables(pme, result)
    candidates: dict[str, dict] = {}
    queryset = (
        rule_queryset
        if rule_queryset is not None
        else RecommendationRule.objects.filter(status=RecommendationRule.Status.ACTIVE)
    )
    for rule in queryset.select_related("offer"):
        if not rule.offer.is_active or not rules.matches(rule.condition, data):
            continue
        entry = candidates.setdefault(rule.offer.code, {"offer": rule.offer, "rules": [], "data": data})
        entry["rules"].append(rule)
    return candidates


def generate_recommendations(diagnostic: Diagnostic, user=None) -> list[Recommendation]:
    """Évalue les règles actives sur le score courant (idempotent : les propositions non décidées sont recalculées)."""
    if diagnostic.status != Diagnostic.Status.VALIDE:
        raise BusinessError("Les recommandations s'appuient sur un diagnostic validé.", code="invalid_status")
    pme = diagnostic.pme
    ensure_catalog(pme_organization(pme))
    result = current_result(diagnostic)
    settings = priority.settings_for(pme_organization(pme))
    candidates = evaluate_rules(pme, result)
    covered = _covered_offers(pme)
    settings["_prerequisites"] = {dep for c in candidates.values() for dep in c["offer"].depends_on}
    kept = []
    for _code, candidate in candidates.items():
        offer = candidate["offer"]
        if offer.pk in covered:
            continue
        matched = candidate["rules"]
        # Conflits : plusieurs règles pour la même offre → fusion, priorité maximale, justifications conservées.
        scorings = [
            priority.score_offer(
                offer, result, candidate["data"], settings, {"impact": r.impact, "urgency": r.urgency, "risk": r.risk}
            )
            for r in matched
        ]
        best = max(scorings, key=lambda s: s.score)
        problem = rules.render(matched[0].problem_template, candidate["data"])
        rationale = " ".join(rules.render(r.rationale_template, candidate["data"]) for r in matched)
        criteria_refs = sorted(set().union(*(rules.referenced_criteria(r.condition) for r in matched)))
        evidence = {
            "criteria": {
                c: candidate["data"]["criterion"].get(c) for c in criteria_refs if c in candidate["data"]["criterion"]
            },
            "global_score": result.get("global_score"),
            "evaluated_on": timezone.localdate().isoformat(),
        }
        values = {
            "offer": offer,
            "source": Recommendation.Source.REGLE,
            "rules": [{"code": r.code, "version": r.version} for r in matched],
            "problem": problem[:300],
            "rationale": rationale,
            "evidence_refs": evidence,
            "impact": best.impact,
            "urgency": best.urgency,
            "risk": best.risk,
            "effort": best.effort,
            "scoring_details": best.details,
            "priority_computed": _decimal(best.score),
        }
        existing = Recommendation.objects.filter(diagnostic=diagnostic, offer=offer).first()
        if existing is None:
            kept.append(
                Recommendation.objects.create(
                    pme=pme, diagnostic=diagnostic, priority_final=_decimal(best.score), created_by=user, **values
                )
            )
        elif existing.status == Recommendation.Status.PROPOSEE:
            for key, value in values.items():
                setattr(existing, key, value)
            if not existing.priority_override_reason:
                existing.priority_final = existing.priority_computed
            existing.save()
            kept.append(existing)
        else:
            kept.append(existing)
    # Propositions devenues sans objet (la situation s'est améliorée) : retirées si personne ne les a décidées.
    Recommendation.objects.filter(
        diagnostic=diagnostic, status=Recommendation.Status.PROPOSEE, source=Recommendation.Source.REGLE
    ).exclude(pk__in=[r.pk for r in kept]).delete()
    audit.record(
        "plan.recommendations_generated",
        entity_type="diagnostic",
        entity_id=diagnostic.pk,
        pme_id=pme.pk,
        actor=user,
        actor_type="USER" if user else "SYSTEM",
        after={"offers": sorted(c for c in candidates if candidates[c]["offer"].pk not in covered)},
    )
    return list(Recommendation.objects.filter(diagnostic=diagnostic).select_related("offer"))


def pme_organization(pme: Pme):
    from pme360.organizations.models import Organization

    return Organization.objects.get(pk=pme.organization_id)


def pme_organization_for(access):
    from pme360.organizations.models import Organization

    return Organization.objects.get(pk=access.organization_id)


def add_recommendation(
    diagnostic: Diagnostic, access, *, offer: SupportOffer, problem: str, rationale: str
) -> Recommendation:
    """Recommandation ajoutée par le conseiller (source CONSEILLER), notée comme les autres."""
    if not access.has("plan.edit"):
        raise PermissionDenied()
    if diagnostic.status != Diagnostic.Status.VALIDE:
        raise BusinessError("Les recommandations s'appuient sur un diagnostic validé.", code="invalid_status")
    if not problem.strip() or not rationale.strip():
        raise ValidationError({"rationale": ["Décrivez le problème et la justification."]})
    if Recommendation.objects.filter(diagnostic=diagnostic, offer=offer).exists():
        raise ValidationError({"offer": ["Cette offre est déjà recommandée pour ce diagnostic."]})
    pme = diagnostic.pme
    result = current_result(diagnostic)
    data = rules.variables(pme, result)
    settings = priority.settings_for(pme_organization(pme))
    settings["_prerequisites"] = set()
    scoring = priority.score_offer(offer, result, data, settings)
    recommendation = Recommendation.objects.create(
        pme=pme,
        diagnostic=diagnostic,
        offer=offer,
        source=Recommendation.Source.CONSEILLER,
        problem=problem.strip()[:300],
        rationale=rationale.strip(),
        evidence_refs={"global_score": result.get("global_score")},
        impact=scoring.impact,
        urgency=scoring.urgency,
        risk=scoring.risk,
        effort=scoring.effort,
        scoring_details=scoring.details,
        priority_computed=_decimal(scoring.score),
        priority_final=_decimal(scoring.score),
        status=Recommendation.Status.ACCEPTEE,
        decided_by=access.user,
        decided_at=timezone.now(),
        created_by=access.user,
    )
    audit.record("plan.recommendation_added", instance=recommendation, pme_id=pme.pk, after={"offer": offer.code})
    return recommendation


def decide_recommendation(
    recommendation: Recommendation,
    access,
    *,
    status: str,
    reason: str = "",
    axes: dict | None = None,
    priority_reason: str = "",
) -> Recommendation:
    """Revue du conseiller : accepter, rejeter (motif) ou ajuster la notation (motif) — Document 7, § 4.4."""
    if not access.has("plan.edit"):
        raise PermissionDenied()
    if recommendation.status == Recommendation.Status.CONVERTIE:
        raise BusinessError("Recommandation déjà convertie en action.", code="already_converted")
    reason = reason.strip()
    if status == Recommendation.Status.REJETEE and not reason:
        raise ValidationError({"reason": ["Motif obligatoire pour rejeter une recommandation."]})
    before = {
        "status": recommendation.status,
        "priority_final": float(recommendation.priority_final),
        "axes": [recommendation.impact, recommendation.urgency, recommendation.risk, recommendation.effort],
    }
    axes = {k: v for k, v in (axes or {}).items() if v is not None}
    if axes:
        changed = {k: v for k, v in axes.items() if getattr(recommendation, k) != v}
        if changed:
            if not priority_reason.strip():
                raise ValidationError({"priority_reason": ["Motif obligatoire pour modifier la priorité."]})
            for key, value in changed.items():
                if not 1 <= value <= 5:
                    raise ValidationError({key: ["Note entre 1 et 5."]})
                setattr(recommendation, key, value)
            settings = priority.settings_for(pme_organization(recommendation.pme))
            recommendation.priority_final = _decimal(
                priority.priority_score(
                    recommendation.impact, recommendation.urgency, recommendation.risk, recommendation.effort, settings
                )
            )
            recommendation.priority_override_reason = priority_reason.strip()
    if status in (Recommendation.Status.ACCEPTEE, Recommendation.Status.REJETEE, Recommendation.Status.PROPOSEE):
        recommendation.status = status
    recommendation.decision_reason = reason
    recommendation.decided_by = access.user
    recommendation.decided_at = timezone.now()
    recommendation.save()
    audit.record(
        "plan.recommendation_decided",
        instance=recommendation,
        pme_id=recommendation.pme_id,
        before=before,
        after={
            "status": recommendation.status,
            "priority_final": float(recommendation.priority_final),
            "reason": reason,
            "priority_reason": recommendation.priority_override_reason,
        },
    )
    return recommendation


# --- Génération du plan -----------------------------------------------------------------------------------------


def _next_ref(year: int) -> str:
    prefix = f"ACT-{year}-"
    last = Action.objects.filter(human_ref__startswith=prefix).aggregate(m=Max("human_ref")).get("m")
    number = int(last.rsplit("-", 1)[1]) + 1 if last else 1
    return f"{prefix}{number:05d}"


def _create_action(**fields) -> Action:
    year = timezone.localdate().year
    for _ in range(5):
        try:
            with transaction.atomic():
                return Action.objects.create(human_ref=_next_ref(year), **fields)
        except IntegrityError:
            continue
    raise BusinessError("Référence d'action indisponible, réessayez.", code="ref_conflict")


def why_for(recommendation: Recommendation) -> str:
    """« Pourquoi » en langage PME (Document 7, § 4.5) : constat, objectif, résultat attendu."""
    offer = recommendation.offer
    return (
        f"Constat : {recommendation.problem[0].lower()}{recommendation.problem[1:]}. "
        f"Objectif : {offer.objective[0].lower()}{offer.objective[1:]} "
        f"Quand les documents demandés seront vérifiés, votre score sera mis à jour automatiquement."
    )


def _main_advisor(pme: Pme):
    advisors = notifications.advisors(pme)
    return advisors[0] if advisors else None


@transaction.atomic
def generate_plan(pme: Pme, access, *, horizon_start: date | None = None, title: str = "") -> ActionPlan:
    """Plan BROUILLON à partir des recommandations acceptées (Document 7, § 4.5). Régénère un brouillon existant."""
    if not access.has("plan.edit"):
        raise PermissionDenied()
    diagnostic = reference_diagnostic(pme)
    plan = ActionPlan.objects.filter(pme=pme, status__in=OPEN_PLAN).first()
    if plan and plan.status != ActionPlan.Status.BROUILLON:
        raise BusinessError(
            "Un plan est déjà en validation ou en cours : créez une nouvelle version du plan.", code="plan_open"
        )
    if plan is not None:
        # Régénération d'un brouillon : ses actions sont recréées à partir des recommandations acceptées.
        plan.actions.all().delete()
        Recommendation.objects.filter(pme=pme, status=Recommendation.Status.CONVERTIE, actions__isnull=True).update(
            status=Recommendation.Status.ACCEPTEE
        )
    accepted = list(
        Recommendation.objects.filter(diagnostic=diagnostic, status=Recommendation.Status.ACCEPTEE)
        .select_related("offer")
        .order_by("-priority_final")
    )
    if not accepted:
        raise BusinessError("Acceptez au moins une recommandation avant de générer le plan.", code="nothing_accepted")
    organization = pme_organization(pme)
    settings = priority.settings_for(organization)
    horizon_start = horizon_start or timezone.localdate()
    if plan is None:
        version = (ActionPlan.objects.filter(pme=pme).aggregate(m=Max("version"))["m"] or 0) + 1
        previous = ActionPlan.objects.filter(pme=pme).order_by("-version").first()
        plan = ActionPlan.objects.create(
            pme=pme,
            diagnostic=diagnostic,
            title=title or f"Plan d'accompagnement — {pme.legal_name}",
            version=version,
            supersedes=previous,
            horizon_start=horizon_start,
            capacity=settings["capacity"],
            created_by=access.user,
        )
    else:
        plan.diagnostic = diagnostic
        plan.horizon_start = horizon_start
        plan.title = title or plan.title
        plan.save()
    _build_actions(plan, accepted, settings, access.user)
    audit.record(
        "plan.generated",
        instance=plan,
        pme_id=pme.pk,
        after={"version": plan.version, "actions": plan.actions.count(), "offers": [r.offer.code for r in accepted]},
    )
    return plan


def _build_actions(plan: ActionPlan, recommendations: list[Recommendation], settings: dict, user, carried=()) -> None:
    items = []
    for rec in recommendations:
        items.append(
            {
                "key": rec.offer.code,
                "rec": rec,
                "phase": priority.base_phase(
                    float(rec.priority_final), rec.impact, rec.urgency, rec.effort, rec.offer.is_growth, settings
                ),
                "depends": rec.offer.depends_on,
            }
        )
    items.sort(key=lambda i: -float(i["rec"].priority_final))
    priority.assign_phases(items, plan.capacity)
    advisor = _main_advisor(plan.pme)
    created: dict[str, Action] = {a.offer.code: a for a in carried if a.offer_id}
    for position, item in enumerate(
        sorted(items, key=lambda i: (priority.PHASE_ORDER.index(i["phase"]), -float(i["rec"].priority_final)))
    ):
        rec, offer = item["rec"], item["rec"].offer
        start = plan.horizon_start + timedelta(days=priority.PHASE_START_DAYS[item["phase"]])
        due = start + timedelta(days=offer.typical_duration_days)
        action = _create_action(
            plan=plan,
            pme=plan.pme,
            recommendation=rec,
            offer=offer,
            dimension_code=offer.dimension_code,
            target_criteria=offer.target_criteria,
            target_level=offer.target_level,
            problem=rec.problem,
            objective=offer.objective,
            title=offer.title,
            description=offer.description,
            why=why_for(rec),
            sub_actions=[{"title": step, "done": False} for step in offer.sub_actions],
            owner_type=Action.Owner.PME,
            advisor_user=advisor,
            priority_score=rec.priority_final,
            phase=item["phase"],
            position=position,
            start_date=start,
            due_date=due,
            estimated_cost_min=offer.estimated_cost_min,
            estimated_cost_max=offer.estimated_cost_max,
            success_indicator=offer.success_indicator,
            created_by=user,
        )
        for template in DeliverableTemplate.objects.filter(code__in=offer.deliverables):
            Deliverable.objects.create(
                action=action, template=template, title=template.title, document_type_code=template.document_type_code
            )
        created[offer.code] = action
        rec.status = Recommendation.Status.CONVERTIE
        rec.save(update_fields=["status", "updated_at"])
    for _code, action in created.items():
        if action.plan_id != plan.pk or action.offer is None:
            continue
        for dependency in action.offer.depends_on:
            if dependency in created and created[dependency].pk != action.pk:
                ActionDependency.objects.get_or_create(action=action, depends_on_action=created[dependency])
    for action in plan.actions.all():
        if action.status == S.NON_COMMENCE and _blocking(action):
            action.status = S.BLOQUE
            action.save(update_fields=["status", "updated_at"])


def _blocking(action: Action) -> list[Action]:
    return [
        link.depends_on_action
        for link in action.dependency_links.select_related("depends_on_action")
        if link.depends_on_action.status not in Action.TERMINAL
    ]


def add_dependency(action: Action, depends_on: Action, access) -> None:
    """Dépendance ajoutée à la main ; refuse les cycles (Document 3, § 3.6)."""
    if not access.has("plan.edit"):
        raise PermissionDenied()
    if action.plan_id != depends_on.plan_id or action.pk == depends_on.pk:
        raise ValidationError({"depends_on": ["Dépendance impossible."]})
    seen, stack = set(), [depends_on]
    while stack:
        current = stack.pop()
        if current.pk == action.pk:
            raise ValidationError({"depends_on": ["Cette dépendance créerait un cycle."]})
        if current.pk in seen:
            continue
        seen.add(current.pk)
        stack.extend(link.depends_on_action for link in current.dependency_links.select_related("depends_on_action"))
    ActionDependency.objects.get_or_create(action=action, depends_on_action=depends_on)
    if action.status == S.NON_COMMENCE and _blocking(action):
        _move(action, S.BLOQUE, access.user, "Dépendance ajoutée", actor_type="SYSTEM")


@transaction.atomic
def new_version(plan: ActionPlan, access, *, reason: str) -> ActionPlan:
    """Nouvelle version du plan (réévaluation, changement majeur) : l'ancienne est close, l'historique conservé.

    Les actions non terminées sont reprises telles quelles ; les recommandations acceptées non converties du
    dernier diagnostic validé deviennent de nouvelles actions.
    """
    if not access.has("plan.edit"):
        raise PermissionDenied()
    if plan.status not in LIVE_PLAN and plan.status != ActionPlan.Status.EN_VALIDATION:
        raise BusinessError("Seul un plan en validation, validé ou en cours peut être révisé.", code="invalid_status")
    if not reason.strip():
        raise ValidationError({"reason": ["Motif obligatoire."]})
    diagnostic = reference_diagnostic(plan.pme)
    plan.status = ActionPlan.Status.CLOS
    plan.closed_at = timezone.now()
    plan.close_reason = f"Remplacé par la version {plan.version + 1} : {reason.strip()}"
    plan.save()
    new = ActionPlan.objects.create(
        pme=plan.pme,
        diagnostic=diagnostic,
        title=plan.title,
        version=plan.version + 1,
        supersedes=plan,
        horizon_start=timezone.localdate(),
        capacity=plan.capacity,
        created_by=access.user,
    )
    carried = list(plan.actions.exclude(status__in=Action.TERMINAL))
    for action in carried:
        action.plan = new
        action.save(update_fields=["plan", "updated_at"])
    accepted = list(
        Recommendation.objects.filter(diagnostic=diagnostic, status=Recommendation.Status.ACCEPTEE)
        .exclude(offer__in=[a.offer_id for a in carried if a.offer_id])
        .select_related("offer")
    )
    _build_actions(new, accepted, priority.settings_for(pme_organization(plan.pme)), access.user, carried)
    audit.record(
        "plan.new_version",
        instance=new,
        pme_id=plan.pme_id,
        before={"version": plan.version},
        after={"version": new.version, "reason": reason, "carried": len(carried), "added": len(accepted)},
    )
    return new


# --- Workflow du plan ---------------------------------------------------------------------------------------------


def plan_visible_to_pme(plan: ActionPlan) -> bool:
    return plan.status in (*LIVE_PLAN, ActionPlan.Status.CLOS) or (
        plan.status == ActionPlan.Status.EN_VALIDATION and plan.validated_at is not None
    )


def transition_plan(plan: ActionPlan, access, action: str, reason: str = "") -> ActionPlan:
    """submit (conseiller) → validate (GUDE) → accept (dirigeant PME) → VALIDÉ ; reopen ; close."""
    before = plan.status
    now = timezone.now()
    if action == "submit":
        _require(access, "plan.edit", staff=True)
        _expect(plan, ActionPlan.Status.BROUILLON)
        if not plan.actions.exists():
            raise BusinessError("Le plan ne contient aucune action.", code="empty_plan")
        plan.status, plan.submitted_at = ActionPlan.Status.EN_VALIDATION, now
    elif action == "validate":
        _require(access, "plan.edit", staff=True)
        _expect(plan, ActionPlan.Status.EN_VALIDATION)
        plan.validated_by, plan.validated_at = access.user, now
        notifications.notify(
            notifications.pme_users(plan.pme),
            "PLAN_TO_ACCEPT",
            {"pme": plan.pme.legal_name, "actions": plan.actions.count()},
            link="/espace/plan",
            pme=plan.pme,
        )
    elif action == "accept":
        _require(access, "plan.accept")
        _expect(plan, ActionPlan.Status.EN_VALIDATION)
        if plan.validated_at is None:
            raise BusinessError("Le plan doit d'abord être validé par GUDE-PME.", code="not_validated")
        if access.is_pme_user and plan.pme_id not in access.own_pme_ids:
            raise PermissionDenied()
        plan.status, plan.accepted_by, plan.accepted_at = ActionPlan.Status.VALIDE, access.user, now
        notifications.notify(
            notifications.recipients(plan.pme, ["CONSEILLER"]),
            "PLAN_ACCEPTED",
            {"pme": plan.pme.legal_name},
            link=f"/pme/{plan.pme_id}?onglet=plan",
            pme=plan.pme,
        )
    elif action == "reopen":
        _require(access, "plan.edit", staff=True)
        _expect(plan, ActionPlan.Status.EN_VALIDATION)
        if not reason.strip():
            raise ValidationError({"reason": ["Motif obligatoire."]})
        plan.status, plan.validated_by, plan.validated_at = ActionPlan.Status.BROUILLON, None, None
    elif action == "close":
        _require(access, "plan.edit", staff=True)
        if plan.status not in LIVE_PLAN:
            raise BusinessError("Seul un plan validé ou en cours peut être clos.", code="invalid_status")
        if not reason.strip():
            raise ValidationError({"reason": ["Motif obligatoire."]})
        plan.status, plan.closed_at, plan.close_reason = ActionPlan.Status.CLOS, now, reason.strip()
    else:
        raise ValidationError({"action": ["Transition inconnue."]})
    plan.save()
    audit.record(
        f"plan.{action}",
        instance=plan,
        pme_id=plan.pme_id,
        before={"status": before},
        after={"status": plan.status, "reason": reason},
    )
    return plan


def _require(access, permission: str, staff: bool = False) -> None:
    if not access.has(permission) or (staff and access.is_pme_user):
        raise PermissionDenied()


def _expect(plan: ActionPlan, status: str) -> None:
    if plan.status != status:
        raise BusinessError(
            f"Transition impossible depuis le statut « {plan.get_status_display()} ».", code="invalid_status"
        )


# --- Workflow des actions (Document 7, § 2.2) --------------------------------------------------------------------

MANUAL = {
    S.NON_COMMENCE: {S.EN_COURS, S.EN_ATTENTE_PME, S.EN_ATTENTE_GUDE, S.ABANDONNE},
    S.EN_COURS: {S.DOCUMENT_DEMANDE, S.EN_ATTENTE_PME, S.EN_ATTENTE_GUDE, S.ABANDONNE, S.TERMINE},
    S.DOCUMENT_DEMANDE: {S.EN_COURS, S.EN_ATTENTE_PME, S.EN_ATTENTE_GUDE, S.ABANDONNE},
    S.NON_CONFORME: {S.EN_COURS, S.DOCUMENT_DEMANDE, S.ABANDONNE},
    S.CONFORME: {S.TERMINE},
    S.EN_ATTENTE_PME: {S.EN_COURS, S.ABANDONNE},
    S.EN_ATTENTE_GUDE: {S.EN_COURS, S.ABANDONNE},
    S.BLOQUE: {S.ABANDONNE},
    S.DOCUMENT_RECU: {S.ABANDONNE},
    S.A_VERIFIER: {S.ABANDONNE},
}
PME_ALLOWED = {S.EN_COURS, S.EN_ATTENTE_GUDE}  # la PME démarre, reprend, ou signale attendre GUDE-PME


def transition_action(action: Action, access, to: str, reason: str = "") -> Action:
    if not access.has("task.update"):
        raise PermissionDenied()
    if access.is_pme_user and (action.pme_id not in access.own_pme_ids or to not in PME_ALLOWED):
        raise PermissionDenied("Cette étape est réalisée par votre conseiller.")
    if action.plan.status not in LIVE_PLAN:
        raise BusinessError("Le plan doit être validé et accepté avant de démarrer les actions.", code="plan_not_live")
    if to not in MANUAL.get(action.status, set()):
        raise BusinessError(
            f"Passage impossible de « {action.get_status_display()} » à « {S(to).label} ».", code="invalid_transition"
        )
    reason = reason.strip()
    if to == S.ABANDONNE and not reason:
        raise ValidationError({"reason": ["Motif obligatoire pour abandonner une action."]})
    if to == S.TERMINE:
        pending = action.deliverables.exclude(status=Deliverable.Status.CONFORME)
        if pending.exists():
            raise BusinessError(
                "Tous les livrables doivent être vérifiés conformes avant de terminer l'action.",
                code="deliverables_pending",
            )
    _move(action, to, access.user, reason)
    return action


def _move(action: Action, to: str, user, reason: str = "", actor_type: str = "USER") -> None:
    before = action.status
    if before == to:
        return
    action.status = to
    action.status_changed_at = timezone.now()
    action.waiting_on = {S.EN_ATTENTE_PME: "PME", S.EN_ATTENTE_GUDE: "GUDE"}.get(to, "")
    today = timezone.localdate()
    if to == S.EN_COURS and action.started_at is None:
        action.started_at = today
    if to == S.ABANDONNE:
        action.abandon_reason = reason
    if to == S.TERMINE:
        action.completed_at = timezone.now()
    action.save()
    ActionTransition.objects.create(
        action=action, from_status=before, to_status=to, actor=user, actor_type=actor_type, reason=reason
    )
    audit.record(
        "action.transitioned",
        instance=action,
        pme_id=action.pme_id,
        actor=user,
        actor_type=actor_type,
        before={"status": before},
        after={"status": to, "reason": reason, "ref": action.human_ref},
    )
    plan = action.plan
    if to == S.EN_COURS and plan.status == ActionPlan.Status.VALIDE:
        plan.status = ActionPlan.Status.EN_COURS
        plan.save(update_fields=["status", "updated_at"])
    if to == S.DOCUMENT_DEMANDE:
        notifications.notify(
            notifications.pme_users(action.pme),
            "ACTION_DOCUMENT_REQUESTED",
            {"action": action.title, "documents": ", ".join(d.title for d in action.deliverables.all())},
            link="/espace/plan",
            pme=action.pme,
        )
    if to == S.NON_CONFORME:
        notifications.notify(
            notifications.pme_users(action.pme),
            "ACTION_DELIVERABLE_REJECTED",
            {"action": action.title, "reason": reason},
            link="/espace/plan",
            pme=action.pme,
        )
    if to in Action.TERMINAL:
        if to == S.TERMINE:
            _record_progress(action)
        _release_dependents(action)


def _record_progress(action: Action) -> None:
    """Action terminée : ses critères atteignent le niveau visé ; score courant recalculé (Document 7, § 2.2)."""
    from pme360.documents.services import after_evidence_change

    if action.target_level:
        for code in action.target_criteria:
            CriterionProgress.objects.get_or_create(
                action=action,
                criterion_code=code,
                defaults={"pme": action.pme, "level": action.target_level, "achieved_at": action.completed_at},
            )
    after_evidence_change(action.pme)
    audit.record(
        "action.progress_recorded",
        instance=action,
        pme_id=action.pme_id,
        actor_type="SYSTEM",
        after={"criteria": action.target_criteria, "level": action.target_level},
    )


def _release_dependents(action: Action) -> None:
    for link in action.dependent_links.select_related("action"):
        dependent = link.action
        if dependent.status == S.BLOQUE and not _blocking(dependent):
            _move(dependent, S.NON_COMMENCE, None, f"Débloquée : {action.human_ref} terminée", actor_type="SYSTEM")
            notifications.notify(
                notifications.pme_users(dependent.pme),
                "ACTION_UNBLOCKED",
                {"action": dependent.title},
                link="/espace/plan",
                pme=dependent.pme,
            )
    if not action.plan.actions.exclude(status__in=Action.TERMINAL).exists() and action.plan.status in LIVE_PLAN:
        plan = action.plan
        plan.status, plan.closed_at = ActionPlan.Status.CLOS, timezone.now()
        plan.close_reason = "Toutes les actions sont terminées."
        plan.save(update_fields=["status", "closed_at", "close_reason", "updated_at"])
        audit.record("plan.completed", instance=plan, pme_id=plan.pme_id, actor_type="SYSTEM")


def update_action(action: Action, access, **fields) -> Action:
    """Modifications de la fiche : conseiller (échéance, horizon, responsable…) ; PME : cocher les étapes."""
    if not access.has("task.update"):
        raise PermissionDenied()
    before = {}
    if access.is_pme_user:
        if action.pme_id not in access.own_pme_ids or set(fields) - {"sub_actions"}:
            raise PermissionDenied("Seules les étapes peuvent être cochées par la PME.")
    elif set(fields) - {"sub_actions"} and not access.has("plan.edit"):
        raise PermissionDenied()
    if "sub_actions" in fields:
        steps = fields.pop("sub_actions")
        titles = [s["title"] for s in action.sub_actions]
        if access.is_pme_user and [s.get("title") for s in steps] != titles:
            raise ValidationError({"sub_actions": ["Les étapes ne peuvent pas être renommées par la PME."]})
        before["sub_actions"] = action.sub_actions
        action.sub_actions = [{"title": str(s.get("title", ""))[:200], "done": bool(s.get("done"))} for s in steps]
    for key, value in fields.items():
        if value is None:
            continue
        before[key] = getattr(action, key)
        setattr(action, key, value)
    if action.start_date and action.due_date < action.start_date:
        raise ValidationError({"due_date": ["L'échéance précède le début."]})
    action.save()
    audit.record(
        "action.updated",
        instance=action,
        pme_id=action.pme_id,
        before={k: str(v) for k, v in before.items()},
        after={k: str(getattr(action, k)) for k in before},
    )
    return action


# --- Livrables et documents -------------------------------------------------------------------------------------


def deliverable_for_upload(deliverable: Deliverable, access, document_type_code: str | None) -> None:
    """Contrôle avant dépôt d'un livrable (appelé par la vue de dépôt)."""
    action = deliverable.action
    if access.is_pme_user and action.pme_id not in access.own_pme_ids:
        raise PermissionDenied()
    if action.plan.status not in LIVE_PLAN:
        raise BusinessError("Le plan doit être validé et accepté avant le dépôt des livrables.", code="plan_not_live")
    if action.status in (*Action.TERMINAL, S.BLOQUE):
        raise BusinessError("Cette action n'attend pas de document.", code="invalid_status")
    if deliverable.status == Deliverable.Status.CONFORME:
        raise BusinessError("Ce livrable est déjà vérifié conforme.", code="already_conform")
    if document_type_code and document_type_code != deliverable.document_type_code:
        raise ValidationError({"document_type": ["Le type de document ne correspond pas au livrable."]})


def on_deliverable_uploaded(deliverable: Deliverable, document, user) -> None:
    """Dépôt lié à une action : DOCUMENT_REÇU (le pipeline documentaire est lancé par le dépôt)."""
    deliverable.document = document
    deliverable.status = Deliverable.Status.DEPOSE
    deliverable.reason = ""
    deliverable.save()
    action = deliverable.action
    if action.status not in Action.TERMINAL:
        if action.status in (S.NON_COMMENCE, S.EN_ATTENTE_PME, S.EN_ATTENTE_GUDE) and action.started_at is None:
            action.started_at = timezone.localdate()
        _move(action, S.DOCUMENT_RECU, user, f"Livrable déposé : {deliverable.title}")


def on_document_analyzed(document) -> None:
    """Fin de l'analyse (pipeline) : les actions concernées passent À VÉRIFIER (file du conseiller)."""
    for deliverable in Deliverable.objects.filter(document=document, status=Deliverable.Status.DEPOSE).select_related(
        "action"
    ):
        deliverable.status = Deliverable.Status.A_VERIFIER
        deliverable.save(update_fields=["status", "updated_at"])
        if deliverable.action.status == S.DOCUMENT_RECU:
            _move(deliverable.action, S.A_VERIFIER, None, "Analyse du document terminée", actor_type="SYSTEM")


def on_document_decision(document) -> None:
    """Décision du conseiller sur un document : livrables et actions liés mis à jour (Document 7, § 2.2)."""
    from pme360.documents.models import Document

    conform = document.conformity_status in (Document.Conformity.CONFORME, Document.Conformity.CONFORME_SOUS_RESERVE)
    for deliverable in (
        Deliverable.objects.filter(document=document)
        .exclude(status=Deliverable.Status.ATTENDU)
        .select_related("action")
    ):
        deliverable.status = Deliverable.Status.CONFORME if conform else Deliverable.Status.NON_CONFORME
        deliverable.reason = document.decision_reason
        deliverable.save(update_fields=["status", "reason", "updated_at"])
        action = deliverable.action
        if action.status in Action.TERMINAL:
            continue
        user = document.verified_by
        if not conform:
            _move(action, S.NON_CONFORME, user, document.decision_reason or "Livrable non conforme")
            continue
        statuses = set(action.deliverables.values_list("status", flat=True))
        if statuses == {Deliverable.Status.CONFORME}:
            _move(action, S.CONFORME, user, "Tous les livrables sont conformes")
            # Automatique si tous les livrables sont conformes (Document 7, § 2.2).
            _move(action, S.TERMINE, None, "Terminée automatiquement : livrables conformes", actor_type="SYSTEM")
        elif not statuses & {Deliverable.Status.DEPOSE, Deliverable.Status.A_VERIFIER}:
            _move(action, S.DOCUMENT_DEMANDE, user, f"{deliverable.title} conforme ; d'autres documents sont attendus")


# --- Retards (planificateur) --------------------------------------------------------------------------------------


def overdue_actions(pme: Pme, today: date):
    return (
        Action.objects.filter(pme=pme, due_date__lt=today, plan__status__in=LIVE_PLAN)
        .exclude(status__in=[*Action.TERMINAL, S.BLOQUE])
        .select_related("plan")
    )


# --- Administration des règles (Document 7, § 3.3) -------------------------------------------------------------


def save_rule(access, data: dict) -> RecommendationRule:
    """Nouvelle règle, ou nouvelle version BROUILLON d'une règle existante (une règle active n'est jamais modifiée)."""
    _require(access, "org.configure", staff=True)
    ensure_catalog(pme_organization_for(access))
    rules.validate_condition(data["condition"])
    offer = SupportOffer.objects.filter(code=data["offer_code"]).first()
    if offer is None:
        raise ValidationError({"offer_code": ["Offre inconnue."]})
    for template in ("problem_template", "rationale_template"):
        try:
            rules.render(data[template], {})
        except Exception as exc:  # gabarit illisible
            raise ValidationError({template: ["Gabarit invalide."]}) from exc
    latest = RecommendationRule.objects.filter(code=data["code"]).order_by("-version").first()
    rule = RecommendationRule.objects.create(
        code=data["code"],
        version=(latest.version + 1) if latest else 1,
        name=data["name"],
        condition=data["condition"],
        offer=offer,
        impact=data.get("impact"),
        urgency=data.get("urgency"),
        risk=data.get("risk"),
        problem_template=data["problem_template"],
        rationale_template=data["rationale_template"],
        status=RecommendationRule.Status.DRAFT,
        created_by=access.user,
    )
    audit.record("plan.rule_saved", instance=rule, after={"code": rule.code, "version": rule.version})
    return rule


def test_rule(rule: RecommendationRule, access) -> dict:
    """« Tester » : exécute la règle en lecture seule sur les PME du périmètre ayant un diagnostic validé."""
    _require(access, "org.configure", staff=True)
    pmes = access.pme_queryset(Pme.objects.all())
    evaluated, matched = 0, []
    for pme in pmes:
        diagnostic = (
            Diagnostic.objects.filter(pme=pme, status=Diagnostic.Status.VALIDE).order_by("-reference_date").first()
        )
        if diagnostic is None:
            continue
        evaluated += 1
        result = current_result(diagnostic)
        data = rules.variables(pme, result)
        if rules.matches(rule.condition, data):
            matched.append(
                {
                    "pme_id": str(pme.pk),
                    "pme_name": pme.legal_name,
                    "rationale": rules.render(rule.rationale_template, data),
                }
            )
    rule.tested_at = timezone.now()
    rule.test_result = {"evaluated": evaluated, "matched": matched}
    rule.save(update_fields=["tested_at", "test_result", "updated_at"])
    return rule.test_result


def set_rule_status(rule: RecommendationRule, access, status: str) -> RecommendationRule:
    _require(access, "org.configure", staff=True)
    before = rule.status
    if status == RecommendationRule.Status.ACTIVE:
        if rule.tested_at is None:
            raise BusinessError("Testez la règle avant de l'activer.", code="not_tested")
        with transaction.atomic():
            RecommendationRule.objects.filter(code=rule.code, status=RecommendationRule.Status.ACTIVE).exclude(
                pk=rule.pk
            ).update(status=RecommendationRule.Status.INACTIVE)
            rule.status = status
            rule.save(update_fields=["status", "updated_at"])
    elif status == RecommendationRule.Status.INACTIVE:
        rule.status = status
        rule.save(update_fields=["status", "updated_at"])
    else:
        raise ValidationError({"status": ["Statut inconnu."]})
    audit.record("plan.rule_status", instance=rule, before={"status": before}, after={"status": rule.status})
    return rule
