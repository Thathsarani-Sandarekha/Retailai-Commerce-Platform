"""Local/S3 private catalog image integration, without external AWS calls."""
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from botocore.exceptions import ClientError

from app.agent import SandboxModel
from app.integrations.storage import (LocalStorage, S3Storage, StorageError,
                                      catalog_key, get_storage)
from app.main import create_app

MANAGER = {"X-Demo-Token": "demo-northstar-manager"}
STAFF = {"X-Demo-Token": "demo-northstar-agent"}
CUSTOMER = {"X-Demo-Token": "demo-northstar-customer-c3"}
RIVER_MANAGER = {"X-Demo-Token": "demo-river-manager"}
PATH = "/integrations/storage/products/N-P-HEELS/image"


def png_photo():
    out = BytesIO()
    im = Image.new("RGB", (200, 160), (31, 89, 156))
    im.save(out, "PNG", pnginfo=None)
    return out.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("RETAILAI_STORAGE_BACKEND", "local")
    monkeypatch.setenv("RETAILAI_STORAGE_LOCAL_DIR", str(tmp_path / "assets"))
    with TestClient(create_app(f"sqlite:///{tmp_path/'test.db'}", agent_model=SandboxModel())) as api:
        yield api, tmp_path


def test_manager_upload_and_private_staff_download(client):
    api, root = client
    result = api.post(PATH, headers=MANAGER, files={"image": ("shoe.png", png_photo(), "image/png")})
    assert result.status_code == 201, result.text
    assert result.json()["backend"] == "local"
    assert result.json()["storage_key"] == "catalog/northstar/N-P-HEELS/primary.jpg"
    assert result.json()["stored_bytes"] > 100
    saved = root / "assets/catalog/northstar/N-P-HEELS/primary.jpg"
    assert saved.exists()
    with Image.open(saved) as im:
        assert im.format == "JPEG"
        assert im.size == (200, 160)
        assert "exif" not in im.info
    response = api.get(PATH, headers=STAFF)
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.content == saved.read_bytes()
    events = api.get("/audit-events", headers=MANAGER).json()
    assert any(e["event"] == "catalog_image_uploaded" and e["resource_id"] == "N-P-HEELS" for e in events)
    status = api.get("/integrations/storage/status", headers=MANAGER).json()
    assert status == {"backend": "local", "images_private": True, "customer_style_uploads_saved": False}


def test_tenant_and_role_enforcement(client):
    api, _ = client
    payload = {"image": ("shoe.png", png_photo(), "image/png")}
    assert api.post(PATH, files=payload).status_code == 401
    assert api.post(PATH, headers=CUSTOMER, files=payload).status_code == 403
    assert api.post(PATH, headers=STAFF, files=payload).status_code == 403
    assert api.post(PATH, headers=RIVER_MANAGER, files=payload).status_code == 404
    assert api.get(PATH).status_code == 401
    assert api.get(PATH, headers=CUSTOMER).status_code == 403
    assert api.get(PATH, headers=RIVER_MANAGER).status_code == 404
    assert api.get(PATH, headers=STAFF).status_code == 404
    assert api.get("/integrations/storage/status", headers=CUSTOMER).status_code == 403


def test_malformed_and_oversized_upload_rejected(client):
    api, root = client
    assert api.post(PATH, headers=MANAGER, files={"image": ("payload.jpg", b"not a picture", "image/jpeg")}).status_code == 415
    assert api.post(PATH, headers=MANAGER, files={"image": ("payload.gif", b"GIF89a", "image/gif")}).status_code == 415
    assert api.post(PATH, headers=MANAGER, files={"image": ("big.jpg", b"x" * (4 * 1024 * 1024 + 1), "image/jpeg")}).status_code == 413
    assert api.post("/integrations/storage/products/unknown/image", headers=MANAGER,
                    files={"image": ("shoe.png", png_photo(), "image/png")}).status_code == 404
    assert not (root / "assets").exists()


