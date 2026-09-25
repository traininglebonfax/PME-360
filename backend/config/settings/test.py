from .base import *  # noqa: F403

DEBUG = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # tests rapides uniquement
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CELERY_TASK_ALWAYS_EAGER = True
LOG_JSON = False
FIELD_ENCRYPTION_KEYS = FIELD_ENCRYPTION_KEYS or ["dGVzdC1rZXktdGVzdC1rZXktdGVzdC1rZXktdGVzdDE="]  # noqa: F405
