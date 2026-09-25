"""Contrôles de sécurité des fichiers déposés (Document 2, § 8.2 ; Document 8, § 7).

Tout est vérifié sur le CONTENU, jamais sur la seule extension :
- liste blanche d'extensions ET signature binaire réelle (« magic bytes ») concordante ;
- taille maximale ; archives Office bornées (protection contre les bombes de décompression) ;
- macros Office refusées (formats macro, ``vbaProject.bin``, flux VBA des anciens formats) ;
- PDF actifs refusés (JavaScript, lancement d'application, fichiers joints, contenus multimédias).
Le fichier accepté est ensuite analysé par l'antivirus avant tout autre traitement (pipeline).
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field

from django.conf import settings

# Extension → types MIME acceptés (Document 8, § 7).
ALLOWED = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".csv": "text/csv",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".heic": "image/heic",
}
MACRO_EXTENSIONS = {".docm", ".xlsm", ".xltm", ".dotm", ".pptm", ".xlam", ".ppam"}
PDF_ACTIVE_MARKERS = (b"/JavaScript", b"/JS", b"/Launch", b"/EmbeddedFile", b"/RichMedia", b"/XFA")
OLE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
VBA_OLE_MARKERS = ("_VBA_PROJECT".encode("utf-16-le"), b"_VBA_PROJECT", "VBA".encode("utf-16-le") + b"\x00\x00")
MAX_ZIP_ENTRIES = 5_000
MAX_ZIP_RATIO = 100


class RejectedFile(ValueError):
    """Fichier refusé : ``code`` stable pour l'API, ``message`` en langage simple pour l'utilisateur."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Inspection:
    extension: str
    mime: str
    findings: list[str] = field(default_factory=list)


def _extension(filename: str) -> str:
    match = re.search(r"(\.[A-Za-z0-9]{1,6})$", filename or "")
    return match.group(1).lower() if match else ""


def _detect(content: bytes) -> str | None:
    head = content[:16]
    if head.startswith(b"%PDF-"):
        return "pdf"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head.startswith(b"PK\x03\x04"):
        return "zip"
    if head.startswith(OLE_SIGNATURE):
        return "ole"
    if content[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1", b"ftyphevc"):
        return "heic"
    return None


def _check_zip_office(content: bytes, extension: str) -> None:
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise RejectedFile(
            "corrupted_file", "Le fichier est endommagé ou n'est pas un document Office valide."
        ) from exc
    entries = archive.infolist()
    if len(entries) > MAX_ZIP_ENTRIES:
        raise RejectedFile("suspicious_archive", "Le document contient une structure anormale et a été refusé.")
    total = sum(entry.file_size for entry in entries)
    if total > settings.PME360_MAX_UNCOMPRESSED_BYTES or total > MAX_ZIP_RATIO * max(len(content), 1):
        raise RejectedFile("suspicious_archive", "Le document contient une structure anormale et a été refusé.")
    names = {entry.filename.lower() for entry in entries}
    if "[content_types].xml" not in names:
        raise RejectedFile("mime_mismatch", "Le contenu du fichier ne correspond pas à son extension.")
    expected_root = "word/" if extension == ".docx" else "xl/"
    if not any(name.startswith(expected_root) for name in names):
        raise RejectedFile("mime_mismatch", "Le contenu du fichier ne correspond pas à son extension.")
    content_types = archive.read("[Content_Types].xml").decode("utf-8", "ignore").lower()
    if any(name.endswith("vbaproject.bin") for name in names) or "macroenabled" in content_types:
        raise RejectedFile(
            "macro_refused", "Les documents contenant des macros sont refusés. Enregistrez-le sans macro."
        )


def _check_pdf(content: bytes) -> list[str]:
    for marker in PDF_ACTIVE_MARKERS:
        # Les noms PDF sont délimités : « /JS » ne doit pas correspondre à « /JSomething ».
        if re.search(re.escape(marker) + rb"(?![A-Za-z])", content):
            raise RejectedFile(
                "active_pdf_refused",
                "Ce PDF contient des éléments actifs (script ou fichier joint). "
                "Imprimez-le en PDF puis déposez-le à nouveau.",
            )
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content), strict=False)
        root = reader.trailer["/Root"]
        names = root.get("/Names", {})
        if "/JavaScript" in names or "/EmbeddedFiles" in names or "/AA" in root:
            raise RejectedFile("active_pdf_refused", "Ce PDF contient des éléments actifs et a été refusé.")
        if reader.is_encrypted:
            raise RejectedFile(
                "encrypted_pdf", "Ce PDF est protégé par un mot de passe. Déposez une version non protégée."
            )
    except RejectedFile:
        raise
    except Exception as exc:  # PDF illisible
        raise RejectedFile("corrupted_file", "Le PDF est endommagé et ne peut pas être lu.") from exc
    return []


def _check_csv(content: bytes) -> None:
    if b"\x00" in content[:65536]:
        raise RejectedFile("mime_mismatch", "Le contenu du fichier ne correspond pas à un fichier CSV.")
    for encoding in ("utf-8", "cp1252"):
        try:
            content[:65536].decode(encoding)
            return
        except UnicodeDecodeError:
            continue
    raise RejectedFile("mime_mismatch", "Le contenu du fichier ne correspond pas à un fichier CSV.")


def inspect(content: bytes, filename: str) -> Inspection:
    """Contrôle un fichier ; lève ``RejectedFile`` s'il doit être refusé."""
    extension = _extension(filename)
    if extension in MACRO_EXTENSIONS:
        raise RejectedFile(
            "macro_refused", "Les documents contenant des macros sont refusés. Enregistrez-le sans macro."
        )
    if extension not in ALLOWED:
        raise RejectedFile(
            "extension_refused", "Format non accepté. Formats autorisés : PDF, Word, Excel, CSV, JPG, PNG, HEIC."
        )
    if not content:
        raise RejectedFile("empty_file", "Le fichier est vide.")
    if len(content) > settings.PME360_MAX_UPLOAD_BYTES:
        limit = settings.PME360_MAX_UPLOAD_BYTES // (1024 * 1024)
        raise RejectedFile("file_too_large", f"Le fichier dépasse la taille maximale autorisée ({limit} Mo).")

    detected = _detect(content)
    expected = {
        ".pdf": "pdf",
        ".docx": "zip",
        ".xlsx": "zip",
        ".xls": "ole",
        ".jpg": "jpeg",
        ".jpeg": "jpeg",
        ".png": "png",
        ".heic": "heic",
        ".csv": None,
    }[extension]
    if detected != expected:
        raise RejectedFile("mime_mismatch", "Le contenu du fichier ne correspond pas à son extension.")
    findings: list[str] = []
    if extension in (".docx", ".xlsx"):
        _check_zip_office(content, extension)
    elif extension == ".xls" and any(marker in content for marker in VBA_OLE_MARKERS):
        raise RejectedFile(
            "macro_refused", "Les documents contenant des macros sont refusés. Enregistrez-le sans macro."
        )
    elif extension == ".pdf":
        findings += _check_pdf(content)
    elif extension == ".csv":
        _check_csv(content)
    return Inspection(extension=extension, mime=ALLOWED[extension], findings=findings)
