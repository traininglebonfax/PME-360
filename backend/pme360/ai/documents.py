"""Analyse IA d'une version déposée (Document 4, § 2 à § 7) : classification, extraction, contrôles, confiance.

Appelée par la chaîne documentaire (``documents.pipeline``) après la lecture du texte. Elle ne décide JAMAIS de la
conformité : elle prépare la vérification humaine (valeurs pré-remplies, contrôles, priorité de la file).
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

import structlog
from django.conf import settings
from django.utils import timezone

from pme360.documents.models import Document, DocumentCheck, DocumentVersion
from pme360.pmes.services import normalize_compact, normalize_rccm

from . import gateway
from .models import DocumentExtraction, FinancialStatement
from .pseudonymize import for_pme
from .rules import fold
from .schemas import AUTRE, CLASSIFIABLE_TYPES, CLASSIFICATION_SCHEMA, EXTRACTION_SCHEMAS, ExtractionSchema

logger = structlog.get_logger(__name__)

SEVERITY_ORDER = ["INFO", "MOYENNE", "ELEVEE", "CRITIQUE"]
CONTROL_FACTOR = {"OK": 1.0, "NON_DETERMINE": 1.0, "ALERTE": 0.6, "ECHEC": 0.3}
VISION_TYPES = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
LEGAL_FORMS = r"\b(sarlu?|sasu?|sa|snc|scs|gie|ets|etablissements?|societe|ste|unipersonnelle|cooperative|scoops)\b"
MAX_TEXT = 60_000


@dataclass
class Control:
    code: str
    result: str  # OK | ALERTE | ECHEC | NON_DETERMINE
    message: str
    severity: str = "INFO"
    fields: tuple[str, ...] = ()
    details: dict = field(default_factory=dict)

    @property
    def anomaly(self) -> bool:
        return self.result in ("ALERTE", "ECHEC") and SEVERITY_ORDER.index(self.severity) >= 1


# --- Aides -----------------------------------------------------------------------------------------------------


def _date(value) -> date | None:
    try:
        return date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def normalize_name(value: str) -> str:
    value = re.sub(LEGAL_FORMS, " ", fold(value or ""))
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def name_similarity(a: str, b: str) -> float:
    a, b = normalize_name(a), normalize_name(b)
    if not a or not b:
        return 0.0
    if a == b or (len(min(a, b, key=len)) >= 6 and (a in b or b in a)):
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _fmt(amount: float) -> str:
    return f"{amount:,.0f}".replace(",", " ") + " FCFA"


def declared_input(pme, key: str) -> tuple[float, date] | None:
    """Dernière valeur déclarée au questionnaire pour une donnée d'indicateur (« input.ca_n »)."""
    from pme360.diagnostic.models import Answer

    answer = (
        Answer.objects.filter(diagnostic__pme=pme, question__feeds=f"input.{key}", value__isnull=False)
        .exclude(diagnostic__status="ANNULE")
        .order_by("-diagnostic__reference_date", "-answered_at")
        .first()
    )
    if answer is None or not isinstance(answer.value, int | float):
        return None
    return float(answer.value), answer.diagnostic.reference_date


# --- Contrôles déterministes (Document 4, § 5) -------------------------------------------------------------------


