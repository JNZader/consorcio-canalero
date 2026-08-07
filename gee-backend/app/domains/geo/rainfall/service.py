"""Snapshot serialization keeps JSON and CSV state/provenance semantics identical."""

import csv
import json
from io import StringIO
from typing import Any


def metric_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten nested metric groups without coercing a missing value to zero."""
    return [
        dict(metric)
        for group in snapshot.values()
        if isinstance(group, dict)
        for metric in group.values()
        if isinstance(metric, dict) and "metric" in metric
    ]


def metric_rows_csv(rows: list[dict[str, Any]]) -> str:
    """Serialize every displayed field; null stays blank and nested evidence stays JSON."""
    fields = tuple(sorted({key for row in rows for key in row}))
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                key: json.dumps(value, sort_keys=True)
                if isinstance(value, (dict, list, tuple))
                else value
                for key, value in row.items()
            }
        )
    return output.getvalue()
