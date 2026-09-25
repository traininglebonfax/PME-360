"""Champ chiffré au niveau applicatif (Document 2, § 8.2) : Fernet, rotation de clés via MultiFernet."""

from functools import lru_cache

from cryptography.fernet import Fernet, MultiFernet
from django.conf import settings
from django.db import models


@lru_cache(maxsize=1)
def _fernet() -> MultiFernet:
    keys = settings.FIELD_ENCRYPTION_KEYS
    if not keys:
        raise RuntimeError("PME360_FIELD_ENCRYPTION_KEYS n'est pas configuré.")
    return MultiFernet([Fernet(key.encode()) for key in keys])


class EncryptedTextField(models.TextField):
    """Stocke le texte chiffré ; la valeur en clair n'existe qu'en mémoire."""

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value in (None, ""):
            return value
        return _fernet().encrypt(value.encode()).decode()

    def from_db_value(self, value, expression, connection):
        if value in (None, ""):
            return value
        return _fernet().decrypt(value.encode()).decode()
