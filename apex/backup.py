"""Explicit opt-in S3-compatible off-site backup (AWS S3 / compatible object stores)."""
from __future__ import annotations
import os
from pathlib import Path
from .storage import APEXStore


class BackupNotConfigured(RuntimeError): pass


def upload_sqlite_backup(store: APEXStore, *, bucket: str | None = None,
                         prefix: str | None = None, endpoint_url: str | None = None) -> dict:
    """Create an integrity-checked local snapshot, then upload it to object storage.

    This is never run automatically. The caller must explicitly invoke it.
    Configure AWS credentials using the provider's secure environment variables.
    """
    bucket = bucket or os.getenv("APEX_S3_BUCKET")
    if not bucket:
        raise BackupNotConfigured("Set APEX_S3_BUCKET and cloud object-store credentials")
    try:
        import boto3
    except ImportError as exc:
        raise BackupNotConfigured("The S3 SDK is not installed; rebuild APEX after adding boto3") from exc
    import tempfile
    with tempfile.TemporaryDirectory(prefix="apex-backup-") as tmp:
        local = Path(tmp) / "apex.sqlite3"
        metadata = store.backup(str(local))
        client = boto3.client("s3", endpoint_url=endpoint_url or os.getenv("APEX_S3_ENDPOINT_URL"))
        key = "/".join(x.strip("/") for x in (prefix or os.getenv("APEX_S3_PREFIX", "apex"), local.name))
        client.upload_file(str(local), bucket, key, ExtraArgs={
            "Metadata": {"sha256": metadata["sha256"], "integrity": "ok"},
        })
    return {"bucket": bucket, "key": key, "sha256": metadata["sha256"],
            "bytes": metadata["bytes"], "integrity": "ok"}
