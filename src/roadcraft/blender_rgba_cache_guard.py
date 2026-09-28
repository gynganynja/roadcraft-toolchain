"""Opt-in, process-local guard for the reviewed SDK's RGBA cache-key lifetime.

Use only around a pinned scratch export. The installed SDK and source Blend are
never changed; the original packer is restored even if export raises.
"""

from __future__ import annotations

from contextlib import contextmanager
import math
from typing import Iterator


ASSET_NAME = "cat_d11t_v2"
BLEND_SHA256 = "1eadf10af8525e2bd72e0db43cba20e05bcb1014c4e8e09354228f7c79115731"
BASELINE_USF_SHA256 = "096a3cc042e382becb69e25c722dbaf0e2c2a65608cf6ff01008705eb0bad24a"
BLENDER_SHA256 = "e27fbfea8564aa645d4463cb0949695fd85562b9de6df9561b06859a1074adf7"
SDK_MESH_SHA256 = "4ab671128044524524028dbea32a5c7dcaf5274630348de151592c87b08be337"


class RgbaCacheGuardError(RuntimeError):
    """The requested guard is outside its reviewed scratch-export scope."""


def require_pins(*, asset_name: str, blend_sha256: str,
                 baseline_usf_sha256: str, blender_sha256: str,
                 sdk_mesh_sha256: str, blender_version: str | None = None) -> None:
    """Reject any unreviewed asset, runtime, or SDK before a scratch write."""
    if (asset_name != ASSET_NAME or blend_sha256 != BLEND_SHA256 or
            baseline_usf_sha256 != BASELINE_USF_SHA256 or
            blender_sha256 != BLENDER_SHA256 or
            sdk_mesh_sha256 != SDK_MESH_SHA256 or
            (blender_version is not None and
             not blender_version.startswith("Blender 5.2.") and
             not blender_version.startswith("5.2."))):
        raise RgbaCacheGuardError("RGBA cache guard source, Blender, or SDK pin differs")


@contextmanager
def immutable_rgba_cache(color_set_class, rgba_cache: dict) -> Iterator[dict]:
    """Snapshot every live RGBA before the original SDK lookup and pack.

    The original packer's numeric expression remains authoritative. Its cache
    sees only immutable tuples during this context, so a freed bpy_prop_array
    cannot later resolve to another mesh's packed value.
    """
    if (not isinstance(rgba_cache, dict) or
            getattr(color_set_class, "FAST_PACK", None) is not False):
        raise RgbaCacheGuardError("reviewed SDK RGBA cache or packing mode differs")
    original_pack = getattr(color_set_class, "rgba_to_saber", None)
    if not callable(original_pack):
        raise RgbaCacheGuardError("reviewed SDK RGBA packer is missing")

    state = {"schemaVersion": 1, "enabled": True, "packCalls": 0,
             "restored": False, "cacheClearedAfter": False}

    def snapshot_pack(rgba):
        try:
            channels = tuple(float(channel) for channel in rgba)
        except (TypeError, ValueError, OverflowError) as exc:
            raise RgbaCacheGuardError("invalid live RGBA value") from exc
        if len(channels) != 4 or not all(math.isfinite(c) for c in channels):
            raise RgbaCacheGuardError("invalid live RGBA value")
        state["packCalls"] += 1
        return original_pack(channels)

    rgba_cache.clear()
    color_set_class.rgba_to_saber = staticmethod(snapshot_pack)
    try:
        yield state
    finally:
        color_set_class.rgba_to_saber = staticmethod(original_pack)
        rgba_cache.clear()
        state["restored"] = color_set_class.rgba_to_saber is original_pack
        state["cacheClearedAfter"] = len(rgba_cache) == 0