def controls_for(document: Document, schema: ExtractionSchema, data: dict, today: date) -> list[Control]:
    pme = document.pme
    found: list[Control] = []

    # ENTITE_CORRESPOND : identifiants d'abord (bloquants), puis raison sociale approchée.
    identifier_checks = [
        ("numero_rccm", pme.rccm_number, normalize_rccm, "RCCM"),
        ("rccm", pme.rccm_number, normalize_rccm, "RCCM"),
        ("ncc", pme.ncc, normalize_compact, "NCC"),
        ("numero_employeur", pme.cnps_employer_number, normalize_compact, "n° employeur CNPS"),
    ]
    entity = None
    for field_name, known, normalize, label in identifier_checks:
        value = data.get(field_name)
        if value and known:
            if normalize(value) != normalize(known):
                entity = Control(
                    "ENTITE_CORRESPOND",
                    "ECHEC",
                    f"Le {label} du document ({value}) ne correspond pas à celui de la PME.",
                    "CRITIQUE",
                    (field_name,),
                    {"document": value, "pme": known},
                )
                break
    if entity is None and data.get("raison_sociale"):
        similarity = max(
            name_similarity(data["raison_sociale"], pme.legal_name),
            name_similarity(data["raison_sociale"], pme.trade_name),
        )
        if similarity >= 0.85:
            entity = Control(
                "ENTITE_CORRESPOND",
                "OK",
                "Le document est bien au nom de la PME.",
                details={"similarity": round(similarity, 2)},
            )
        elif similarity >= 0.6:
            entity = Control(
                "ENTITE_CORRESPOND",
                "ALERTE",
                f"Nom proche mais différent : « {data['raison_sociale']} ».",
                "MOYENNE",
                ("raison_sociale",),
                {"similarity": round(similarity, 2)},
            )
        else:
            entity = Control(
                "ENTITE_CORRESPOND",
                "ECHEC",
                f"Le document semble établi au nom de « {data['raison_sociale']} », et non de la PME.",
                "CRITIQUE",
                ("raison_sociale",),
                {"similarity": round(similarity, 2)},
            )
    found.append(entity or Control("ENTITE_CORRESPOND", "NON_DETERMINE", "Entité non lue sur le document."))

    # DATE_VALIDITE (sur les dates lues, si l'utilisateur n'en a pas saisi).
    end = _date(data.get("date_validite") or data.get("date_fin"))
    issued = _date(data.get("date_delivrance"))
    if end:
        field_name = "date_validite" if data.get("date_validite") else "date_fin"
        if end < today:
            found.append(
                Control(
                    "DATE_VALIDITE",
                    "ECHEC",
                    f"Document expiré le {end:%d/%m/%Y}.",
                    "ELEVEE",
                    (field_name,),
                    {"expires_at": end.isoformat()},
                )
            )
        else:
            found.append(
                Control(
                    "DATE_VALIDITE",
                    "OK",
                    f"Valable jusqu'au {end:%d/%m/%Y}.",
                    fields=(field_name,),
                    details={"expires_at": end.isoformat()},
                )
            )

    # CONTENU_SUSPECT (indicatif) : dates impossibles. Jamais une accusation : une vérification.
    impossible = []
    if issued and issued > today:
        impossible.append("date de délivrance dans le futur")
    if issued and end and end < issued:
        impossible.append("fin de validité antérieure à la délivrance")
    start_fy, end_fy = _date(data.get("exercice_debut")), _date(data.get("exercice_fin"))
    if start_fy and end_fy and not 180 <= (end_fy - start_fy).days <= 550:
        impossible.append("durée d'exercice inhabituelle")
    if impossible:
        found.append(
            Control("CONTENU_SUSPECT", "ALERTE", "Dates à vérifier : " + ", ".join(impossible) + ".", "MOYENNE")
        )

    # PERIODE_ATTENDUE (sur la période lue).
    deadline = document.deadline
    start = _date(data.get("periode_debut") or data.get("exercice_debut"))
    stop = _date(data.get("periode_fin") or data.get("exercice_fin"))
    if deadline and stop:
        covers = (start or stop) <= deadline.period_start and stop >= deadline.period_end
        same_year = schema.document_type == "ETATS_FIN_SYSCOHADA" and stop.year == deadline.period_end.year
        ok = covers or same_year
        found.append(
            Control(
                "PERIODE_ATTENDUE",
                "OK" if ok else "ALERTE",
                f"Période attendue : {deadline.period_label}."
                + ("" if ok else f" Le document couvre une période close le {stop:%d/%m/%Y}."),
                "INFO" if ok else "ELEVEE",
                ("periode_fin",) if not ok else (),
            )
        )

    if schema.document_type == "ETATS_FIN_SYSCOHADA":
        found.extend(_financial_controls(pme, data, end_fy))
    if schema.document_type == "ATTEST_CNPS" and data.get("effectif_declare") is not None and pme.headcount:
        declared, read = pme.headcount, data["effectif_declare"]
        gap = abs(read - declared) / max(declared, 1)
        found.append(
            Control(
                "COHERENCE_EFFECTIF_CNPS",
                "OK" if gap <= 0.2 or abs(read - declared) <= 2 else "ALERTE",
                f"Effectif CNPS : {read} ; effectif déclaré : {declared}.",
                "INFO" if gap <= 0.2 or abs(read - declared) <= 2 else "MOYENNE",
                ("effectif_declare",),
            )
        )
    return found


