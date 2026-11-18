"""Pinned identity of the WhiteboxTools BINARY (issue #733).

The ``whitebox`` pip wrapper only pins the *wrapper*. On first use it
downloads an UNVERSIONED ``WhiteboxTools_linux_amd64.zip`` from
whiteboxgeo.com (no checksum, no version in the URL); WBT 2.4.0 changed
``d8_flow_accumulation`` semantics that way and the productive pipeline
produced silent garbage until #730. Both Docker images therefore bake the
binary pinned by SHA256, and every ``_get_wbt`` singleton refuses to run
with any other build.

These constants are the single source of truth: the same values are mirrored
as ``ARG`` lines in ``Dockerfile`` and ``Dockerfile.geo``, and
``tests/test_ci_workflow_contracts.py`` fails the build when they drift. A
bump is deliberate work: download the new zip, verify the pipeline on the
real AOI, then update the SHA here and in both Dockerfiles in one change.
"""

from __future__ import annotations

import re

PINNED_WBT_VERSION = "2.4.0"
PINNED_WBT_SHA256 = "370493b569aaf84977fde95921f96d4a39c1820a2d36d907da9d53772295f440"
PINNED_WBT_ZIP_URL = "https://www.whiteboxgeo.com/WBT_Linux/WhiteboxTools_linux_amd64.zip"


def assert_pinned_wbt_version(wbt, *, expected: str = PINNED_WBT_VERSION) -> None:
    """Fail loud when the runtime WhiteboxTools binary is not the pinned build.

    ``wbt.version()`` returns the full banner (``WhiteboxTools v2.4.0 (c)
    ...``); the check uses a word boundary so a ``v2.4.05`` cannot pass as
    ``v2.4.0``. The #730 lesson is that a wrong build fails *silently* —
    garbage output from an unpinned binary must never flow through the
    pipeline.
    """
    banner = wbt.version()
    if not isinstance(banner, str):
        # The wrapper's version() CATCHES OSError and returns the exception
        # object instead of raising (whitebox_tools.py v2.3.6) — typically a
        # missing/non-executable binary at the package root.
        raise RuntimeError(
            "WhiteboxTools did not report a version banner (got "
            f"{banner!r}). The wrapper's version() returns the exception "
            "object instead of raising when the binary is missing or not "
            "executable at the package root. Check the baked binary "
            "placement in the image (issue #733)."
        )
    if not re.search(rf"v{re.escape(expected)}\b", banner):
        raise RuntimeError(
            "WhiteboxTools binary version mismatch: expected "
            f"v{expected}, got {banner!r}. The pipeline refuses to run "
            "with an unpinned binary (issue #733). Re-pin deliberately: "
            "update app/domains/geo/wbt_version.py and the ARG lines in "
            "Dockerfile + Dockerfile.geo in one change."
        )
