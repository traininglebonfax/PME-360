"""Rendu HTML → PDF (Document 2 : gabarits HTML versionnés).

WeasyPrint est le moteur de référence (image de production Linux : Pango et HarfBuzz installés). Sans ses
bibliothèques natives (poste Windows de développement), xhtml2pdf, en Python pur, prend le relais sur le même
gabarit : celui-ci n'utilise que le sous-ensemble CSS commun aux deux moteurs.
"""

from __future__ import annotations

import contextlib
import io
import logging
from functools import cache

from django.conf import settings
from django.template.loader import render_to_string

# Polices de base des PDF (encodage WinAnsi) : quelques symboles sont remplacés par un équivalent lisible.
FALLBACKS = {
    "≥": ">=",
    "≤": "<=",
    "→": "->",
    "←": "<-",
    "✔": "OK",
    "✖": "X",
    "−": "-",
    " ": " ",
    " ": " ",
}


@cache
def engine() -> str:
    preferred = getattr(settings, "PME360_PDF_ENGINE", "auto")
    if preferred in ("weasyprint", "auto"):
        try:
            # WeasyPrint affiche un long avertissement quand Pango est absent : on le rend silencieux.
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                import weasyprint  # noqa: F401 — le chargement échoue sans Pango

            return "weasyprint"
        except (ImportError, OSError):
            if preferred == "weasyprint":
                raise
    return "xhtml2pdf"


def _winansi(html: str) -> str:
    for char, replacement in FALLBACKS.items():
        html = html.replace(char, replacement)
    return html.encode("cp1252", errors="replace").decode("cp1252")


def render_pdf(template: str, context: dict) -> tuple[bytes, str]:
    """Rend ``template`` en PDF ; renvoie (contenu, moteur utilisé)."""
    name = engine()
    html = render_to_string(template, {**context, "engine": name})
    if name == "weasyprint":
        import weasyprint

        return weasyprint.HTML(string=html).write_pdf(), name
    from xhtml2pdf import pisa

    logging.getLogger("xhtml2pdf").setLevel(logging.ERROR)  # propriétés CSS ignorées : sans conséquence

    output = io.BytesIO()
    result = pisa.CreatePDF(_winansi(html), dest=output, encoding="utf-8")
    if result.err:
        raise RuntimeError(f"Rendu PDF impossible ({result.err} erreur(s)).")
    return output.getvalue(), name
