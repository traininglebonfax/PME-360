"""Clés par organisation et chiffrement enveloppe des fichiers (Document 2, § 8.2 et § 9 ; V1).

- Clé maîtresse (KEK) : hors base, ``PME360_STORAGE_MASTER_KEYS`` (clés Fernet ; la première enveloppe, toutes
  désenveloppent → rotation possible de la clé maîtresse sans rechiffrer les fichiers).
- Clé de données (DEK) : AES-256 propre à chaque organisation, stockée enveloppée (``OrganizationKey``) et versionnée.
- Objet chiffré : ``P360E1`` + version de clé (4 octets) + nonce (12 octets) + AES-256-GCM(contenu). Le chemin de
  l'objet sert de données associées : un fichier déplacé vers le préfixe d'une autre organisation ou d'une autre
  PME est refusé au déchiffrement.
- Un objet sans en-tête (déposé avant la V1) est relu tel quel ; ``manage.py encrypt_storage`` les chiffre.
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
import struct
import threading
import uuid

from cryptography.fernet import Fernet, MultiFernet
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils import timezone

from pme360.core.exceptions import BusinessError
from pme360.core.tenancy import current_org_id, system_context

MAGIC = b"P360E1"
HEADER = struct.Struct(">6sI12s")  # magic, version de clé, nonce
KEY_PATH = re.compile(r"^(?:org|reports)/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/")

_cache: dict[tuple[str, int], bytes] = {}
_lock = threading.Lock()


class StorageKeyError(BusinessError):
    """Clé introuvable, altération ou objet déplacé : le fichier n'est pas déchiffrable (erreur d'intégrité)."""

    default_code = "integrity_error"


def _master_keys() -> list[str]:
    keys = settings.STORAGE_MASTER_KEYS
    if not keys:
        raise ImproperlyConfigured("PME360_STORAGE_MASTER_KEYS n'est pas configuré.")
    return keys


def _master() -> MultiFernet:
    return MultiFernet([Fernet(k.encode()) for k in _master_keys()])


def master_key_id(key: str | None = None) -> str:
    return hashlib.sha256((key or _master_keys()[0]).encode()).hexdigest()[:16]


def organization_of(storage_key: str) -> uuid.UUID:
    match = KEY_PATH.match(storage_key)
    if not match:
        raise StorageKeyError(f"Chemin de stockage sans organisation : {storage_key}")
    org_id = uuid.UUID(match.group(1))
    current = current_org_id()
    if current is not None and str(current) != str(org_id):
        raise StorageKeyError("Accès à un fichier d'une autre organisation refusé.")
    return org_id


def _wrap(dek: bytes) -> str:
    return _master().encrypt(dek).decode()


def _unwrap(wrapped: str) -> bytes:
    return _master().decrypt(wrapped.encode())


def create_key(org_id, retire_previous: bool = True):
    """Nouvelle version de clé active (première clé ou rotation) ; renvoie l'``OrganizationKey`` créée."""
    from .models import OrganizationKey

    with system_context(), transaction.atomic():
        keys = OrganizationKey.objects.select_for_update().filter(organization_id=org_id)
        last = keys.order_by("-version").first()
        if retire_previous:
            keys.filter(status=OrganizationKey.Status.ACTIVE).update(
                status=OrganizationKey.Status.RETIRED, retired_at=timezone.now()
            )
        key = OrganizationKey.objects.create(
            organization_id=org_id,
            version=(last.version + 1) if last else 1,
            wrapped_key=_wrap(AESGCM.generate_key(bit_length=256)),
            master_key_id=master_key_id(),
        )
    return key


def _active(org_id) -> tuple[int, bytes]:
    from .models import OrganizationKey

    with system_context():
        key = OrganizationKey.objects.filter(organization_id=org_id, status=OrganizationKey.Status.ACTIVE).first()
    if key is None:
        with _lock:
            with system_context():
                key = OrganizationKey.objects.filter(
                    organization_id=org_id, status=OrganizationKey.Status.ACTIVE
                ).first()
            if key is None:
                key = create_key(org_id, retire_previous=False)
    return key.version, _dek(org_id, key.version, key.wrapped_key)


def _dek(org_id, version: int, wrapped: str | None = None) -> bytes:
    cache_key = (str(org_id), version)
    if cache_key in _cache:
        return _cache[cache_key]
    if wrapped is None:
        from .models import OrganizationKey

        with system_context():
            key = OrganizationKey.objects.filter(organization_id=org_id, version=version).first()
        if key is None:
            raise StorageKeyError(f"Clé de version {version} introuvable pour cette organisation.")
        wrapped = key.wrapped_key
    dek = _unwrap(wrapped)
    _cache[cache_key] = dek
    return dek


def clear_cache() -> None:
    _cache.clear()


def is_encrypted(blob: bytes) -> bool:
    return blob[: len(MAGIC)] == MAGIC


def key_version(blob: bytes) -> int | None:
    return HEADER.unpack(blob[: HEADER.size])[1] if is_encrypted(blob) else None


def encrypt(storage_key: str, content: bytes) -> bytes:
    org_id = organization_of(storage_key)
    version, dek = _active(org_id)
    nonce = os.urandom(12)
    return HEADER.pack(MAGIC, version, nonce) + AESGCM(dek).encrypt(nonce, content, storage_key.encode())


def decrypt(storage_key: str, blob: bytes) -> bytes:
    if not is_encrypted(blob):
        return blob  # fichier antérieur au chiffrement par organisation
    org_id = organization_of(storage_key)
    _, version, nonce = HEADER.unpack(blob[: HEADER.size])
    try:
        return AESGCM(_dek(org_id, version)).decrypt(nonce, blob[HEADER.size :], storage_key.encode())
    except Exception as exc:  # InvalidTag : contenu altéré ou objet déplacé
        raise StorageKeyError("Fichier illisible : contenu altéré, déplacé ou clé incorrecte.") from exc


def rewrap_all() -> int:
    """Après ajout d'une nouvelle clé maîtresse en tête de liste : ré-enveloppe toutes les clés de données."""
    from .models import OrganizationKey

    current = master_key_id()
    count = 0
    with system_context(), transaction.atomic():
        for key in OrganizationKey.objects.exclude(master_key_id=current).select_for_update():
            key.wrapped_key = _wrap(_unwrap(key.wrapped_key))
            key.master_key_id = current
            key.save(update_fields=["wrapped_key", "master_key_id", "updated_at"])
            count += 1
    clear_cache()
    return count


def development_key() -> str:
    """Clé maîtresse déterministe réservée au développement et aux tests (jamais en production)."""
    return base64.urlsafe_b64encode(hashlib.sha256(b"pme360-dev-storage-master-key").digest()).decode()