def _financial_controls(pme, data: dict, fiscal_year_end: date | None) -> list[Control]:
    found = []
    assets, liabilities = data.get("total_actif"), data.get("total_passif")
    if assets and liabilities:
        gap = abs(assets - liabilities) / max(abs(assets), abs(liabilities))
        found.append(
            Control(
                "BILAN_EQUILIBRE",
                "OK" if gap <= 0.005 else "ALERTE",
                "Bilan équilibré."
                if gap <= 0.005
                else f"Total actif ({_fmt(assets)}) ≠ total passif ({_fmt(liabilities)}).",
                "INFO" if gap <= 0.005 else "ELEVEE",
                ("total_actif", "total_passif"),
                {"gap": round(gap, 4)},
            )
        )
    else:
        found.append(Control("BILAN_EQUILIBRE", "NON_DETERMINE", "Totaux du bilan non lus."))
    revenue = data.get("chiffre_affaires")
    declared = declared_input(pme, "ca_n")
    if revenue and declared:
        gap = abs(revenue - declared[0]) / max(abs(declared[0]), 1)
        severity = "INFO" if gap <= 0.10 else "ELEVEE" if gap > 0.30 else "MOYENNE"
        found.append(
            Control(
                "COHERENCE_CA_DECLARATIF",
                "OK" if gap <= 0.10 else "ALERTE",
                f"CA du document : {_fmt(revenue)} ; CA déclaré au questionnaire : {_fmt(declared[0])} "
                f"(écart {gap:.0%}).",
                severity,
                ("chiffre_affaires",),
                {"gap": round(gap, 3)},
            )
        )
    previous = (
        FinancialStatement.objects.filter(pme=pme, fiscal_year_end__lt=fiscal_year_end)
        .exclude(status=FinancialStatement.Status.ECARTE)
        .first()
        if fiscal_year_end
        else None
    )
    compared = {}
    if revenue and data.get("chiffre_affaires_n1"):
        compared["chiffre_affaires"] = (data["chiffre_affaires_n1"], revenue)
    if previous:
        mapping = {
            "chiffre_affaires": "ca_n",
            "resultat_net": "resultat_net",
            "capitaux_propres": "capitaux_propres",
            "total_passif": "total_passif",
        }
        for name, key in mapping.items():
            if data.get(name) and previous.values.get(key):
                compared.setdefault(name, (previous.values[key], data[name]))
    jumps = [
        f"{name.replace('_', ' ')} : {_fmt(before)} → {_fmt(after)}"
        for name, (before, after) in compared.items()
        if before and abs(after - before) / abs(before) > 0.5
    ]
    if compared:
        found.append(
            Control(
                "COHERENCE_N_N1",
                "ALERTE" if jumps else "OK",
                ("Variation de plus de 50 % à expliquer : " + " ; ".join(jumps) + ".")
                if jumps
                else "Variations N / N-1 dans les ordres de grandeur attendus.",
                "MOYENNE" if jumps else "INFO",
                tuple(name for name, _ in compared.items()) if jumps else (),
            )
        )
    # Seuils de régime fiscal : non codés tant qu'ils ne sont pas sourcés et vérifiés (RM-08).
    found.append(
        Control(
            "COHERENCE_REGIME_CA",
            "NON_DETERMINE",
            "Seuils des régimes fiscaux non configurés (règle à vérifier) : contrôle non réalisé.",
        )
    )
    return found


# --- Confiance (Document 4, § 6) ---------------------------------------------------------------------------------


def field_confidences(
    schema: ExtractionSchema, data: dict, model_conf: dict, reading: float, controls: list[Control]
) -> dict:
    factors: dict[str, float] = {}
    for control in controls:
        for name in control.fields:
            factors[name] = min(factors.get(name, 1.0), CONTROL_FACTOR[control.result])
    result = {}
    for f in schema.fields:
        if data.get(f.name) is None:
            continue
        model_value = model_conf.get(f.name)
        model_value = float(model_value) if isinstance(model_value, int | float) else 0.5
        result[f.name] = round(min(max(model_value, 0.0), 1.0, reading) * factors.get(f.name, 1.0), 3)
    return result


