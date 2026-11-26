"""No AWS account needed: isolated local catalog image round-trip smoke test."""
import os
from io import BytesIO
from tempfile import TemporaryDirectory
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from app.agent import SandboxModel
from app.main import create_app


def main():
    with TemporaryDirectory(prefix="retailai-storage-") as directory:
        # Never touch the active RetailAI DB or the production S3 bucket.
        os.environ["RETAILAI_STORAGE_BACKEND"] = "local"
        os.environ["RETAILAI_STORAGE_LOCAL_DIR"] = str(Path(directory) / "assets")
        buf = BytesIO()
        Image.new("RGB", (96, 96), (90, 130, 185)).save(buf, format="PNG")
        api = create_app(f"sqlite:///{Path(directory) / 'smoke.db'}", agent_model=SandboxModel())
        with TestClient(api) as client:
            path = "/integrations/storage/products/N-P-HEELS/image"
            headers = {"X-Demo-Token": "demo-northstar-manager"}
            result = client.post(path, headers=headers,
                files={"image": ("test.png", buf.getvalue(), "image/png")})
            assert result.status_code == 201, result.text
            downloaded = client.get(path, headers=headers)
            assert downloaded.status_code == 200, downloaded.text
            with Image.open(BytesIO(downloaded.content)) as image:
                assert image.format == "JPEG" and image.size == (96, 96)
            blocked = client.get(path, headers={"X-Demo-Token": "demo-river-manager"})
            assert blocked.status_code == 404
            print("RetailAI storage smoke: PASS")
            print("Backend: local")
            print("Private photo upload, JPEG normalization, retrieval, tenant isolation: PASS")
            print("No AWS calls or changes to your RetailAI application database.")


if __name__ == "__main__":
    main()
