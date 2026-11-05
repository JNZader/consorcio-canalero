"""PATCH bodies may omit a field. An explicit null on a NOT NULL column is 422."""

from __future__ import annotations

from pydantic import model_validator


def forbid_explicit_nulls(*field_names: str):
    """Return a model validator that rejects explicit nulls for the named fields.

    An omitted key stays optional. A key present in the JSON body with ``null``
    would otherwise reach ``setattr`` and surface as ``IntegrityError`` 500.
    """

    @model_validator(mode="after")
    def _reject_explicit_nulls(self):
        blocked = [
            name
            for name in field_names
            if name in self.model_fields_set and getattr(self, name) is None
        ]
        if blocked:
            joined = ", ".join(blocked)
            raise ValueError(f"No se puede anular: {joined}")
        return self

    return _reject_explicit_nulls