def document_confidence(schema: ExtractionSchema, confidences: dict) -> float:
    critical = schema.critical or schema.fields
    total = sum(f.weight for f in critical)
    return round(sum(f.weight * confidences.get(f.name, 0.0) for f in critical) / total, 3) if total else 0.0


def _coerce(schema: ExtractionSchema, raw: dict) -> dict:
    """Types attendus ; une valeur illisible devient ``None`` (jamais inventée)."""
    data = {}
    for f in schema.fields:
        value = raw.get(f.name)
        if value in ("", []):
            value = None
        if value is not None:
            if f.type == "number" and not isinstance(value, int | float):
                value = None
            elif f.type == "integer":
                value = int(value) if isinstance(value, int | float) else None
            elif f.type == "date" and _date(value) is None:
                value = None
            elif f.type == "boolean" and not isinstance(value, bool):
                value = None
        data[f.name] = value
    return data


# --- Orchestration ------------------------------------------------------------------------------------------------


def _type_message(document: Document, classified: str) -> str:
    looks_like = CLASSIFIABLE_TYPES.get(classified, "autre document")
    return f"Type attendu : {document.document_type.name} ; le document ressemble à : {looks_like}."


def _document_content(document: Document, text: str) -> str:
    return (
        f"Type attendu par le dépôt : {document.document_type.name} ({document.document_type.code}).\n"
        f"<donnees>\n{text[:MAX_TEXT]}\n</donnees>"
    )


