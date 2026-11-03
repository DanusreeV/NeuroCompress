"""Create sample images in backend/samples (synthetic always; a few public-domain/CC0 photos if scikit-image is installed)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from PIL import Image  # noqa: E402

from neurocompress import samples as S  # noqa: E402

out = ROOT / "backend" / "samples"
out.mkdir(parents=True, exist_ok=True)
for name, gen in S.GENERATORS.items():
    Image.fromarray(gen()).save(out / f"{name}.png", optimize=True)
    print("wrote", name)
try:
    from skimage import data
    for name in ("astronaut", "coffee", "chelsea"):  # public domain / CC0 images distributed with scikit-image
        im = Image.fromarray(getattr(data, name)())
        im.thumbnail((256, 256), Image.LANCZOS)
        im.save(out / f"photo_{name}.png", optimize=True)
        print("wrote photo_" + name)
except Exception as e:  # noqa: BLE001
    print("scikit-image not available, skipping photos:", e)
