"""Recording test double for the Earth Engine module (``ee``).

Every imagery helper under ``app.domains.geo.gee_service_imagery_support``
receives ``ee`` **injected** as ``ee_module`` (or operates on objects handed to
it), so the whole module is testable without credentials, network or a real
Earth Engine session.

``FakeEE`` mimics the fluent Earth Engine API: any attribute access produces a
chainable node, any call is recorded in a shared log, and the result is a node
that can be chained further. Tests then assert on the *sequence of operations*
the production code asked for (``select('QA_PIXEL')`` → ``bitwiseAnd(2)`` →
``updateMask``), which is exactly the contract that regressions broke.

Terminal calls that must return real Python values (``getInfo``, ``getMapId``,
``size``) are configured through ``overrides``: a mapping from a *dotted call
path suffix* to the value to return. The longest matching suffix wins, so
``"size.getInfo"`` and ``"reduceRegion.getInfo"`` can return different values
inside the same test. An override whose value is an exception instance is
raised instead of returned (used to prove the fallback paths).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List

_UNSET = object()


@dataclass(frozen=True)
class EECall:
    """A single recorded call on the fake Earth Engine API."""

    path: str
    args: tuple
    kwargs: dict

    def __str__(self) -> str:  # pragma: no cover — debugging aid only
        return f"{self.path}(args={self.args!r}, kwargs={self.kwargs!r})"


class EENode:
    """Chainable, self-recording stand-in for any ``ee`` object."""

    def __init__(self, path: List[str], log: List[EECall], overrides: Dict[str, Any]):
        self._path = path
        self._log = log
        self._overrides = overrides

    # -- chaining ---------------------------------------------------------
    def __getattr__(self, name: str) -> "EENode":
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        return EENode([*self._path, name], self._log, self._overrides)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        dotted = ".".join(self._path)
        self._log.append(EECall(dotted, args, kwargs))

        # ``collection.map(fn)`` must actually run ``fn`` so the operations it
        # performs on each image get recorded too — that is where the cloud and
        # haze masks live.
        if self._path and self._path[-1] == "map" and len(args) == 1 and callable(args[0]):
            mapped = args[0](EENode([*self._path, "element"], self._log, self._overrides))
            return mapped

        override = self._resolve(dotted)
        if override is not _UNSET:
            if isinstance(override, BaseException):
                raise override
            if callable(override):
                return override(*args, **kwargs)
            return override
        return EENode(list(self._path), self._log, self._overrides)

    def _resolve(self, dotted: str) -> Any:
        parts = dotted.split(".")
        for start in range(len(parts)):
            key = ".".join(parts[start:])
            if key in self._overrides:
                return self._overrides[key]
        return _UNSET

    def __repr__(self) -> str:  # pragma: no cover — debugging aid only
        return f"<EENode {'.'.join(self._path)}>"


class FakeEE(EENode):
    """Root node: use it wherever production code expects the ``ee`` module."""

    def __init__(self, overrides: Dict[str, Any] | None = None):
        super().__init__([], [], dict(overrides or {}))

    @property
    def calls(self) -> List[EECall]:
        return self._log

    @property
    def paths(self) -> List[str]:
        return [call.path for call in self._log]

    def calls_to(self, suffix: str) -> List[EECall]:
        """Every recorded call whose dotted path ends with ``suffix``."""
        return [call for call in self._log if _ends_with(call.path, suffix)]

    def one_call_to(self, suffix: str) -> EECall:
        matches = self.calls_to(suffix)
        assert len(matches) == 1, f"expected exactly one {suffix!r} call, got {matches}"
        return matches[0]

    def called(self, suffix: str) -> bool:
        return bool(self.calls_to(suffix))

    def reset(self) -> None:
        self._log.clear()


def _ends_with(path: str, suffix: str) -> bool:
    parts = path.split(".")
    wanted = suffix.split(".")
    return len(wanted) <= len(parts) and parts[-len(wanted) :] == wanted


class TileFetcher:
    def __init__(self, url_format: str):
        self.url_format = url_format


def map_id(url: str = "https://earthengine.example/tiles/{z}/{x}/{y}") -> Dict[str, Any]:
    """Value for a ``getMapId`` override."""
    return {"tile_fetcher": TileFetcher(url)}


def percentile_stats(bands: List[str], low: float, high: float) -> Dict[str, float]:
    """``reduceRegion().getInfo()`` payload for a 2–98 percentile stretch."""
    stats: Dict[str, float] = {}
    for index, band in enumerate(bands):
        stats[f"{band}_p2"] = low + index
        stats[f"{band}_p98"] = high + index
    return stats


class FakeExplorer:
    """Duck-typed stand-in for ``ImageExplorer`` as seen by the builders.

    The builders only ever touch ``zona``, ``VIS_PRESETS`` and the private
    collection helpers, so recording those calls is enough to assert the date
    window and the collection routing.
    """

    def __init__(
        self,
        ee_module: FakeEE,
        *,
        dates: List[str] | None = None,
        vis_presets: Dict[str, Dict[str, Any]] | None = None,
        cloudscore: Callable[[Any], Any] | None = None,
    ):
        self._ee = ee_module
        self.zona = ee_module.FeatureCollection("projects/test/zona")
        self.dates = dates if dates is not None else []
        self.landsat_calls: List[dict] = []
        self.sentinel2_calls: List[dict] = []
        self.sentinel1_calls: List[dict] = []
        self.cloudscore_calls = 0
        self._cloudscore = cloudscore
        if vis_presets is not None:
            self.VIS_PRESETS = vis_presets
        else:
            from app.domains.geo.gee_service_imagery_support import VIS_PRESETS

            self.VIS_PRESETS = VIS_PRESETS

    def _collection_dates(self, collection) -> List[str]:
        return list(self.dates)

    def _landsat_collection(self, sensor, start_date, end_date, max_cloud):
        self.landsat_calls.append(
            {
                "sensor": sensor,
                "start_date": start_date,
                "end_date": end_date,
                "max_cloud": max_cloud,
            }
        )
        return self._ee.ImageCollection(f"landsat:{sensor}")

    def _sentinel2_collection(self, start_date, end_date, max_cloud, *, use_toa):
        self.sentinel2_calls.append(
            {
                "start_date": start_date,
                "end_date": end_date,
                "max_cloud": max_cloud,
                "use_toa": use_toa,
            }
        )
        name = "COPERNICUS/S2_HARMONIZED" if use_toa else "COPERNICUS/S2_SR_HARMONIZED"
        return name, self._ee.ImageCollection(name)

    def _sentinel1_collection(self, start_date, end_date):
        self.sentinel1_calls.append({"start_date": start_date, "end_date": end_date})
        return self._ee.ImageCollection("COPERNICUS/S1_GRD")

    def _mask_s2_cloudscore(self, collection):
        self.cloudscore_calls += 1
        if self._cloudscore is not None:
            return self._cloudscore(collection)
        return collection.linkCollection("cloudscore")