def analyze(version: DocumentVersion, content: bytes) -> DocumentExtraction:
    """Analyse idempotente d'une version : ne remplace jamais une extraction déjà revue par un humain."""
    document = version.document
    existing = DocumentExtraction.objects.filter(version=version).first()
    if existing and existing.status in DocumentExtraction.REVIEWED:
        return existing
    extraction = existing or DocumentExtraction(version=version, expected_type=document.document_type.code)
    today = timezone.localdate()
    text = version.text_content or ""
    native = version.text_status == DocumentVersion.Text.TEXTE_NATIF and len(text.strip()) >= 25
    attachments = []
    if not native and version.extension in VISION_TYPES:
        attachments = [(VISION_TYPES[version.extension], content)]
    sensitive = document.document_type.sensitive
    pseudonymizer = for_pme(document.pme)
    refs = {"document": str(document.pk), "version": version.version_no, "sha256": version.sha256}
    reading = 1.0 if native else 0.85
    thresholds = _thresholds()

    # A. Classification.
    classification = gateway.run(
        prompt_code="doc.classify",
        content="Types possibles : "
        + "; ".join(f"{code} = {label}" for code, label in CLASSIFIABLE_TYPES.items())
        + f"; {AUTRE} = autre document.\n"
        + (_document_content(document, text) if native else "Document scanné : lire la pièce jointe."),
        schema=CLASSIFICATION_SCHEMA,
        context={"text": text},
        attachments=attachments,
        pme=document.pme,
        document_version=version,
        input_refs=refs,
        sensitive=sensitive,
        pseudonymizer=pseudonymizer,
        confidence_path="confidence",
    )
    extraction.classification_analysis = classification.analysis
    if not classification.ok:
        extraction.status = DocumentExtraction.Status.NON_ANALYSEE
        extraction.reason = (
            "Document scanné : lecture visuelle par le conseiller (IA externe non autorisée ou indisponible)."
            if attachments or not native
            else f"Analyse IA indisponible : {classification.analysis.error or classification.status}."
        )
        extraction.save()
        return extraction
    classified = classification.output["document_type"]
    class_conf = float(classification.output["confidence"])
    extraction.classified_type = classified
    extraction.classification_confidence = Decimal(str(round(class_conf, 3)))
    expected = document.document_type.code
    reasons: list[str] = []
    type_ok = classified == expected or class_conf < thresholds["auto"]
    if classified != expected:
        if class_conf >= thresholds["auto"]:
            reasons.append(f"le document ressemble à : {CLASSIFIABLE_TYPES.get(classified, 'autre document')}")
        else:
            reasons.append("type de document incertain")

    # B. Extraction (types du MVP).
    schema_type = (
        expected if expected in EXTRACTION_SCHEMAS else classified if classified in EXTRACTION_SCHEMAS else None
    )
    controls: list[Control] = []
    if schema_type is None:
        extraction.status = DocumentExtraction.Status.A_VERIFIER if reasons else DocumentExtraction.Status.PROVISOIRE
        extraction.reason = "; ".join(reasons) or "Type classé ; pas d'extraction structurée pour ce type (MVP)."
        extraction.confidence = extraction.classification_confidence
        if classified != expected and class_conf >= thresholds["auto"]:
            controls.append(
                Control(
                    "TYPE_ATTENDU",
                    "ALERTE",
                    _type_message(document, classified),
                    "ELEVEE",
                )
            )
        extraction.save()
        _store_checks(version, controls)
        return extraction
    schema = EXTRACTION_SCHEMAS[schema_type]
    result = gateway.run(
        prompt_code="doc.extract",
        content="Champs à extraire (nom : libellé, type) :\n"
        + "\n".join(f"- {f.name} : {f.label} ({f.type})" for f in schema.fields)
        + "\n"
        + (_document_content(document, text) if native else "Document scanné : lire la pièce jointe."),
        schema=schema.json_schema(),
        context={"text": text, "document_type": schema_type},
        attachments=attachments,
        pme=document.pme,
        document_version=version,
        input_refs={**refs, "schema": f"{schema.code}@{schema.version}"},
        sensitive=sensitive,
        pseudonymizer=pseudonymizer,
    )
    extraction.extraction_analysis = result.analysis
    extraction.schema_code, extraction.schema_version = schema.code, schema.version
    if not result.ok:
        extraction.status = DocumentExtraction.Status.A_VERIFIER
        extraction.reason = f"Extraction impossible : {result.analysis.error or result.status}."
        extraction.save()
        return extraction
    data = _coerce(schema, result.output["fields"])

    # C. Contrôles, D. confiance, E. routage (Document 4, § 7).
    controls = controls_for(document, schema, data, today)
    if not type_ok:
        controls.append(
            Control(
                "TYPE_ATTENDU",
                "ALERTE",
                _type_message(document, classified),
                "ELEVEE",
            )
        )
    confidences = field_confidences(schema, data, result.output.get("field_confidence", {}), reading, controls)
    doc_conf = document_confidence(schema, confidences)
    weak = [f.label for f in schema.critical if confidences.get(f.name, 0) < thresholds["field"]]
    serious = [c for c in controls if c.anomaly and SEVERITY_ORDER.index(c.severity) >= 2]
    if weak:
        reasons.append("champs critiques incertains ou absents : " + ", ".join(weak))
    if serious:
        reasons.append("anomalie : " + "; ".join(c.message for c in serious))
    if doc_conf < thresholds["auto"]:
        reasons.append(f"confiance du document {doc_conf:.0%} < {thresholds['auto']:.0%}")
    extraction.data = data
    extraction.field_confidence = confidences
    extraction.confidence = Decimal(str(doc_conf))
    extraction.status = DocumentExtraction.Status.A_VERIFIER if reasons else DocumentExtraction.Status.PROVISOIRE
    extraction.reason = "; ".join(dict.fromkeys(reasons))[:300]
    extraction.save()
    _store_checks(version, controls)
    if schema_type == "ETATS_FIN_SYSCOHADA" and extraction.status == DocumentExtraction.Status.PROVISOIRE:
        upsert_statement(extraction, verified=False)
    return extraction


def _thresholds() -> dict:
    organization = gateway._organization()
    return {
        "auto": float(organization.setting("ai_auto_threshold")),
        "field": float(organization.setting("ai_field_threshold")),
    }


def _store_checks(version: DocumentVersion, controls: list[Control]) -> None:
    existing = {c.check_code: c for c in version.checks.all()}
    for control in controls:
        # Une date ou une période saisie par l'utilisateur prime sur la lecture (contrôle déjà réalisé).
        previous = existing.get(control.code)
        if previous and control.code in ("DATE_VALIDITE", "PERIODE_ATTENDUE") and previous.result != "NON_DETERMINE":
            continue
        DocumentCheck.objects.update_or_create(
            version=version,
            check_code=control.code,
            defaults={
                "result": control.result,
                "message": control.message[:300],
                "details": {
                    **control.details,
                    "severity": control.severity,
                    "anomaly": control.anomaly,
                    "source": "IA",
                },
            },
        )


# --- États financiers ---------------------------------------------------------------------------------------------


