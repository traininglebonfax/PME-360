from .base import *  # noqa: F403

DEBUG = False
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)  # noqa: F405
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
MFA_ENFORCED = True

if not FIELD_ENCRYPTION_KEYS:  # noqa: F405
    raise RuntimeError("PME360_FIELD_ENCRYPTION_KEYS est obligatoire en production.")

if PME360_ANTIVIRUS != "clamd":  # noqa: F405
    raise RuntimeError("En production, l'antivirus ClamAV est obligatoire (PME360_ANTIVIRUS=clamd).")
if PME360_STORAGE_BACKEND != "s3":  # noqa: F405
    raise RuntimeError("En production, le stockage objet S3 est obligatoire (PME360_STORAGE_BACKEND=s3).")
PME360_S3_SSE = PME360_S3_SSE or "AES256"  # noqa: F405
