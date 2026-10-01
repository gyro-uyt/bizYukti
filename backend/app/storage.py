"""Media storage: local disk for development, any S3-compatible bucket in production."""

from pathlib import Path

from .config import settings


class LocalStorage:
    def __init__(self, root: str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, key: str, data: bytes, content_type: str) -> None:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def delete(self, key: str) -> None:
        (self.root / key).unlink(missing_ok=True)

    def read(self, key: str) -> bytes:
        return (self.root / key).read_bytes()


class S3Storage:
    def __init__(self) -> None:
        import boto3

        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url or None,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key or None,
            aws_secret_access_key=settings.s3_secret_key or None,
        )

    def save(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type,
                               CacheControl="public, max-age=31536000, immutable")

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def read(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()


_storage = None
_private = None


def get_private_storage():
    """Verification documents. Never served by the public /media route; admins stream them via the API."""
    global _private
    if _private is None:
        if settings.storage_backend == "s3":
            _private = S3Storage()
        else:
            _private = LocalStorage(settings.media_root.rstrip("/") + "_private")
    return _private


def get_storage():
    global _storage
    if _storage is None:
        _storage = S3Storage() if settings.storage_backend == "s3" else LocalStorage(settings.media_root)
    return _storage


def public_url(key: str | None) -> str | None:
    if not key:
        return None
    return f"{settings.media_public_base_url.rstrip('/')}/{key}"
