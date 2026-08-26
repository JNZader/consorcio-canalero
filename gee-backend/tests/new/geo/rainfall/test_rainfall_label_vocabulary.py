"""BL-LABEL-VOCAB-GATE: the cross-language metric vocabulary is asserted, not narrated.

``service.SUMMARY_METRIC_LABELS`` (the sentence the backend writes into the
narrative and the export) and ``rainfallFormat.RAINFALL_METRIC_LABELS`` (the
badge the card draws) are hand-duplicated Spanish vocabularies. Until this file
the mirror was asserted in PROSE on BOTH sides and tested by nothing, so a
rename on one side shipped a screen naming one metric two ways -- LI4-004 with
the NAME instead of the period, in the same DOM subtree.

The gate reads the TypeScript source from pytest. That mechanism is not new
here: ``test_rainfall_reference_metrics.py`` already pins ``ANTECEDENT_ORDER``
the same way, for the same reason -- a contract that spans two languages has to
be checked somewhere, and the backend suite is the side that runs on every
change to either map's callers.

The two maps are deliberately NOT the same size. The frontend PRUNED the eight
``intensity`` labels (``p30``/``p60``/``p3h``/``p24h``/``i30``/``i60``/``peak``/
``duration``) because ``build_snapshot`` cannot emit that group, while the
backend keeps them for its CSV export. So the contract is asymmetric and stated
as such: every frontend key must exist on the backend with the SAME string, and
the backend-only surplus must be exactly that documented intensity set -- a new
backend label with no frontend counterpart is a decision, not a diff nobody
sees.
"""

from __future__ import annotations

import re
from pathlib import Path

# The eight labels the frontend pruned on purpose (rainfallFormat.ts:28-36).
# Pinned as a literal rather than derived from either map: derived, it would
# absorb whatever divergence appears and assert nothing.
_BACKEND_ONLY_KEYS = frozenset({"p30", "p60", "p3h", "p24h", "i30", "i60", "peak", "duration"})

_ENTRY = re.compile(r"^\s*'?(?P<key>[A-Za-z0-9_]+)'?\s*:\s*'(?P<value>[^']*)',\s*$")


def _repo_root() -> Path:
    # tests/new/geo/rainfall/<file> -> gee-backend -> repository root
    return Path(__file__).resolve().parents[4].parent


def _typescript_string_map(source: str, declaration: str) -> dict[str, str]:
    """Parse one ``const <declaration> ... = { ... };`` object literal.

    Comment lines and blank lines are skipped; every other line inside the
    block MUST parse, so a shape this parser does not understand fails the test
    instead of silently shrinking the map it compares.
    """
    assert declaration in source, f"{declaration} not found in the TypeScript source"
    block = source.split(declaration, 1)[1].split("= {", 1)[1].split("\n};", 1)[0]

    labels: dict[str, str] = {}
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("//", "/*", "*")):
            continue
        match = _ENTRY.match(line)
        assert match is not None, f"unparsed entry in {declaration}: {line!r}"
        labels[match.group("key")] = match.group("value")
    assert labels, f"{declaration} parsed empty"
    return labels


def _frontend_labels() -> dict[str, str]:
    source = (
        _repo_root() / "consorcio-web/src/components/map2d/rainfall/rainfallFormat.ts"
    ).read_text(encoding="utf-8")
    return _typescript_string_map(source, "const RAINFALL_METRIC_LABELS")


def test_every_frontend_metric_label_names_the_metric_the_backend_names():
    """The gate itself: key-for-key and string-for-string over the shared keys.

    Compared as whole dicts restricted to the frontend's key set, not key by
    key, so pytest's diff names every divergent pair at once instead of
    stopping at the first.
    """
    from app.domains.geo.rainfall.service import SUMMARY_METRIC_LABELS

    frontend = _frontend_labels()
    missing = sorted(set(frontend) - set(SUMMARY_METRIC_LABELS))
    assert not missing, f"frontend labels the backend does not know: {missing}"

    shared = {key: SUMMARY_METRIC_LABELS[key] for key in frontend}
    assert shared == frontend


def test_the_backend_only_labels_are_exactly_the_pruned_intensity_group():
    """The asymmetry is a decision, so it is pinned.

    Without this half, a backend label added with no frontend counterpart --
    exactly how a metric reaches a screen under its raw wire key -- passes the
    test above by construction, because that test only walks the frontend's
    keys.
    """
    from app.domains.geo.rainfall.service import SUMMARY_METRIC_LABELS

    surplus = set(SUMMARY_METRIC_LABELS) - set(_frontend_labels())
    assert surplus == set(_BACKEND_ONLY_KEYS)


def test_the_baseline_labelled_metric_sets_agree_across_the_two_languages():
    """``BASELINE_LABELED_METRICS`` (backend) / ``BASELINE_LABELLED_METRICS``
    (frontend) decide which labels get the served period appended.

    Same duplication, same prose-only mirror, and a divergence here is the
    original LI4-004: one surface reading "Normal 1991-2020" and another
    reading a bare "Normal" in the same fold.
    """
    from app.domains.geo.rainfall.service import BASELINE_LABELED_METRICS

    source = (
        _repo_root() / "consorcio-web/src/components/map2d/rainfall/rainfallFormat.ts"
    ).read_text(encoding="utf-8")
    block = source.split("const BASELINE_LABELLED_METRICS", 1)[1].split("]", 1)[0]
    frontend = set(re.findall(r"'([A-Za-z0-9_]+)'", block))

    assert frontend, "BASELINE_LABELLED_METRICS parsed empty"
    assert frontend == set(BASELINE_LABELED_METRICS)
