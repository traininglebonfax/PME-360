"""Analyse antivirus (Document 2, § 8.2) : ClamAV (``clamd``, protocole INSTREAM) en production.

``EicarScanner`` ne détecte QUE le fichier de test EICAR : il sert au développement et aux tests quand ClamAV
n'est pas démarré. La configuration de production refuse de démarrer avec lui (``config/settings/prod.py``).
"""

from __future__ import annotations

import socket
import struct
from dataclasses import dataclass

from django.conf import settings

# Chaîne de test EICAR, assemblée à l'exécution : écrite d'un seul bloc, ce fichier source serait lui-même
# mis en quarantaine par l'antivirus du poste de développement.
EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$" + b"EICAR-STANDARD-ANTIVIRUS-" + b"TEST-FILE!$H+H*"
CHUNK = 64 * 1024


@dataclass(frozen=True)
class ScanResult:
    clean: bool
    signature: str | None
    engine: str


class ScannerUnavailable(RuntimeError):
    pass


class EicarScanner:
    engine = "eicar-dev"

    def scan(self, content: bytes) -> ScanResult:
        infected = EICAR in content
        return ScanResult(
            clean=not infected, signature="Eicar-Test-Signature" if infected else None, engine=self.engine
        )


class ClamdScanner:
    engine = "clamav"

    def __init__(self, host: str, port: int, timeout: float = 30.0):
        self.host, self.port, self.timeout = host, port, timeout

    def scan(self, content: bytes) -> ScanResult:
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
                sock.sendall(b"zINSTREAM\0")
                for start in range(0, len(content), CHUNK):
                    chunk = content[start : start + CHUNK]
                    sock.sendall(struct.pack("!L", len(chunk)) + chunk)
                sock.sendall(struct.pack("!L", 0))
                response = b""
                while not response.endswith(b"\0"):
                    data = sock.recv(4096)
                    if not data:
                        break
                    response += data
        except OSError as exc:
            raise ScannerUnavailable(f"ClamAV injoignable ({self.host}:{self.port})") from exc
        text = response.rstrip(b"\0").decode("utf-8", "replace")
        if text.endswith("OK"):
            return ScanResult(clean=True, signature=None, engine=self.engine)
        if text.endswith("FOUND"):
            return ScanResult(
                clean=False, signature=text.split(":", 1)[-1].removesuffix("FOUND").strip(), engine=self.engine
            )
        raise ScannerUnavailable(f"Réponse ClamAV inattendue : {text}")


def get_scanner():
    if settings.PME360_ANTIVIRUS == "clamd":
        return ClamdScanner(settings.PME360_CLAMD_HOST, settings.PME360_CLAMD_PORT)
    return EicarScanner()
