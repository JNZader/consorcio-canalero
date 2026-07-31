"""Cardinality of the packaged ``suelos_cu.geojson``, in one place.

Both the ETL tests and the packaging tests assert against the same source file,
so the numbers live here instead of being repeated as literals: when the source
is re-cut, exactly one edit updates every test that depends on its shape.

Not a test module (leading underscore, no ``test_`` prefix): pytest does not
collect it.
"""

from __future__ import annotations

#: Features in the packaged source == rows the load must store (assertion 1).
SOURCE_FEATURE_COUNT = 45

#: Features with a NULL ``cap`` — valid source data that must survive the load
#: rather than abort it (assertion 6).
SOURCE_NULL_CAP_COUNT = 2