def test_local_storage_key_validation_and_replacement(tmp_path):
    storage = LocalStorage(tmp_path / "storage")
    key = catalog_key("northstar", "N-P-HEELS")
    storage.put(key, b"first")
    storage.put(key, b"second")
    assert storage.get(key) == b"second"
    for bad in ["../escape.jpg", "catalog/northstar/../../etc/passwd", "catalog/a/b/other.jpg"]:
        with pytest.raises(ValueError):
            storage.put(bad, b"bytes")
    with pytest.raises(ValueError):
        catalog_key("..", "N-P-HEELS")


class FakeS3:
    def __init__(self):
        self.objects = {}
        self.writes = []
        self.fail = False

    def put_object(self, **kwargs):
        if self.fail:
            raise RuntimeError("secret AWS credentials and response")
        self.writes.append(kwargs)
        self.objects[kwargs["Key"]] = kwargs["Body"]

    def get_object(self, **kwargs):
        if self.fail:
            raise RuntimeError("secret AWS credentials and response")
        item = self.objects.get(kwargs["Key"])
        if item is None:
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "private details"}}, "GetObject")
        return {"Body": BytesIO(item), "ContentLength": len(item)}


def test_s3_put_get_private_encryption_and_prefix():
    fake = FakeS3()
    storage = S3Storage("retailai-assets-prod", "retailai/demo", client=fake)
    key = catalog_key("northstar", "N-P-HEELS")
    storage.put(key, b"jpeg-bytes")
    call = fake.writes[0]
    assert call["Bucket"] == "retailai-assets-prod"
    assert call["Key"] == "retailai/demo/catalog/northstar/N-P-HEELS/primary.jpg"
    assert call["ServerSideEncryption"] == "AES256"
    assert call["ContentType"] == "image/jpeg"
    assert "ACL" not in call
    assert storage.get(key) == b"jpeg-bytes"
    with pytest.raises(StorageError) as error:
        fake.fail = True
        storage.put(key, b"new")
    assert "secret" not in str(error.value)
    for bucket in ["", "bad_bucket", "localhost:9000", "bad..bucket"]:
        with pytest.raises(ValueError):
            S3Storage(bucket, client=fake)
    with pytest.raises(ValueError):
        S3Storage("retailai-assets-prod", "../unsafe", client=fake)


def test_fastapi_uses_s3_adapter_without_contacting_aws(tmp_path, monkeypatch):
    from app.integrations import storage

    fake = FakeS3()
    cloud = S3Storage("retailai-assets-prod", client=fake)
    monkeypatch.setattr(storage, "get_storage", lambda: cloud)
    with TestClient(create_app(f"sqlite:///{tmp_path/'s3.db'}", agent_model=SandboxModel())) as api:
        put = api.post(PATH, headers=MANAGER,
                       files={"image": ("shoe.png", png_photo(), "image/png")})
        assert put.status_code == 201, put.text
        assert put.json()["backend"] == "s3"
        assert api.get(PATH, headers=STAFF).status_code == 200
        assert api.get(PATH, headers=RIVER_MANAGER).status_code == 404
        fake.fail = True
        failure = api.get(PATH, headers=STAFF)
        assert failure.status_code == 503
        assert "secret" not in failure.text
        fail_put = api.post(PATH, headers=MANAGER,
                            files={"image": ("shoe.png", png_photo(), "image/png")})
        assert fail_put.status_code == 503
        assert "secret" not in fail_put.text


def test_storage_mode_selection_is_safe(monkeypatch, tmp_path):
    monkeypatch.setenv("RETAILAI_STORAGE_BACKEND", "local")
    monkeypatch.setenv("RETAILAI_STORAGE_LOCAL_DIR", str(tmp_path / "image-store"))
    assert get_storage().backend == "local"
    monkeypatch.setenv("RETAILAI_STORAGE_BACKEND", "unknown")
    with pytest.raises(ValueError):
        get_storage()
