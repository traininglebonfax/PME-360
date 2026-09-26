"""Fournisseur Anthropic (Claude) : offre API sans entraînement sur les données clients (décision D-03).

Sorties structurées par un outil de sortie forcé dont le schéma d'entrée est le JSON Schema de la tâche ;
la passerelle revalide la sortie (le fournisseur n'est jamais cru sur parole).
"""

from __future__ import annotations

import base64

from django.conf import settings

from pme360.ai.prompts import Prompt

from .base import ProviderError, ProviderResult, StructuredRequest

OUTPUT_TOOL = "enregistrer_resultat"


def _client():
    import anthropic

    return anthropic.Anthropic(
        api_key=settings.ANTHROPIC_API_KEY, timeout=settings.PME360_AI_TIMEOUT_SECONDS, max_retries=2
    )


def _raise_for(exc: Exception) -> ProviderError:
    import anthropic

    transient = isinstance(
        exc,
        anthropic.APIConnectionError
        | anthropic.APITimeoutError
        | anthropic.RateLimitError
        | anthropic.InternalServerError,
    )
    return ProviderError(f"{type(exc).__name__}: {str(exc)[:300]}", transient=transient)


def content_blocks(text: str, attachments: list[tuple[str, bytes]]) -> list[dict]:
    blocks: list[dict] = []
    for media_type, data in attachments:
        source = {"type": "base64", "media_type": media_type, "data": base64.b64encode(data).decode()}
        blocks.append({"type": "document" if media_type == "application/pdf" else "image", "source": source})
    blocks.append({"type": "text", "text": text})
    return blocks


class AnthropicProvider:
    name = "anthropic"
    external = True

    def supports(self, prompt: Prompt, attachments: bool) -> bool:
        return bool(settings.ANTHROPIC_API_KEY)

    def structured(self, request: StructuredRequest) -> ProviderResult:
        try:
            response = _client().messages.create(
                model=request.model,
                max_tokens=8192,
                system=request.prompt.system,
                messages=[{"role": "user", "content": content_blocks(request.content, request.attachments)}],
                tools=[
                    {
                        "name": OUTPUT_TOOL,
                        "description": "Enregistre le résultat structuré de la tâche.",
                        "input_schema": request.schema,
                    }
                ],
                tool_choice={"type": "tool", "name": OUTPUT_TOOL},
            )
        except Exception as exc:
            raise _raise_for(exc) from exc
        block = next((b for b in response.content if b.type == "tool_use"), None)
        if block is None:
            raise ProviderError("Réponse sans sortie structurée.", transient=False)
        return ProviderResult(
            output=dict(block.input),
            model=response.model,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
        )

    def chat(self, *, model: str, system: str, messages: list[dict], tools: list[dict], max_tokens: int = 4096):
        """Un tour de la boucle agentique Ask AI (outils en lecture seule)."""
        try:
            return _client().messages.create(
                model=model, max_tokens=max_tokens, system=system, messages=messages, tools=tools
            )
        except Exception as exc:
            raise _raise_for(exc) from exc
