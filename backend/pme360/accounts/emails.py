"""E-mails transactionnels du module comptes (texte brut, langage simple).

Les modèles configurables par tenant (``notification_template``) arrivent avec le module Notifications ;
ces messages d'authentification restent système.
"""

from django.conf import settings
from django.core.mail import send_mail


def send_login_code(email: str, full_name: str, code: str) -> None:
    send_mail(
        subject=f"Votre code de connexion PME360 : {code}",
        message=(
            f"Bonjour {full_name},\n\n"
            f"Voici votre code de connexion : {code}\n\n"
            f"Il est valable {settings.OTP_TTL_MINUTES} minutes et ne peut servir qu'une fois.\n"
            "Si vous n'avez pas demandé ce code, ignorez ce message.\n\n"
            "L'équipe PME360"
        ),
        from_email=None,
        recipient_list=[email],
    )


def send_password_link(email: str, full_name: str, link: str, *, invitation: bool, organization_name: str = "") -> None:
    if invitation:
        subject = f"Invitation à rejoindre {organization_name or 'PME360'}"
        intro = (
            f"Vous êtes invité(e) à rejoindre l'espace {organization_name or 'PME360'}.\n\n"
            "Choisissez votre mot de passe"
        )
    else:
        subject = "Réinitialisation de votre mot de passe PME360"
        intro = "Une réinitialisation de votre mot de passe a été demandée.\n\nChoisissez un nouveau mot de passe"
    send_mail(
        subject=subject,
        message=(
            f"Bonjour {full_name},\n\n{intro} en ouvrant ce lien (valable 3 jours) :\n{link}\n\n"
            "Si vous n'êtes pas à l'origine de cette demande, ignorez ce message.\n\nL'équipe PME360"
        ),
        from_email=None,
        recipient_list=[email],
    )


def send_pme_invitation(email: str, full_name: str, organization_name: str, pme_name: str) -> None:
    send_mail(
        subject=f"{organization_name} vous invite sur PME360",
        message=(
            f"Bonjour {full_name},\n\n"
            f"{organization_name} vous donne accès à l'espace de {pme_name} sur PME360.\n"
            f"Pour vous connecter, ouvrez {settings.FRONTEND_URL}/connexion, choisissez « Espace PME » "
            "et saisissez votre adresse e-mail : vous recevrez un code de connexion.\n\n"
            "L'équipe PME360"
        ),
        from_email=None,
        recipient_list=[email],
    )
