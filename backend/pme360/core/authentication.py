from rest_framework import authentication


class SessionAuthentication(authentication.SessionAuthentication):
    """Session Django + CSRF ; renvoie 401 (et non 403) quand aucune session n'est ouverte."""

    def authenticate_header(self, request) -> str:
        return 'Session realm="pme360"'
