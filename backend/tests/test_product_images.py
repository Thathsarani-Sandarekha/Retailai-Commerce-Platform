"""The demo catalog uses only bundled images, with no external image services."""
import re
from pathlib import Path


def test_all_demo_product_images_are_bundled():
    project = Path(__file__).resolve().parents[2]
    frontend = project / 'frontend'
    images = (frontend / 'lib/product-images.ts').read_text(encoding='utf8')
    manifest = dict(re.findall(r'"(N-P-[A-Z]+)": "(/images/products/[a-z-]+\.webp)"', images))
    assert len(manifest) == 16
    assert len(set(manifest.values())) == 16
    for product_id, url_path in manifest.items():
        file = frontend / 'public' / url_path.lstrip('/')
        assert file.exists(), f'{product_id}: {file} not found'
        assert file.read_bytes().startswith(b'RIFF'), f'{product_id}: not a WebP file'