def statement_values(data: dict) -> dict:
    from .schemas import FINANCIAL_INPUT_MAP

    values = {}
    for key, fields in FINANCIAL_INPUT_MAP.items():
        parts = [data.get(name) for name in fields]
        # Un agrégat (actif / passif circulant) n'est calculé que si TOUTES ses composantes ont été lues.
        if all(p is not None for p in parts):
            values[key] = sum(parts)
    return values


def upsert_statement(extraction: DocumentExtraction, *, verified: bool, user=None) -> FinancialStatement | None:
    end = _date(extraction.data.get("exercice_fin"))
    if end is None:
        return None
    version = extraction.version
    pme = version.document.pme
    current = FinancialStatement.objects.filter(pme=pme, fiscal_year_end=end).first()
    if current and current.status == FinancialStatement.Status.VERIFIE and not verified:
        return current  # une extraction provisoire ne remplace jamais des comptes vérifiés
    values = statement_values(extraction.data)
    defaults = {
        "system": extraction.data.get("systeme") or "",
        "values": values,
        "status": FinancialStatement.Status.VERIFIE if verified else FinancialStatement.Status.PROVISOIRE,
        "source_version": version,
        "confidence": extraction.confidence,
        "verified_by": user if verified else None,
        "verified_at": timezone.now() if verified else None,
    }
    statement, _ = FinancialStatement.objects.update_or_create(pme=pme, fiscal_year_end=end, defaults=defaults)
    return statement


def review(
    extraction: DocumentExtraction, access, *, status: str, corrections: dict, comment: str
) -> DocumentExtraction:
    """Revue humaine d'une extraction : valider, corriger (justifié) ou rejeter (human_review, Document 4, § 7)."""
    from rest_framework.exceptions import PermissionDenied, ValidationError

    from pme360.audit import services as audit
    from pme360.core.exceptions import BusinessError
    from pme360.documents.services import after_evidence_change

    if not access.has("ai.review"):
        raise PermissionDenied()
    if status not in DocumentExtraction.REVIEWED:
        raise ValidationError({"status": ["Statut de revue inconnu."]})
    if extraction.schema_code == "" and status != DocumentExtraction.Status.REJETEE and corrections:
        raise BusinessError("Ce type de document n'a pas de champs extraits.", code="no_schema")
    schema = EXTRACTION_SCHEMAS.get(extraction.schema_code)
    comment = comment.strip()
    if status in (DocumentExtraction.Status.CORRIGEE, DocumentExtraction.Status.REJETEE) and not comment:
        raise ValidationError({"comment": ["Justifiez la correction ou le rejet (RM-06)."]})
    changes = {}
    if status == DocumentExtraction.Status.CORRIGEE:
        if not corrections:
            raise ValidationError({"corrections": ["Aucune correction fournie."]})
        unknown = [name for name in corrections if schema is None or schema.field(name) is None]
        if unknown:
            raise ValidationError({"corrections": [f"Champ inconnu : {', '.join(unknown)}."]})
        coerced = _coerce(schema, {**extraction.data, **corrections})
        for name in corrections:
            if coerced.get(name) != extraction.data.get(name):
                changes[name] = {"before": extraction.data.get(name), "after": coerced.get(name)}
        extraction.data = coerced
        extraction.field_confidence = {**extraction.field_confidence, **{name: 1.0 for name in changes}}
    before_status = extraction.status
    extraction.status = status
    extraction.corrections = changes
    extraction.review_comment = comment
    extraction.reviewed_by = access.user
    extraction.reviewed_at = timezone.now()
    extraction.save()
    audit.record(
        "ai.extraction_reviewed",
        instance=extraction,
        pme_id=extraction.version.document.pme_id,
        before={"status": before_status},
        after={"status": status, "corrections": changes, "comment": comment},
    )
    if extraction.schema_code == "ETATS_FIN_SYSCOHADA":
        pme = extraction.version.document.pme
        if status == DocumentExtraction.Status.REJETEE:
            FinancialStatement.objects.filter(source_version=extraction.version).exclude(
                status=FinancialStatement.Status.VERIFIE
            ).update(status=FinancialStatement.Status.ECARTE)
        else:
            upsert_statement(extraction, verified=True, user=access.user)
        after_evidence_change(pme)
    return extraction


def ai_enabled() -> bool:
    return settings.PME360_AI_ENABLED
