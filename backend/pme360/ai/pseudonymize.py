"""Minimisation et pseudonymisation avant tout envoi à un fournisseur externe (Document 4, § 3.2 ; décision D-03).

Les noms des personnes connues (dirigeants, associés, contacts), les e-mails, les téléphones et les numéros de
pièce d'identité sont remplacés par des jetons (« [PERSONNE_1] »), puis ré-injectés dans la réponse.
Les montants et libellés comptables ne sont pas des données personnelles : ils restent en clair.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Téléphones ivoiriens : +225 / 00225 facultatif puis 10 chiffres commençant par 0 (éventuellement groupés
# par deux). Un montant de 10 chiffres (« 2400000000 ») ne commence pas par 0 : il n'est pas masqué.
PHONE = re.compile(r"(?<![\d\w])(?:(?:\+|00)225[\s.-]?)?0[1-9](?:[\s.-]?\d{2}){4}(?!\d)")
# Pièces d'identité (CNI ivoirienne « C 0123 4567 89 », passeports) : lettre(s) + 8 à 11 chiffres.
IDENTITY = re.compile(
    r"\b(?:CNI|C\.N\.I\.|passeport|pièce)\s*(?:n°|no|num[ée]ro)?\s*:?\s*([A-Z]{1,2}\s?[\d\s]{8,13}\d)", re.I
)


@dataclass
class Pseudonymizer:
    names: list[str] = field(default_factory=list)
    mapping: dict[str, str] = field(default_factory=dict)  # jeton → valeur
    _reverse: dict[str, str] = field(default_factory=dict)

    def _token(self, kind: str, value: str) -> str:
        key = f"{kind}:{value.strip().lower()}"
        if key not in self._reverse:
            count = sum(1 for token in self.mapping if token.startswith(f"[{kind}_")) + 1
            token = f"[{kind}_{count}]"
            self.mapping[token] = value.strip()
            self._reverse[key] = token
        return self._reverse[key]

    def text(self, value: str) -> str:
        if not value:
            return value
        for name in sorted({n.strip() for n in self.names if n and len(n.strip()) >= 3}, key=len, reverse=True):
            value = re.sub(re.escape(name), lambda m: self._token("PERSONNE", m.group(0)), value, flags=re.I)
        value = EMAIL.sub(lambda m: self._token("EMAIL", m.group(0)), value)
        value = IDENTITY.sub(lambda m: m.group(0).replace(m.group(1), self._token("IDENTITE", m.group(1))), value)
        return PHONE.sub(lambda m: self._token("TELEPHONE", m.group(0)), value)

    def restore(self, value):
        """Ré-injection récursive dans la sortie structurée."""
        if isinstance(value, str):
            for token, original in self.mapping.items():
                value = value.replace(token, original)
            return value
        if isinstance(value, list):
            return [self.restore(item) for item in value]
        if isinstance(value, dict):
            return {key: self.restore(item) for key, item in value.items()}
        return value


def for_pme(pme) -> Pseudonymizer:
    """Pseudonymiseur alimenté par les personnes connues de la PME (dirigeants, associés, contacts)."""
    names: list[str] = []
    if pme is not None:
        for person in pme.persons.all():
            names.append(person.full_name)
            names.extend(part for part in person.full_name.split() if len(part) >= 4)
    return Pseudonymizer(names=names)
