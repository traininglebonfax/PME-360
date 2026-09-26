"""Identité visuelle par organisation (marque blanche, V1).

Le logiciel s'appelle « PME360 » par défaut ; chaque organisation peut afficher son nom de produit, son nom court
(utilisé dans les libellés : « Équipe {nom} », « Mon conseiller {nom} »), sa couleur principale et son logo, dans
l'interface, les rapports PDF et les e-mails. Aucune donnée d'une organisation n'apparaît dans une autre.
"""

from __future__ import annotations

import base64
import binascii
import io
import re

from rest_framework.exceptions import ValidationError

DEFAULT_PRODUCT = "PME360"
DEFAULT_COLOR = "#2E4A6B"
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
LOGO_MAX_BYTES = 150_000
LOGO_TYPES = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}


def _luminance(hex_color: str) -> float:
    def channel(value: int) -> float:
        c = value / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast_with_white(hex_color: str) -> float:
    return 1.05 / (_luminance(hex_color) + 0.05)


def brand(organization) -> dict:
    """Identité effective (valeurs par défaut comprises), sûre à transmettre à l'interface."""
    data = organization.branding or {}
    return {
        "product_name": (data.get("product_name") or DEFAULT_PRODUCT).strip(),
        "short_name": (data.get("short_name") or organization.name).strip(),
        "primary_color": data.get("primary_color") if HEX.match(data.get("primary_color") or "") else DEFAULT_COLOR,
        "logo": data.get("logo") or None,
        "tagline": data.get("tagline") or "Connaître · Accompagner · Mesurer",
    }


def _validate_logo(value: str | None) -> str | None:
    if not value:
        return None
    match = re.match(r"^data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)$", value)
    if not match:
        raise ValidationError({"logo": ["Logo PNG, JPEG ou WebP attendu (les SVG ne sont pas acceptés)."]})
    try:
        raw = base64.b64decode(match.group(2), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValidationError({"logo": ["Image illisible."]}) from exc
    if len(raw) > LOGO_MAX_BYTES:
        raise ValidationError({"logo": [f"Logo trop lourd ({len(raw) // 1000} Ko) : 150 Ko au plus."]})
    from PIL import Image, UnidentifiedImageError

    try:
        image = Image.open(io.BytesIO(raw))
        image.verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValidationError({"logo": ["Image illisible ou corrompue."]}) from exc
    if image.format not in LOGO_TYPES:
        raise ValidationError({"logo": ["Logo PNG, JPEG ou WebP attendu."]})
    return f"data:{LOGO_TYPES[image.format]};base64,{match.group(2)}"


def validate(data: dict, current: dict | None = None) -> dict:
    """Nouvelle identité validée (les clés absentes gardent leur valeur actuelle)."""
    result = dict(current or {})
    errors: dict[str, list[str]] = {}
    for field, label, maximum in (
        ("product_name", "Nom du produit", 40),
        ("short_name", "Nom court", 40),
        ("tagline", "Slogan", 80),
    ):
        if field in data:
            value = (data[field] or "").strip()
            if len(value) > maximum:
                errors[field] = [f"{label} : {maximum} caractères au plus."]
            result[field] = value
    if "primary_color" in data:
        color = (data["primary_color"] or "").strip()
        if not HEX.match(color):
            errors["primary_color"] = ["Couleur au format #RRGGBB."]
        elif contrast_with_white(color) < 4.5:
            errors["primary_color"] = [
                f"Couleur trop claire : le texte blanc des boutons serait illisible "
                f"(contraste {contrast_with_white(color):.1f}:1, 4,5:1 au minimum). Choisissez une teinte plus foncée."
            ]
        else:
            result["primary_color"] = color.upper()
    if "logo" in data:
        try:
            result["logo"] = _validate_logo(data["logo"])
        except ValidationError as exc:
            errors.update(exc.detail)
    if errors:
        raise ValidationError(errors)
    return {k: v for k, v in result.items() if v not in (None, "")}


def current_brand() -> dict:
    """Identité de l'organisation courante (contexte de tenant) ; identité neutre à défaut."""
    from pme360.core.tenancy import current_org_id, system_context

    from .models import Organization

    org_id = current_org_id()
    organization = None
    if org_id is not None:
        with system_context():
            organization = Organization.objects.filter(pk=org_id).first()
    if organization is not None:
        return brand(organization)
    return {
        "product_name": DEFAULT_PRODUCT,
        "short_name": DEFAULT_PRODUCT,
        "primary_color": DEFAULT_COLOR,
        "logo": None,
        "tagline": "",
    }
