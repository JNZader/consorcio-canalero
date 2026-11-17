"""The D8 accumulation input is ALWAYS a pointer raster — say so explicitly.

WhiteboxTools 2.4.0 (downloaded on demand by the python wrapper, verified in
the container on 2026-11-17) stopped auto-detecting pointer inputs: without
``--pntr`` it interprets the pointer raster as a DEM and silently returns
garbage accumulation (max 34 cells where the correct run gives 487 848 —
reproduced on this AOI's own prod raster). The productive pipeline calls this
impl with ``flow_dir`` rasters only, so the flag is always correct here.
"""

from __future__ import annotations

import importlib

mod = importlib.import_module("app.domains.geo.processing_wbt_support")


class RecordingWbt:
    def __init__(self):
        self.method = None
        self.kwargs = {}

    def __getattr__(self, name):
        def call(*args, **kwargs):
            self.method = name
            self.kwargs = kwargs

        return call


def test_accumulation_declares_its_input_is_a_pointer(tmp_path):
    wbt = RecordingWbt()

    def run_wbt_tool(output_path, runner):
        runner(wbt, output_path)
        return output_path

    out = mod.compute_flow_accumulation_impl(
        run_wbt_tool=run_wbt_tool,
        flow_dir_path="/data/flow_dir.tif",
        output_path="flow_acc.tif",
    )
    assert out == "flow_acc.tif"
    assert wbt.method == "d8_flow_accumulation"
    assert wbt.kwargs.get("pntr") is True
    assert wbt.kwargs.get("out_type") == "cells"
