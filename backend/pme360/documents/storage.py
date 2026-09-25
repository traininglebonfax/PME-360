"""Stockage des fichiers (Document 2, § 8.2) : stockage objet S3 (MinIO ou cloud) ou disque local (tests).

Les fichiers ne sont JAMAIS exposés par une URL publique : les clés sont préfixées par tenant et par PME, les noms
de fichiers sont régénérés, et le téléchargement passe par une URL signée à courte durée délivrée après contrôle
d'accès (``documents.views.FileDownloadView``).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from django.conf import settings


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError("Clé de stockage invalide.")
        return path

    def put(self, key: str, content: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class S3Storage:
    def __init__(self):
        import boto3
        from botocore.config import Config

        self.bucket = settings.PME360_S3_BUCKET
        self.sse = settings.PME360_S3_SSE
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.PME360_S3_ENDPOINT or None,
            aws_access_key_id=settings.PME360_S3_ACCESS_KEY,
            aws_secret_access_key=settings.PME360_S3_SECRET_KEY,
            region_name=settings.PME360_S3_REGION,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
        if settings.PME360_S3_CREATE_BUCKET:
            existing = {b["Name"] for b in self.client.list_buckets().get("Buckets", [])}
            if self.bucket not in existing:
                self.client.create_bucket(Bucket=self.bucket)

    def put(self, key: str, content: bytes, content_type: str) -> None:
        extra = {"ServerSideEncryption": self.sse} if self.sse else {}
        self.client.put_object(Bucket=self.bucket, Key=key, Body=content, ContentType=content_type, **extra)

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


@lru_cache(maxsize=1)
def get_storage():
    if settings.PME360_STORAGE_BACKEND == "s3":
        return S3Storage()
    return LocalStorage(Path(settings.PME360_LOCAL_STORAGE_ROOT))
