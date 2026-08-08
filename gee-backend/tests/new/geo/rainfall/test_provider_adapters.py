"""Provider adapter tests for the P3 wiring (fake GEE client, no network).

The concrete CHIRPS / IMERG adapters only talk to a ``GeeZonalClient``-shaped
object; every test substitutes a fake client so CI never touches the GEE
network. Real-catalog/auth behavior is covered separately by the read-only
validation spike (2026-08-07, engram obs #12820).
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.domains.geo.rainfall.adapters.chirps import (
    CHIRPS_V3_RNN_COLLECTION,
    CHIRPS_V3_SAT_COLLECTION,
    ChirpsV3Adapter,
)
from app.domains.geo.rainfall.adapters.gee_client import (
    UnknownProviderScope,
    asset_name_for,
)
from app.domains.geo.rainfall.adapters.imerg import IMERG_V07_COLLECTION, ImergV07Adapter
from app.domains.geo.rainfall.adapters.zonal import build_zonal_batch


class FakeGeeClient:
    """Deterministic stand-in for :class:`GeeZonalClient` (no ``ee`` import)."""

    def __init__(self, *, series=(), error=None, scale_meters: int = 1000) -> None:
        self.series = list(series)
        self.error = error
        self.scale_meters = scale_meters
        self.collections: list[tuple[str, datetime, datetime, object, str]] = []
        self.geometry_scope: tuple[str, str] | None = None

    def geometry(self, *, scope_kind: str, scope_id: str) -> object:
        self.geometry_scope = (scope_kind, scope_id)
        return ("asset", scope_kind, scope_id)

    def zonal_series(self, *, collection_id, start, end, geometry, band):
        self.collections.append((collection_id, start, end, geometry, band))
        if self.error is not None:
            raise self.error
        return list(self.series)


def _fetch_kwargs(start: datetime, end: datetime, *, source_id: str = "chirps-v3-final") -> dict:
    return {
        "source_id": source_id,
        "scope_kind": "zone",
        "scope_id": "z1",
        "scope_version": "v1",
        "start": start,
        "end": end,
    }


# ---------------------------------------------------------------------------
# CHIRPS v3
# ---------------------------------------------------------------------------


def test_chirps_rnn_adapter_fetches_daily_intervals_with_provider_revision():
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = datetime(2024, 1, 3, tzinfo=UTC)
    fake = FakeGeeClient(
        series=[
            (datetime(2024, 1, 1, tzinfo=UTC), 1.88),
            (datetime(2024, 1, 2, tzinfo=UTC), 1.12),
        ]
    )
    batch = ChirpsV3Adapter(gee=fake).fetch(**_fetch_kwargs(start, end))

    assert batch.cadence == timedelta(days=1)
    assert len(batch.intervals) == 2
    assert [interval.value for interval in batch.intervals] == [1.88, 1.12]
    assert all(interval.provider_revision == "v3-final" for interval in batch.intervals)
    assert all(interval.unit == "mm" for interval in batch.intervals)
    assert batch.coverage == 1.0
    assert batch.completeness == 1.0
    assert batch.checksum.startswith("sha256:")
    # Catalog ids are case sensitive — the exact validated collection must be used.
    assert fake.collections[0][0] == CHIRPS_V3_RNN_COLLECTION
    assert fake.geometry_scope == ("zone", "z1")


def test_chirps_sat_profile_maps_to_nrt_collection_and_daily_fallback_revision():
    start = datetime(2024, 1, 1, tzinfo=UTC)
    fake = FakeGeeClient(series=[(datetime(2024, 1, 1, tzinfo=UTC), 1.88)])
    batch = ChirpsV3Adapter(gee=fake).fetch(
        **_fetch_kwargs(start, datetime(2024, 1, 2, tzinfo=UTC), source_id="chirps-v3-sat")
    )

    assert fake.collections[0][0] == CHIRPS_V3_SAT_COLLECTION
    assert batch.intervals[0].provider_revision == "v3-nrt"


def test_chirps_adapter_rejects_unknown_source_id():
    start = datetime(2024, 1, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="unsupported CHIRPS"):
        ChirpsV3Adapter(gee=FakeGeeClient()).fetch(
            **_fetch_kwargs(start, datetime(2024, 1, 2, tzinfo=UTC), source_id="chirps-v2")
        )


# ---------------------------------------------------------------------------
# IMERG V07
# ---------------------------------------------------------------------------


def test_imerg_v07_adapter_builds_one_interval_per_30min_step():
    start = datetime(2024, 1, 1, tzinfo=UTC)
    fake = FakeGeeClient(
        series=[
            (start + timedelta(minutes=30 * i), value)
            for i, value in enumerate((0.077, 0.061, 0.050, 0.043))
        ]
    )
    batch = ImergV07Adapter(gee=fake).fetch(
        **_fetch_kwargs(start, start + timedelta(hours=2), source_id="imerg-v07")
    )

    assert batch.cadence == timedelta(minutes=30)
    assert len(batch.intervals) == 4
    assert [interval.value for interval in batch.intervals] == [0.077, 0.061, 0.050, 0.043]
    assert all(
        interval.interval_end - interval.interval_start == timedelta(minutes=30)
        for interval in batch.intervals
    )
    assert all(interval.provider_revision == "v07" for interval in batch.intervals)
    assert batch.coverage == 1.0
    assert fake.collections[0][0] == IMERG_V07_COLLECTION


def test_imerg_v07_adapter_rejects_wrong_source_id():
    start = datetime(2024, 1, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="unsupported IMERG"):
        ImergV07Adapter(gee=FakeGeeClient()).fetch(
            **_fetch_kwargs(start, start + timedelta(minutes=30), source_id="imerg-v06")
        )


# ---------------------------------------------------------------------------
# Coverage, discrepancies, checksum semantics
# ---------------------------------------------------------------------------


def test_missing_grid_slots_reduce_completeness_and_record_discrepancies():
    start = datetime(2024, 1, 1, tzinfo=UTC)
    fake = FakeGeeClient(series=[(datetime(2024, 1, 1, tzinfo=UTC), 2.5)])
    batch = ChirpsV3Adapter(gee=fake).fetch(
        **_fetch_kwargs(start, datetime(2024, 1, 4, tzinfo=UTC))
    )

    assert len(batch.intervals) == 1
    assert batch.completeness == pytest.approx(1 / 3)
    assert batch.coverage == pytest.approx(1 / 3)
    assert "expected_interval=2024-01-02T00:00:00+00:00" in batch.discrepancies
    assert "expected_interval=2024-01-03T00:00:00+00:00" in batch.discrepancies


def test_checksum_is_deterministic_and_content_sensitive():
    start = datetime(2024, 1, 1, tzinfo=UTC)
    rows = [(datetime(2024, 1, 1, tzinfo=UTC), 1.0)]
    first = ChirpsV3Adapter(gee=FakeGeeClient(series=rows)).fetch(
        **_fetch_kwargs(start, datetime(2024, 1, 2, tzinfo=UTC))
    )
    second = ChirpsV3Adapter(gee=FakeGeeClient(series=rows)).fetch(
        **_fetch_kwargs(start, datetime(2024, 1, 2, tzinfo=UTC))
    )
    assert first.checksum == second.checksum

    different = ChirpsV3Adapter(
        gee=FakeGeeClient(series=[(datetime(2024, 1, 1, tzinfo=UTC), 9.9)])
    ).fetch(**{**_fetch_kwargs(start, datetime(2024, 1, 2, tzinfo=UTC))})
    assert different.checksum != first.checksum


def test_zonal_batch_refuses_duplicate_values_for_the_same_slot():
    start = datetime(2024, 1, 1, tzinfo=UTC)
    rows = [
        (datetime(2024, 1, 1, tzinfo=UTC), 1.0),
        (datetime(2024, 1, 1, 12, 0, tzinfo=UTC), 2.0),  # snaps to the same daily slot
    ]
    with pytest.raises(ValueError, match="refusing to blend"):
        build_zonal_batch(
            source_id="chirps-v3-final",
            scope_kind="zone",
            scope_id="z1",
            scope_version="v1",
            cadence=timedelta(days=1),
            provider_revision="v3-final",
            unit="mm",
            catalog_id=CHIRPS_V3_RNN_COLLECTION,
            band="precipitation",
            scale_m=1000,
            start=start,
            end=datetime(2024, 1, 3, tzinfo=UTC),
            series=rows,
        )


# ---------------------------------------------------------------------------
# Manifest contract (provider revisions, roles, evidence-gate status)
# ---------------------------------------------------------------------------


def test_manifest_records_wired_provider_profiles_and_keeps_candidates_disabled():
    from app.domains.geo.rainfall.adapters.manifests import CANDIDATE_MANIFESTS

    by_id = {manifest.source_id: manifest for manifest in CANDIDATE_MANIFESTS}
    ch_final = by_id["chirps-v3-final"]
    ch_sat = by_id["chirps-v3-sat"]
    imerg = by_id["imerg-v07"]

    # CHIRPS v3 final keeps the historical contract; SAT is the daily fallback.
    assert ch_final.role == "historical"
    assert ch_final.cadence_minutes == 1440
    assert ch_final.provider_revision == "v3-final"
    assert ch_sat.role == "daily"
    assert ch_sat.cadence_minutes == 1440
    assert ch_sat.provider_revision == "v3-nrt"
    assert imerg.role == "intensity"
    assert imerg.cadence_minutes == 30
    assert imerg.provider_revision == "v07"

    # Evidence-gating stays intact: manifests stay disabled until a deployment
    # validates + enables them; the feature-flag gate still controls contact.
    assert all(manifest.enabled is False for manifest in (ch_final, ch_sat, imerg))
    assert ch_final.checksum == ch_sat.checksum == imerg.checksum == "pending-spike"


def test_manifest_revisions_match_adapter_provider_revisions():
    from app.domains.geo.rainfall.adapters.manifests import CANDIDATE_MANIFESTS

    by_id = {manifest.source_id: manifest for manifest in CANDIDATE_MANIFESTS}
    start = datetime(2024, 1, 1, tzinfo=UTC)
    rows = [(start, 1.0)]

    chirps_batch = ChirpsV3Adapter(gee=FakeGeeClient(series=rows)).fetch(
        **_fetch_kwargs(start, datetime(2024, 1, 2, tzinfo=UTC))
    )
    assert chirps_batch.intervals[0].provider_revision == by_id["chirps-v3-final"].provider_revision

    sat_batch = ChirpsV3Adapter(gee=FakeGeeClient(series=rows)).fetch(
        **_fetch_kwargs(start, datetime(2024, 1, 2, tzinfo=UTC), source_id="chirps-v3-sat")
    )
    assert sat_batch.intervals[0].provider_revision == by_id["chirps-v3-sat"].provider_revision

    imerg_batch = ImergV07Adapter(gee=FakeGeeClient(series=rows)).fetch(
        **_fetch_kwargs(start, start + timedelta(minutes=30), source_id="imerg-v07")
    )
    assert imerg_batch.intervals[0].provider_revision == by_id["imerg-v07"].provider_revision


# ---------------------------------------------------------------------------
# Resilience interaction and provider error propagation
# ---------------------------------------------------------------------------


def test_resilient_adapter_retries_then_opens_circuit_on_provider_failure(monkeypatch):
    from app.domains.geo.rainfall.adapters.resilience import (
        AdapterError,
        CircuitOpen,
        MemoryCircuitStore,
        ResilientAdapter,
    )

    monkeypatch.setattr(
        "app.domains.geo.rainfall.adapters.resilience.time.sleep", lambda _seconds: None
    )
    store = MemoryCircuitStore()
    faulty = ChirpsV3Adapter(gee=FakeGeeClient(error=TimeoutError("gee down")))

    resilient = ResilientAdapter(
        faulty.fetch,
        store=store,
        timeout_seconds=5,
        max_retries=1,
        failure_threshold=2,
        recovery_seconds=3600,
    )
    start = datetime(2024, 1, 1, tzinfo=UTC)
    kwargs = {
        "source_id": "chirps-v3-final",
        "role": "historical",
        "scope_kind": "zone",
        "scope_id": "z1",
        "scope_version": "v1",
        "start": start,
        "end": datetime(2024, 1, 2, tzinfo=UTC),
    }

    with pytest.raises(AdapterError, match="gee down"):
        resilient.fetch(**kwargs)
    assert resilient.state.consecutive_failures == 2  # initial attempt + retry

    with pytest.raises(CircuitOpen):
        resilient.fetch(**kwargs)


def test_provider_success_after_failure_resets_the_circuit(monkeypatch):
    from app.domains.geo.rainfall.adapters.resilience import (
        AdapterError,
        MemoryCircuitStore,
        ResilientAdapter,
    )

    monkeypatch.setattr(
        "app.domains.geo.rainfall.adapters.resilience.time.sleep", lambda _seconds: None
    )
    store = MemoryCircuitStore()
    start = datetime(2024, 1, 1, tzinfo=UTC)
    kwargs = {
        "source_id": "chirps-v3-final",
        "role": "historical",
        "scope_kind": "zone",
        "scope_id": "z1",
        "scope_version": "v1",
        "start": start,
        "end": datetime(2024, 1, 2, tzinfo=UTC),
    }

    failing = ChirpsV3Adapter(gee=FakeGeeClient(error=TimeoutError("down")))
    first = ResilientAdapter(
        failing.fetch,
        store=store,
        timeout_seconds=5,
        max_retries=0,
        failure_threshold=1,
        recovery_seconds=0,
    )
    with pytest.raises(AdapterError):
        first.fetch(**kwargs)

    healthy = ChirpsV3Adapter(gee=FakeGeeClient(series=[(datetime(2024, 1, 1, tzinfo=UTC), 1.0)]))
    second = ResilientAdapter(
        healthy.fetch,
        store=store,
        timeout_seconds=5,
        max_retries=0,
        failure_threshold=1,
        recovery_seconds=0,
    )
    batch = second.fetch(**kwargs)
    assert len(batch.intervals) == 1
    assert second.state.consecutive_failures == 0


# ---------------------------------------------------------------------------
# SQPE-OBS and unmapped candidates
# ---------------------------------------------------------------------------


def test_sqpe_obs_raises_the_documented_not_implemented_error(monkeypatch):
    from app.domains.geo.rainfall import tasks

    with pytest.raises(NotImplementedError) as excinfo:
        tasks._concrete_fetch("sqpe-obs")
    message = str(excinfo.value)
    assert "sqpe-obs provider not available in GEE (SMN NetCDF)" in message
    assert "spec permits CHIRPS v3 daily fallback" in message

    # With the role manually enabled, the full ingest path surfaces the same
    # provider decision raw (never wrapped as a retryable adapter error).
    monkeypatch.setattr(tasks, "_role_enabled", lambda role, db=None: True)
    with pytest.raises(NotImplementedError, match="SMN NetCDF"):
        tasks.ingest_source_scope(
            source_id="sqpe-obs",
            role="daily",
            scope_kind="zone",
            scope_id="z1",
            scope_version="v1",
            year=2025,
        )


def test_unwired_candidate_still_raises_evidence_gated_not_implemented():
    from app.domains.geo.rainfall import tasks

    with pytest.raises(NotImplementedError, match="evidence-gated"):
        tasks._concrete_fetch("sinarame-rqpe")


# ---------------------------------------------------------------------------
# Scope → asset resolution
# ---------------------------------------------------------------------------


def test_scope_asset_resolution_maps_zone_default_and_known_basins():
    assert asset_name_for("zone", "any-zone-id") == "zona_cc_ampliada"
    assert asset_name_for("basin", "candil") == "candil"
    assert asset_name_for("basin", "ml") == "ml"
    assert asset_name_for("basin", "noroeste") == "noroeste"
    assert asset_name_for("basin", "norte") == "norte"


def test_unmapped_basin_scope_raises_unknown_provider_scope():
    with pytest.raises(UnknownProviderScope, match="no GEE asset mapped"):
        asset_name_for("basin", "basin-42")
    with pytest.raises(UnknownProviderScope, match="unsupported provider scope kind"):
        asset_name_for("parcel", "p1")
