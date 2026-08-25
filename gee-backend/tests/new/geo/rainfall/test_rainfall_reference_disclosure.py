"""The label surfaces of the six antecedent reference metrics (SDD S3, phase 5).

`design.md` D1 is explicit that the cost of flat sibling rows is NOT
labels-only: three allow-lists key on the literal string ``normal``, and a
metric named ``d7_normal`` matches none of them. Left alone it renders as its
raw wire key in the panel and as a period-LESS "Antecedente 7 días normal" in
the narrative and the workbook -- **beside** an annual "Normal 1991-2020" read
straight off the envelope, on one screen and in one downloaded file.

That is LI4-004 reproduced one metric over: one screen, two periods, one of
them asserted by a constant. The defect this file exists to prevent is not a
missing translation; it is a reader comparing two normals and having no way to
know they are computed over the same thirty years.

Scope here is the two PURE backend allow-lists -- `SUMMARY_METRIC_LABELS` /
`BASELINE_LABELED_METRICS` (`service.py`) and the export label path
(`export.py`). The real-PG half (the six riding into the CSV and the xlsx, the
suppressed ones surviving as rows) lives in `test_rainfall_export_xlsx.py`,
beside the fixtures it needs; the frontend half is
`consorcio-web/tests/unit/rainfallFormat.test.ts`.
"""

import pytest

# The six wire names S2a emits (`compute.py`, `antecedents[f"{name}_normal"]`).
# Written out rather than derived from a loop: the point of a pin is that a key
# renamed on the wire fails HERE, and a comprehension over the same source that
# produced them would rename itself along with it.
REFERENCE_NORMALS = ("d7_normal", "d30_normal", "d90_normal")
REFERENCE_PERCENTILES = ("d7_percentile", "d30_percentile", "d90_percentile")


class TestTheNormalsCarryTheServedPeriod:
    """5.1/5.2 -- `BASELINE_LABELED_METRICS` and the six Spanish labels."""

    @pytest.mark.parametrize("name", REFERENCE_NORMALS)
    def test_each_window_normal_is_a_baseline_labelled_metric(self, name: str) -> None:
        from app.domains.geo.rainfall.service import BASELINE_LABELED_METRICS

        assert name in BASELINE_LABELED_METRICS

    @pytest.mark.parametrize("name", REFERENCE_PERCENTILES)
    def test_no_window_percentile_is_baseline_labelled(self, name: str) -> None:
        """The annual rule, carried over rather than re-decided: a percentile's
        period belongs to the SENTENCE that states the rank ("Percentil 27 de
        1991-2020"), not to the metric's name. `percentile` is deliberately
        absent from this set (`service.py`'s own comment) and its three window
        siblings inherit that reason, not a new one."""
        from app.domains.geo.rainfall.service import BASELINE_LABELED_METRICS

        assert name not in BASELINE_LABELED_METRICS

    @pytest.mark.parametrize("name", REFERENCE_NORMALS + REFERENCE_PERCENTILES)
    def test_every_reference_key_has_a_spanish_label_of_its_own(self, name: str) -> None:
        """An unlabelled key degrades to its raw wire name -- honest, and
        unreadable. `summary_metric_label` cannot tell the two apart, so the
        assertion is that the label is NOT the key."""
        from app.domains.geo.rainfall.service import SUMMARY_METRIC_LABELS

        label = SUMMARY_METRIC_LABELS[name]
        assert label != name
        assert label.strip() == label and label != ""

    def test_the_period_travels_with_the_window_normal_from_the_envelope(self) -> None:
        """NOT 1991-2020: the expectation is derived from the argument, so a
        label that ignored the envelope and pasted a constant would fail."""
        from app.domains.geo.rainfall.service import summary_metric_label

        assert summary_metric_label("d7_normal", "2001-2030").endswith(" 2001-2030")
        assert summary_metric_label("d30_normal", "2001-2030").endswith(" 2001-2030")
        assert summary_metric_label("d90_normal", "2001-2030").endswith(" 2001-2030")

    def test_a_missing_baseline_yields_a_period_less_label_not_a_constant(self) -> None:
        """Honest degradation, same rule as `normal`: naming the metric without
        a period states what it IS; defaulting to a period asserts a baseline
        the envelope never carried."""
        from app.domains.geo.rainfall.service import SUMMARY_METRIC_LABELS, summary_metric_label

        assert summary_metric_label("d7_normal") == SUMMARY_METRIC_LABELS["d7_normal"]
        assert summary_metric_label("d7_normal", None) == SUMMARY_METRIC_LABELS["d7_normal"]
        assert summary_metric_label("d7_normal", "") == SUMMARY_METRIC_LABELS["d7_normal"]

    def test_the_li4_004_comparison_two_normals_one_period_on_one_surface(self) -> None:
        """**The defect class this whole slice exists to close.**

        One narrative, one envelope, four normals in it (the annual one and the
        three window ones). Every one of them must state the SAME period, and
        state it explicitly -- a reader comparing "Normal 1991-2020" against a
        bare "Antecedente 7 días normal" cannot know whether the second was
        computed over those same thirty years or over the seven days it names.

        The baseline is doctored away from 1991-2020 so a constant anywhere in
        the label path shows up as a period this envelope never served.
        """
        from app.domains.geo.rainfall.service import summary_metric_label

        baseline = "2001-2030"
        labels = [summary_metric_label(name, baseline) for name in ("normal", *REFERENCE_NORMALS)]

        assert all(label.endswith(f" {baseline}") for label in labels), labels
        # No two normals share a name: four rows reading "Normal 2001-2030" is
        # a different unreadable screen from four rows reading no period.
        assert len(set(labels)) == len(labels), labels
        assert not [label for label in labels if "1991" in label], labels


