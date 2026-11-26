"""Private, tenant-scoped product-image storage for the RetailAI catalog.

Local disk is the default. Set RETAILAI_STORAGE_BACKEND=s3 to use an IAM-authenticated
S3 client. Neither backend persists customer-owned Style Rescue uploads.
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Protocol

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import Actor, authenticate_staff, require_role
from ..models import Product
from ..services import audit
from ..style_rescue import MAX_UPLOAD, normalize_image

_SAFE_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$")
_SAFE_KEY = re.compile(r"^catalog/[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+/primary\.jpg$")
_BUCKET = re.compile(r"^(?=.{3,63}$)(?!\d+\.\d+\.\d+\.\d+$)[a-z0-9][a-z0-9.-]*[a-z0-9]$")
_PREFIX = re.compile(r"^[a-zA-Z0-9/_-]{1,96}$")


class StorageError(Exception):
    """A non-sensitive storage failure; never expose provider payloads."""


class StorageMissing(StorageError):
    pass


def catalog_key(tenant_id: str, product_id: str) -> str:
    if not _SAFE_ID.fullmatch(tenant_id) or not _SAFE_ID.fullmatch(product_id):
        raise ValueError("Invalid catalog identifier")
    return f"catalog/{tenant_id}/{product_id}/primary.jpg"


def _check_key(key: str) -> None:
    if not _SAFE_KEY.fullmatch(key):
        raise ValueError("Invalid storage key")


class Storage(Protocol):
    backend: str

    def put(self, key: str, body: bytes) -> None: ...
    def get(self, key: str) -> bytes: ...


class LocalStorage:
    backend = "local"

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        _check_key(key)
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise StorageError("Invalid local storage path")
        return path

    def put(self, key: str, body: bytes) -> None:
        path = self._path(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            # Atomic replacement protects readers from partially written JPEGs.
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".upload-", delete=False) as tmp:
                temp_name = tmp.name
                tmp.write(body)
            try:
                os.replace(temp_name, path)
            finally:
                Path(temp_name).unlink(missing_ok=True)
        except OSError:
            raise StorageError("Storage write failed") from None

    def get(self, key: str) -> bytes:
        path = self._path(key)
        try:
            return path.read_bytes()
        except FileNotFoundError:
            raise StorageMissing("Image not found") from None
        except OSError:
            raise StorageError("Storage read failed") from None


class S3Storage:
    backend = "s3"

    def __init__(self, bucket: str, prefix: str = "retailai", client=None):
        if not _BUCKET.fullmatch(bucket) or ".." in bucket or ".-" in bucket or "-." in bucket:
            raise ValueError("Invalid private S3 bucket name")
        if not _PREFIX.fullmatch(prefix) or "//" in prefix or ".." in prefix:
            raise ValueError("Invalid S3 object prefix")
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        if not self.prefix:
            raise ValueError("S3 object prefix must not be empty")
        if client is None:
            import boto3
            from botocore.config import Config
            client = boto3.client("s3", config=Config(
                connect_timeout=4, read_timeout=10,
                retries={"mode": "standard", "max_attempts": 3},
            ))
        self.client = client

    def _key(self, key: str) -> str:
        _check_key(key)
        return f"{self.prefix}/{key}"

    def put(self, key: str, body: bytes) -> None:
        try:
            self.client.put_object(
                Bucket=self.bucket, Key=self._key(key), Body=body,
                ContentType="image/jpeg", CacheControl="private, no-store",
                ServerSideEncryption="AES256",
            )
        except Exception:
            raise StorageError("S3 storage write failed") from None

    def get(self, key: str) -> bytes:
        from botocore.exceptions import ClientError
        try:
            res = self.client.get_object(Bucket=self.bucket, Key=self._key(key))
            if int(res.get("ContentLength", 0)) > MAX_UPLOAD:
                raise StorageError("Stored image exceeds maximum allowed size")
            body = res["Body"].read(MAX_UPLOAD + 1)
            if len(body) > MAX_UPLOAD:
                raise StorageError("Stored image exceeds maximum allowed size")
            return body
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"NoSuchKey", "404", "NotFound"}:
                raise StorageMissing("Image not found") from None
            raise StorageError("S3 storage read failed") from None
        except StorageError:
            raise
        except Exception:
            raise StorageError("S3 storage read failed") from None


def get_storage() -> Storage:
    """Resolve configuration lazily; importing and starting the API never contacts AWS."""
    backend = os.getenv("RETAILAI_STORAGE_BACKEND", "local").lower().strip()
    if backend == "local":
        return LocalStorage(os.getenv("RETAILAI_STORAGE_LOCAL_DIR", ".retailai_storage"))
    if backend == "s3":
        bucket = os.getenv("RETAILAI_S3_BUCKET", "")
        prefix = os.getenv("RETAILAI_S3_PREFIX", "retailai")
        return S3Storage(bucket, prefix)
    raise ValueError("Unknown RETAILAI_STORAGE_BACKEND")


def mount_storage_routes(app, db_session) -> None:
    router = APIRouter(prefix="/integrations/storage", tags=["RetailAI Private Catalog Image Storage"])

    def _product(db: Session, actor: Actor, product_id: str) -> Product:
        product = db.scalar(select(Product).where(
            Product.id == product_id, Product.tenant_id == actor.tenant_id,
        ))
        if product is None:
            raise HTTPException(404, "Product not found")
        return product

    def _storage() -> Storage:
        try:
            return get_storage()
        except (ValueError, RuntimeError, ImportError):
            raise HTTPException(503, "Storage configuration unavailable") from None

    @router.get("/status")
    def status(actor: Actor = Depends(authenticate_staff)):
        # No AWS credentials, paths or bucket names are returned.
        storage = _storage()
        return {"backend": storage.backend, "images_private": True,
                "customer_style_uploads_saved": False}

    @router.post("/products/{product_id}/image", status_code=201)
    async def upload_product_image(product_id: str, image: UploadFile = File(...),
                                   actor: Actor = Depends(authenticate_staff),
                                   db: Session = Depends(db_session)):
        require_role(actor, "manager")
        _product(db, actor, product_id)
        try:
            content = await image.read(MAX_UPLOAD + 1)
            clean_jpeg = normalize_image(content, image.content_type or "")
            store = _storage()
            key = catalog_key(actor.tenant_id, product_id)
            try:
                store.put(key, clean_jpeg)
            except StorageError:
                raise HTTPException(503, "Image storage unavailable") from None
            audit(db, actor, "catalog_image_uploaded", product_id, backend=store.backend)
            db.commit()
            return {"product_id": product_id, "storage_key": key,
                    "backend": store.backend, "content_type": "image/jpeg",
                    "stored_bytes": len(clean_jpeg)}
        finally:
            await image.close()

    @router.get("/products/{product_id}/image")
    def get_product_image(product_id: str, actor: Actor = Depends(authenticate_staff),
                          db: Session = Depends(db_session)):
        _product(db, actor, product_id)
        store = _storage()
        try:
            image = store.get(catalog_key(actor.tenant_id, product_id))
        except StorageMissing:
            raise HTTPException(404, "Product image not found") from None
        except StorageError:
            raise HTTPException(503, "Image storage unavailable") from None
        return Response(content=image, media_type="image/jpeg",
                        headers={"Cache-Control": "private, no-store",
                                 "X-Content-Type-Options": "nosniff"})

    app.include_router(router)
