"""Paramètres communs à tous les environnements.

Toute valeur sensible ou dépendante de l'environnement est lue depuis les variables d'environnement
(cf. `.env.example`). Aucune règle métier n'est définie ici : elles sont stockées en base (Document 1, § 12).
"""

import os
from datetime import timedelta
from pathlib import Path

from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def _load_dotenv(path: Path) -> None:
    """Charge un fichier .env minimal (CLE=valeur) sans écraser l'environnement existant."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv(BASE_DIR / ".env")


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise RuntimeError(f"Variable d'environnement manquante : {name}")
    return value


def env_bool(name: str, default: bool = False) -> bool:
    return env(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


ENVIRONMENT = env("PME360_ENV", "dev")
SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = False
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.postgres",
    "rest_framework",
    "drf_spectacular",
    "pme360.core",
    "pme360.organizations",
    "pme360.accounts",
    "pme360.audit",
    "pme360.pmes",
    "pme360.diagnostic",
    "pme360.scoring",
    "pme360.documents",
    "pme360.compliance",
    "pme360.alerts",
    "pme360.notifications",
    "pme360.ai",
    "pme360.plans",
    "pme360.analytics",
    "pme360.reports",
    "pme360.dashboards",
]

MIDDLEWARE = [
    "pme360.core.middleware.RequestContextMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "pme360.core.middleware.TenantMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "pme360" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
    }
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", "pme360"),
        "USER": env("POSTGRES_USER", "pme360"),
        "PASSWORD": env("POSTGRES_PASSWORD", ""),
        "HOST": env("POSTGRES_HOST", "localhost"),
        "PORT": env("POSTGRES_PORT", "5442"),
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
        # Les transactions sont ouvertes par TenantMiddleware (une transaction par requête, RLS positionnée).
        "ATOMIC_REQUESTS": False,
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Sessions (Document 2, § 8.1) : 8 h glissantes côté GUDE, 30 jours sur appareil de confiance côté PME.
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_NAME = "pme360_session"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = int(timedelta(hours=8).total_seconds())
SESSION_SAVE_EVERY_REQUEST = True
PME_TRUSTED_DEVICE_SESSION_AGE = int(timedelta(days=30).total_seconds())
CSRF_COOKIE_NAME = "pme360_csrftoken"
CSRF_COOKIE_HTTPONLY = False  # lu par le frontend pour l'en-tête X-CSRFToken
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", "http://localhost:3010")

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# Authentification
MFA_ENFORCED = env_bool("PME360_MFA_ENFORCED", True)
MFA_ISSUER = "PME360"
LOGIN_MAX_FAILURES = 5
LOGIN_LOCK_MINUTES = 15
OTP_TTL_MINUTES = 10
OTP_MAX_ATTEMPTS = 5
OTP_MAX_PER_HOUR = int(env("PME360_OTP_MAX_PER_HOUR", "5"))
AUTH_PENDING_TTL_SECONDS = 600

# Chiffrement applicatif des champs sensibles (clés Fernet, la première chiffre, toutes déchiffrent).
FIELD_ENCRYPTION_KEYS = env_list("PME360_FIELD_ENCRYPTION_KEYS")

FRONTEND_URL = env("PME360_FRONTEND_URL", "http://localhost:3010")

# Documents (Document 2, § 8.2 ; Document 8, § 7)
PME360_MAX_UPLOAD_BYTES = int(env("PME360_MAX_UPLOAD_MB", "25")) * 1024 * 1024
PME360_MAX_UNCOMPRESSED_BYTES = 250 * 1024 * 1024
PME360_DOWNLOAD_URL_TTL = 300  # URL signée : 5 minutes
PME360_STORAGE_BACKEND = env("PME360_STORAGE_BACKEND", "local")  # local | s3
PME360_LOCAL_STORAGE_ROOT = env("PME360_LOCAL_STORAGE_ROOT", str(BASE_DIR / "var" / "documents"))
PME360_S3_ENDPOINT = env("PME360_S3_ENDPOINT", "")
PME360_S3_BUCKET = env("PME360_S3_BUCKET", "pme360-documents")
PME360_S3_ACCESS_KEY = env("PME360_S3_ACCESS_KEY", "")
PME360_S3_SECRET_KEY = env("PME360_S3_SECRET_KEY", "")
PME360_S3_REGION = env("PME360_S3_REGION", "us-east-1")
PME360_S3_SSE = env("PME360_S3_SSE", "")  # « AES256 » en production (chiffrement côté serveur)
PME360_S3_CREATE_BUCKET = env_bool("PME360_S3_CREATE_BUCKET", True)
PME360_ANTIVIRUS = env("PME360_ANTIVIRUS", "eicar")  # clamd (production) | eicar (développement uniquement)
PME360_CLAMD_HOST = env("PME360_CLAMD_HOST", "localhost")
PME360_CLAMD_PORT = int(env("PME360_CLAMD_PORT", "3310"))

# Échéances (Document 8, § 4)
PME360_DEADLINE_HORIZON_DAYS = 120

# IA (Document 4 ; décision D-03). Sans clé ou sans autorisation du tenant : moteur de règles local uniquement.
PME360_AI_ENABLED = env_bool("PME360_AI_ENABLED", True)
PME360_AI_PROVIDER = env("PME360_AI_PROVIDER", "local")  # local | anthropic
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", "")
PME360_AI_TIMEOUT_SECONDS = int(env("PME360_AI_TIMEOUT_SECONDS", "60"))
# Routage par tâche (Document 4, § 3.3) : classification → rapide ; extraction → standard ; synthèses → raisonnement.
PME360_AI_MODELS = {
    "fast": env("PME360_AI_MODEL_FAST", "claude-haiku-4-5-20251001"),
    "standard": env("PME360_AI_MODEL_STANDARD", "claude-sonnet-5"),
    "reasoning": env("PME360_AI_MODEL_REASONING", "claude-opus-5-5"),
}
# Prix en USD par million de jetons (entrée, sortie) : estimation à confirmer sur la grille tarifaire en vigueur.
PME360_AI_PRICING = {
    PME360_AI_MODELS["fast"]: (1.0, 5.0),
    PME360_AI_MODELS["standard"]: (3.0, 15.0),
    PME360_AI_MODELS["reasoning"]: (5.0, 25.0),
}
# Rapports PDF : auto = WeasyPrint si ses bibliothèques natives sont présentes, sinon xhtml2pdf (Document 2).
PME360_PDF_ENGINE = env("PME360_PDF_ENGINE", "auto")  # auto | weasyprint | xhtml2pdf
PME360_AI_MAX_TOOL_CALLS = 8  # Ask AI : boucle agentique limitée, lecture seule (Document 4, § 9)

LANGUAGE_CODE = "fr"
TIME_ZONE = "Africa/Abidjan"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", "localhost")
EMAIL_PORT = int(env("EMAIL_PORT", "1035"))
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", False)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "PME360 <no-reply@pme360.local>")

REDIS_URL = env("REDIS_URL", "redis://localhost:6390/0")
CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": REDIS_URL}}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["pme360.core.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["pme360.core.permissions.HasOrganizationPermission"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_PAGINATION_CLASS": "pme360.core.pagination.DefaultCursorPagination",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "pme360.core.exceptions.problem_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.UserRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        "user": "600/min",
        "auth": env("PME360_AUTH_RATE", "10/min"),
        "otp": env("PME360_OTP_RATE", "5/min"),
    },
    "PAGE_SIZE": 25,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "PME360 API",
    "DESCRIPTION": "API de la plateforme PME360 (instance GUDE-PME 360). Erreurs au format RFC 9457.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": "/api/v1",
    "COMPONENT_SPLIT_REQUEST": True,
    "ENUM_NAME_OVERRIDES": {
        "ScopeEnum": "pme360.accounts.models.Scope",
        "OrganizationStatusEnum": "pme360.organizations.models.Organization.Status",
        "LifecycleStatusEnum": "pme360.pmes.models.Pme.LifecycleStatus",
        "LoginStatusEnum": ["ok", "mfa_required", "mfa_setup_required"],
        "OrganizationTypeEnum": "pme360.organizations.models.Organization.Type",
        "DiagnosticStatusEnum": "pme360.diagnostic.models.Diagnostic.Status",
        "DiagnosticTypeEnum": "pme360.diagnostic.models.Diagnostic.Type",
        "FrameworkVersionStatusEnum": "pme360.diagnostic.models.FrameworkVersion.Status",
        "AssessmentStatusEnum": "pme360.diagnostic.models.CriterionAssessment.Status",
        "QuestionTypeEnum": "pme360.diagnostic.models.Question.Type",
        "SnapshotKindEnum": "pme360.scoring.models.ScoreSnapshot.Kind",
        "RoleEnum": "pme360.pmes.models.PmePerson.Role",
        "MessageRoleEnum": "pme360.ai.models.ConversationMessage.Role",
        "AiAnalysisStatusEnum": "pme360.ai.models.AiAnalysis.Status",
        "AiTaskEnum": "pme360.ai.models.AiAnalysis.Task",
        "ExtractionStatusEnum": "pme360.ai.models.DocumentExtraction.Status",
        "SuggestionStatusEnum": "pme360.ai.models.CriterionSuggestion.Status",
        "ActionStatusEnum": "pme360.plans.models.Action.Status",
        "ReportTypeEnum": "pme360.reports.models.Report.Type",
        "ActionPlanStatusEnum": "pme360.plans.models.ActionPlan.Status",
        "DeliverableStatusEnum": "pme360.plans.models.Deliverable.Status",
        "RecommendationStatusEnum": "pme360.plans.models.Recommendation.Status",
        "RecommendationRuleStatusEnum": "pme360.plans.models.RecommendationRule.Status",
    },
}

CELERY_BROKER_URL = REDIS_URL
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_TIME_LIMIT = 300
CELERY_BEAT_SCHEDULE = {
    "dispatch-outbox": {"task": "pme360.core.tasks.dispatch_outbox", "schedule": 10.0},
    "compliance-daily": {"task": "pme360.compliance.tasks.run_daily", "schedule": crontab(hour=2, minute=0)},
    # Vues analytiques : rafraîchies par événement (plafond 30 s) et au moins toutes les 15 minutes (retards datés).
    "analytics-refresh": {"task": "pme360.analytics.tasks.refresh_views", "schedule": 900.0},
    # Rapport trimestriel de portefeuille (anonymisé) le 1er jour de chaque trimestre, pour le trimestre écoulé.
    "portfolio-quarterly-report": {
        "task": "pme360.reports.tasks.generate_quarterly_portfolio_reports",
        "schedule": crontab(day_of_month=1, month_of_year="1,4,7,10", hour=3, minute=0),
    },
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
    "loggers": {"django.db.backends": {"level": "WARNING"}},
}
LOG_JSON = env_bool("PME360_LOG_JSON", True)