class TestTheExportLabelPathCarriesThemToo:
    """5.3/5.4 -- CSV and xlsx label the metric by its WIRE name.

    `metric_rows` flattens the groups away, so the sheet's label is keyed on
    `metric` rather than on the group key the narrative uses -- which is why
    `EXPORT_METRIC_ALIASES` exists at all (`annual_normal` on the wire is
    `normal` in the vocabulary). The six reference metrics need no alias
    because their wire name IS their vocabulary key; the assertion below is
    therefore on the BEHAVIOUR the aliases exist to produce, not on the
    presence of a mapping. See the deviation note in `tasks.md` 5.3/5.4.
    """

    @pytest.mark.parametrize("name", REFERENCE_NORMALS)
    def test_a_window_normal_row_carries_the_period_in_the_sheet(self, name: str) -> None:
        from app.domains.geo.rainfall.export import export_metric_label
        from app.domains.geo.rainfall.service import summary_metric_label

        assert export_metric_label(name, "2001-2030") == summary_metric_label(name, "2001-2030")
        assert export_metric_label(name, "2001-2030").endswith(" 2001-2030")

    @pytest.mark.parametrize("name", REFERENCE_PERCENTILES)
    def test_a_window_percentile_row_is_named_without_a_period(self, name: str) -> None:
        from app.domains.geo.rainfall.export import export_metric_label
        from app.domains.geo.rainfall.service import SUMMARY_METRIC_LABELS

        assert export_metric_label(name, "2001-2030") == SUMMARY_METRIC_LABELS[name]

    def test_the_six_are_never_relabelled_onto_the_annual_vocabulary(self) -> None:
        """The alias dict maps a wire name onto a SHARED vocabulary key, which
        is exactly how `d7_normal` could come to render as "Normal 1991-2020" --
        the annual row's own label -- in a sheet that also has an `annual_normal`
        row. Two rows, one label, two different numbers."""
        from app.domains.geo.rainfall.export import EXPORT_METRIC_ALIASES, export_metric_label

        labels = {
            name: export_metric_label(name, "1991-2020")
            for name in ("annual_normal", "annual_percentile", *REFERENCE_NORMALS)
            + REFERENCE_PERCENTILES
        }
        assert len(set(labels.values())) == len(labels), labels
        for name in REFERENCE_NORMALS + REFERENCE_PERCENTILES:
            assert EXPORT_METRIC_ALIASES.get(name, name) == name, name
