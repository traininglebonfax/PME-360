"""Fournisseur local : moteur de règles, aucune donnée ne quitte l'infrastructure (mode dégradé, Document 4, § 3)."""

from __future__ import annotations

from pme360.ai import rules
from pme360.ai.prompts import LOCAL_ENGINE_VERSION, Prompt
from pme360.ai.schemas import EXTRACTION_SCHEMAS

from .base import ProviderError, ProviderResult, StructuredRequest


class LocalProvider:
    name = "local"
    external = False

    def supports(self, prompt: Prompt, attachments: bool) -> bool:
        # Pas de lecture visuelle (ni OCR installé) : un scan part en vérification humaine.
        return not attachments and prompt.code in {
            "doc.classify",
            "doc.extract",
            "diagnostic.prediagnostic",
            "finance.interpret",
        }

    def structured(self, request: StructuredRequest) -> ProviderResult:
        code, context = request.prompt.code, request.context
        if code == "doc.classify":
            output = rules.classify(context["text"])
        elif code == "doc.extract":
            output = rules.extract(EXTRACTION_SCHEMAS[context["document_type"]], context["text"])
        elif code == "diagnostic.prediagnostic":
            output = rules.prediagnose(context["criteria"])
        elif code == "finance.interpret":
            output = rules.interpret(context["metrics"])
        else:
            raise ProviderError(f"Tâche non prise en charge en local : {code}", transient=False)
        return ProviderResult(output=output, model=LOCAL_ENGINE_VERSION)
