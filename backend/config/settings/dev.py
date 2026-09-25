from .base import *  # noqa: F403

DEBUG = True
LOG_JSON = env_bool("PME360_LOG_JSON", False)  # noqa: F405
# Sans worker Celery en développement, les tâches (traitement des documents) s exécutent immédiatement.
CELERY_TASK_ALWAYS_EAGER = env_bool("PME360_CELERY_EAGER", True)  # noqa: F405
