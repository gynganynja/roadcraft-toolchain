import unittest

try:
    import numpy as np
    from PIL import Image  # noqa: F401
except ImportError:  # optional dependency of roadcraft.normal_maps
    np = None

from roadcraft import normal_maps


def _height_field(size=128, seed=7):
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:size, 0:size].astype(float)
    h = np.zeros((size, size))
    for _ in range(25):                                  # rivets and panels: smooth bumps of mixed sizes
        cx, cy = rng.uniform(0, size, 2)
        r = rng.uniform(3, 14)
        h += rng.uniform(-1, 1) * np.exp(-((x - cx) ** 2 + (y - cy) ** 2) / (2 * r * r))
    return h * 6.0


def _normal_map(h, green_up):
    dhdx = np.zeros_like(h)
    dhdr = np.zeros_like(h)
    dhdx[:, 1:-1] = (h[:, 2:] - h[:, :-2]) / 2
    dhdr[1:-1, :] = (h[2:, :] - h[:-2, :]) / 2
    n = np.stack([-dhdx, dhdr if green_up else -dhdr, np.ones_like(h)], axis=-1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return np.clip((n + 1) * 127.5, 0, 255).astype(np.uint8)


@unittest.skipIf(np is None, "Pillow and numpy are optional dependencies of roadcraft.normal_maps")
class NormalConventionTests(unittest.TestCase):
    def test_directx_map_reads_positive(self):
        corr, count = normal_maps.correlation(_normal_map(_height_field(), green_up=False))
        self.assertGreater(count, 1000)
        self.assertGreater(corr, 0.5)

    def test_opengl_map_reads_negative(self):
        corr, _ = normal_maps.correlation(_normal_map(_height_field(), green_up=True))
        self.assertLess(corr, -0.5)

    def test_flip_turns_opengl_into_directx(self):
        h = _height_field(seed=3)
        flipped = normal_maps.to_directx(_normal_map(h, green_up=True))
        self.assertGreater(normal_maps.correlation(flipped)[0], 0.5)
        self.assertTrue(np.array_equal(flipped, _normal_map(h, green_up=False)) or
                        np.abs(flipped.astype(int) - _normal_map(h, green_up=False).astype(int)).max() <= 1)

    def test_flat_map_is_undecided(self):
        flat = np.full((64, 64, 3), (128, 128, 255), dtype=np.uint8)
        corr, count = normal_maps.correlation(flat)
        self.assertEqual((corr, count), (0.0, 0))


if __name__ == "__main__":
    unittest.main()
