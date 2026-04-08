"""
Conftest for unit tests — no database required.

These tests exercise pure logic (numpy, encoding, size estimation)
without needing PostGIS or any other external service.
"""

import sys
import pytest
from unittest.mock import MagicMock as _MagicMock

_MISSING = object()

# GEE modules that carry module-level state (e.g. import ee, _gee_initialized)
# and must be re-imported fresh whenever a test injects a mock ee.
#
# NOTE: gee_tasks is intentionally NOT in this list.  Its task functions are
# registered in Celery's task registry at first import; Celery returns a
# celery.local.Proxy whose _get_current_object() always resolves to THAT
# original task.  If we pop gee_tasks from sys.modules between tests, @patch
# ends up patching a freshly-imported module dict that is different from the
# one the task's run.__globals__ points to — so the mocks are never seen.
# gee_tasks has no module-level GEE state (_gee_initialized lives in
# gee_service), so it is safe to leave it in sys.modules across tests.
_GEE_STATEFUL_MODULES = [
    "app.domains.geo.gee_service",
    "app.domains.geo.water_detection",
]


@pytest.fixture(autouse=True)
def _isolate_gee_modules():
    """Remove cached GEE modules before each test so that fresh imports
    pick up whatever sys.modules['ee'] is at that point.

    Also resets any class-level attributes set on MagicMock by
    _mock_set_magics (Python 3.14+), which can override the
    NonCallableMock.return_value property and corrupt subsequent tests.
    """
    # Snapshot MagicMock class-level 'return_value' before the test.
    # In Python 3.14, some test setups cause MagicMock.return_value to be
    # set as a class-level MagicMock instance (a data descriptor), which
    # shadows the NonCallableMock.return_value property for ALL instances.
    rv_before = _MagicMock.__dict__.get("return_value", _MISSING)

    # Snapshot the modules that are currently loaded
    snapshot = {
        mod: sys.modules.pop(mod, None)
        for mod in _GEE_STATEFUL_MODULES
    }
    yield
    # After the test: restore the original modules (or remove if they weren't
    # present before — the next test that needs them will re-import cleanly).
    for mod, original in snapshot.items():
        if original is not None:
            sys.modules[mod] = original
        else:
            sys.modules.pop(mod, None)

    # Restore MagicMock class-level state.
    # If 'return_value' was set at class level DURING the test, undo it so
    # the property defined on NonCallableMock takes effect again.
    rv_after = _MagicMock.__dict__.get("return_value", _MISSING)
    if rv_before is _MISSING and rv_after is not _MISSING:
        delattr(_MagicMock, "return_value")
    elif rv_before is not _MISSING and rv_after is not rv_before:
        setattr(_MagicMock, "return_value", rv_before)
