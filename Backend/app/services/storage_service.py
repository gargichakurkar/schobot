from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


class StorageError(RuntimeError):
    pass


class StorageService:
    def __init__(self) -> None:
        self.supabase_url = settings.supabase_url.rstrip("/") if settings.supabase_url else ""
        self.supabase_key = settings.supabase_service_role_key or settings.supabase_key or ""
        self.bucket = settings.supabase_storage_bucket or "student-documents"
        self.is_supabase_configured = bool(self.supabase_url and self.supabase_key)

        # Local storage fallback directory
        if settings.storage_local_dir:
            self.local_root = Path(settings.storage_local_dir)
        else:
            self.local_root = Path(".storage") / self.bucket
        if not self.is_supabase_configured and not self.is_production:
            self.local_root.mkdir(parents=True, exist_ok=True)

    @property
    def is_production(self) -> bool:
        env = (getattr(settings, "environment", None) or "development").strip().lower()
        return env == "production" or os.getenv("RENDER") == "true"

    def _assert_storage_available(self) -> None:
        if not self.is_supabase_configured and self.is_production:
            raise StorageError(
                "Production environment requires Supabase Storage configuration "
                "(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY). Local filesystem storage fallback is prohibited in production."
            )

    def upload_file(self, storage_path: str, file_bytes: bytes, content_type: str = "application/octet-stream") -> str:
        """Upload file bytes to storage. Returns the storage_path on success."""
        self._assert_storage_available()
        if self.is_supabase_configured:
            try:
                import httpx

                url = f"{self.supabase_url}/storage/v1/object/{self.bucket}/{storage_path}"
                headers = {
                    "Authorization": f"Bearer {self.supabase_key}",
                    "apikey": self.supabase_key,
                    "Content-Type": content_type,
                    "x-upsert": "true",
                }
                with httpx.Client(timeout=30.0) as client:
                    resp = client.post(url, content=file_bytes, headers=headers)
                    if resp.status_code not in (200, 201):
                        logger.error("Supabase Storage upload failed: %s %s", resp.status_code, resp.text)
                        raise StorageError(f"Supabase Storage error (HTTP {resp.status_code}): {resp.text}")
                return storage_path
            except StorageError:
                raise
            except Exception as exc:
                logger.error("Supabase Storage upload exception: %s", exc)
                raise StorageError(f"Failed to upload document to storage: {exc}") from exc
        else:
            # Local filesystem fallback (local dev / tests only)
            local_file = self.local_root / storage_path
            local_file.parent.mkdir(parents=True, exist_ok=True)
            local_file.write_bytes(file_bytes)
            return storage_path

    def download_file(self, storage_path: str) -> bytes:
        """Download file bytes from storage."""
        self._assert_storage_available()
        if self.is_supabase_configured:
            try:
                import httpx

                url = f"{self.supabase_url}/storage/v1/object/authenticated/{self.bucket}/{storage_path}"
                headers = {
                    "Authorization": f"Bearer {self.supabase_key}",
                    "apikey": self.supabase_key,
                }
                with httpx.Client(timeout=30.0) as client:
                    resp = client.get(url, headers=headers)
                    if resp.status_code != 200:
                        raise StorageError(f"Supabase Storage download error (HTTP {resp.status_code})")
                    return resp.content
            except Exception as exc:
                raise StorageError(f"Failed to download document: {exc}") from exc
        else:
            local_file = self.local_root / storage_path
            if not local_file.is_file():
                raise StorageError(f"File not found in storage: {storage_path}")
            return local_file.read_bytes()

    def create_signed_url(self, storage_path: str, expires_in: int = 3600) -> str:
        """Create a temporary authenticated signed URL for private document download."""
        self._assert_storage_available()
        if self.is_supabase_configured:
            try:
                import httpx

                url = f"{self.supabase_url}/storage/v1/object/sign/{self.bucket}/{storage_path}"
                headers = {
                    "Authorization": f"Bearer {self.supabase_key}",
                    "apikey": self.supabase_key,
                    "Content-Type": "application/json",
                }
                payload = {"expiresIn": expires_in}
                with httpx.Client(timeout=15.0) as client:
                    resp = client.post(url, json=payload, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        signed_path = data.get("signedURL") or data.get("signedUrl")
                        if signed_path:
                            if signed_path.startswith("http"):
                                return signed_path
                            return f"{self.supabase_url}/storage/v1{signed_path}"
            except Exception as exc:
                logger.warning("Could not generate Supabase signed URL: %s", exc)

        # Fallback to application download proxy endpoint
        return f"/api/student/documents/raw/{storage_path}"

    def delete_file(self, storage_path: str) -> bool:
        """Delete file from storage."""
        self._assert_storage_available()
        if self.is_supabase_configured:
            try:
                import httpx

                url = f"{self.supabase_url}/storage/v1/object/{self.bucket}"
                headers = {
                    "Authorization": f"Bearer {self.supabase_key}",
                    "apikey": self.supabase_key,
                    "Content-Type": "application/json",
                }
                payload = {"prefixes": [storage_path]}
                with httpx.Client(timeout=15.0) as client:
                    resp = client.request("DELETE", url, json=payload, headers=headers)
                    return resp.status_code == 200
            except Exception as exc:
                logger.warning("Failed to delete from Supabase Storage: %s", exc)
                return False
        else:
            local_file = self.local_root / storage_path
            if local_file.is_file():
                try:
                    local_file.unlink()
                    return True
                except OSError as exc:
                    logger.warning("Failed to delete local storage file: %s", exc)
                    return False
            return True


_default_storage_service: StorageService | None = None


def get_storage_service() -> StorageService:
    global _default_storage_service
    if _default_storage_service is None:
        _default_storage_service = StorageService()
    return _default_storage_service
