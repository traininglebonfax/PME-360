"""Interface commune des fournisseurs (Document 4, § 13 : abstraction de la passerelle, mode dégradé local)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from pme360.ai.prompts import Prompt


@dataclass
class StructuredRequest:
    prompt: Prompt
    model: str
    content: str  # message utilisateur (déjà pseudonymisé pour un fournisseur externe)
    schema: dict
    context: dict = field(default_factory=dict)  # paramètres structurés (utilisés par le moteur de règles local)
    attachments: list[tuple[str, bytes]] = field(default_factory=list)  # (type MIME, contenu) : lecture visuelle


@dataclass
class ProviderResult:
    output: dict
    model: str
    tokens_in: int = 0
    tokens_out: int = 0


class ProviderError(Exception):
    def __init__(self, message: str, *, transient: bool):
        super().__init__(message)
        self.transient = transient


class Provider(Protocol):
    name: str
    external: bool  # True : les données quittent l'infrastructure (politique du tenant + pseudonymisation)

    def supports(self, prompt: Prompt, attachments: bool) -> bool: ...

    def structured(self, request: StructuredRequest) -> ProviderResult: ...
