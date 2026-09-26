from .base import *  # noqa: F403

DEBUG = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # tests rapides uniquement
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CELERY_TASK_ALWAYS_EAGER = True
LOG_JSON = False
FIELD_ENCRYPTION_KEYS = FIELD_ENCRYPTION_KEYS or ["dGVzdC1rZXktdGVzdC1rZXktdGVzdC1rZXktdGVzdDE="]  # noqa: F405
PME360_STORAGE_BACKEND = "local"
PME360_ANTIVIRUS = "eicar"
PME360_LOCAL_STORAGE_ROOT = str(BASE_DIR / "var" / "test-documents")  # noqa: F405
# Clé maîtresse de développement (déterministe, jamais en production) si aucune n'est fournie.
STORAGE_MASTER_KEYS = STORAGE_MASTER_KEYS or [  # noqa: F405
    __import__("base64")
    .urlsafe_b64encode(__import__("hashlib").sha256(b"pme360-dev-storage-master-key").digest())
    .decode()
]
