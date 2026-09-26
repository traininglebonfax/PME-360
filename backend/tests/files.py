"""Fichiers de test construits en mémoire (aucun fichier malveillant n'est écrit sur disque)."""

import io
import zipfile

from pypdf import PdfWriter

from pme360.documents.antivirus import EICAR


def pdf(text_pages: int = 1, javascript: bool = False) -> bytes:
    writer = PdfWriter()
    for _ in range(text_pages):
        writer.add_blank_page(width=595, height=842)
    if javascript:
        writer.add_js("app.alert('x');")
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def png() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def office(kind: str = "docx", macro: bool = False) -> bytes:
    """Archive Office minimale ; date fixe : deux appels donnent exactement les mêmes octets (doublons)."""

    def entry(name: str) -> zipfile.ZipInfo:
        return zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        content_type = "application/vnd.ms-word.document.macroEnabled.main+xml" if macro else "application/xml"
        archive.writestr(entry("[Content_Types].xml"), f'<Types><Override ContentType="{content_type}"/></Types>')
        root = "word/document.xml" if kind == "docx" else "xl/sharedStrings.xml"
        archive.writestr(entry(root), "<w:document><w:t>Organigramme de la société</w:t></w:document>")
        if macro:
            archive.writestr(entry(("word/" if kind == "docx" else "xl/") + "vbaProject.bin"), b"VBA")
    return buffer.getvalue()


def eicar_csv() -> bytes:
    return EICAR + b"\n"
