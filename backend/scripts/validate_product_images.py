"""static-image regression checks, no FastAPI or API keys required."""
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
front = root / "frontend"
source = (front / "lib/product-images.ts").read_text(encoding="utf8")
matches = re.findall(r'"(N-P-[A-Z]+)": "(/images/products/[a-z-]+\.webp)"', source)
assert len(matches) == 16, f"Expected 16 mappings; found {len(matches)}"
assert len({pid for pid, _ in matches}) == 16
assert len({path for _, path in matches}) == 16
for pid, webpath in matches:
    image = front / "public" / webpath.lstrip("/")
    assert image.is_file(), f"{pid}: missing {image}"
    assert image.read_bytes()[:4] == b"RIFF", f"{pid}: not RIFF WebP"
    assert image.stat().st_size > 1000, f"{pid}: empty image"

views = [
    "app/shop/retail-catalog.tsx",
    "app/shop/cart-drawer.tsx",
    "app/shop/style/page.tsx",
    "app/shop/style/three-looks/page.tsx",
    "app/shop/style/rescue/page.tsx",
]
for view in views:
    assert "ProductPhoto" in (front / view).read_text(encoding="utf8"), f"Missing image in {view}"
print("PASS: 16 distinct local images mapped, WebP assets valid, all 5 views integrated")
