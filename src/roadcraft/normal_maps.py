"""Which way a tangent-space normal map's green channel points: DirectX (Y-, RoadCraft's ``_nm``) or OpenGL (Y+).

A normal map baked from a height field h is integrable. Reading the slopes as p = dh/dx = -R/B and
q = dh/d(row down) = -G/B (the DirectX / engine reading), the mixed derivatives agree: dp/d(row) equals dq/dx,
so their correlation over the textured texels is positive. Read with the wrong green sign the correlation turns
negative. The sign is robust where the magnitude is not: baked maps mix flat panels, UV seams and compression
noise, so values of 0.1-0.3 are normal (WALL-E's four supplied maps: -0.12 to -0.29, OpenGL).

Optional dependency: Pillow and numpy (not part of the stdlib-only core); the functions import them on use.

    python -m roadcraft.normal_maps MAP.png [MAP2.png ...]
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class NormalConvention:
    path: str
    convention: str          # "directx" (RoadCraft) or "opengl"
    correlation: float       # corr(dp/drow, dq/dcol) under the DirectX reading
    texels: int              # texels with a non-flat slope that entered the measurement

    @property
    def needs_green_flip(self) -> bool:
        return self.convention == "opengl"


def _arrays(image: Any):
    import numpy as np  # optional dependency
    a = np.asarray(image, dtype=np.float64)
    if a.ndim != 3 or a.shape[2] < 3:
        raise ValueError("expected an RGB normal map")
    if a.max() > 1.5:
        a = a / 255.0
    n = a[..., :3] * 2.0 - 1.0
    return n[..., 0], n[..., 1], n[..., 2]


def correlation(image: Any, *, min_z: float = 0.35, min_slope: float = 0.01) -> tuple[float, int]:
    """Mixed-derivative correlation of an RGB normal map (array-like, 0-255 or 0-1) under the DirectX reading."""
    import numpy as np
    nx, ny, nz = _arrays(image)
    ok = nz > min_z
    nz = np.where(ok, nz, 1.0)
    p = -nx / nz
    q = -ny / nz
    dp = p[1:, :-1] - p[:-1, :-1]
    dq = q[:-1, 1:] - q[:-1, :-1]
    valid = ok[1:, 1:] & ok[:-1, :-1] & ok[1:, :-1] & ok[:-1, 1:]
    use = valid & ((np.abs(dp) > min_slope) | (np.abs(dq) > min_slope))
    count = int(use.sum())
    if count < 16:
        return 0.0, count
    a, b = dp[use], dq[use]
    if a.std() == 0 or b.std() == 0:
        return 0.0, count
    return float(np.corrcoef(a, b)[0, 1]), count


def measure(path: str | Path, *, blur: float = 0.0) -> NormalConvention:
    """Decide a map's convention. ``blur`` (pixels) can steady very noisy (JPEG) maps; the WALL-E maps gave the
    same sign with and without 1.5 px."""
    from PIL import Image, ImageFilter  # optional dependency
    image = Image.open(path).convert("RGB")
    if blur:
        image = image.filter(ImageFilter.GaussianBlur(blur))
    corr, count = correlation(image)
    return NormalConvention(str(path), "directx" if corr >= 0 else "opengl", corr, count)


def to_directx(image: Any):
    """Flip the green channel of an 8-bit RGB(A) map (OpenGL -> DirectX); returns a numpy array."""
    import numpy as np
    a = np.array(image, dtype=np.uint8, copy=True)
    a[..., 1] = 255 - a[..., 1]
    return a


def main(argv: list[str] | None = None) -> int:
    paths = sys.argv[1:] if argv is None else argv
    if not paths:
        print(__doc__)
        return 2
    for path in paths:
        r = measure(path)
        flip = " -> flip green for RoadCraft" if r.needs_green_flip else ""
        print(f"{path}: {r.convention} (correlation {r.correlation:+.3f} over {r.texels} texels){flip}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
