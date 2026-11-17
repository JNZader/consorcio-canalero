"""Wiring contract of the COG conversion — the only rio-cogeo surface.

rio-cogeo is a geo-worker/runtime dependency with NO test coverage anywhere
(surfaced while reviewing the 5→7 major bump, PR #729: a green CI proved
nothing about this path). This pins the exact call shape
`convert_to_cog_impl` makes, so a major that changes the contract fails HERE
instead of in production tiles. The real-library smoke (rio-cogeo 7.0.4,
same call, synthetic 256x256 raster → overviews [2..32], tiled, deflate) ran
on 2026-11-17 and is recorded in the PR body.
"""

from __future__ import annotations

import importlib

mod = importlib.import_module("app.domains.geo.processing_raster_support")


class FakePath:
    def __init__(self, path: str):
        self._path = path

    def with_suffix(self, suffix: str) -> "FakePath":
        base = self._path.rsplit(".", 1)[0]
        return FakePath(base + suffix)

    def __str__(self) -> str:
        return self._path


def test_cog_translate_gets_the_documented_call_shape():
    calls: dict = {}

    def cog_translate_fn(src, dst, profile, **kwargs):
        calls["src"] = src
        calls["dst"] = dst
        calls["profile"] = profile
        calls["kwargs"] = kwargs

    out = mod.convert_to_cog_impl(
        path_cls=FakePath,
        ensure_parent_dir=lambda p: calls.setdefault("ensured", p),
        cog_translate_fn=cog_translate_fn,
        cog_profiles_get=lambda name: {"fake-profile": name},
        input_path="/data/in.tif",
        output_path=None,
    )
    assert out == "/data/in.cog.tif"  # sufijo .cog.tif por defecto
    assert calls["ensured"] == "/data/in.cog.tif"
    assert calls["profile"] == {"fake-profile": "deflate"}  # perfil deflate
    assert calls["kwargs"]["overview_level"] == 5
    assert calls["kwargs"]["overview_resampling"] == "nearest"
    assert calls["kwargs"]["quiet"] is True
    assert calls["kwargs"]["config"] == {
        "GDAL_NUM_THREADS": "ALL_CPUS",
        "GDAL_TIFF_OVR_BLOCKSIZE": "512",
    }


def test_explicit_output_path_is_honored():
    calls: dict = {}

    def cog_translate_fn(src, dst, profile, **kwargs):
        calls["dst"] = dst

    mod.convert_to_cog_impl(
        path_cls=FakePath,
        ensure_parent_dir=lambda p: None,
        cog_translate_fn=cog_translate_fn,
        cog_profiles_get=lambda name: {},
        input_path="/data/in.tif",
        output_path="/data/custom.cog.tif",
    )
    assert calls["dst"] == "/data/custom.cog.tif"
