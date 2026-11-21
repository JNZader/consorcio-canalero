"""Minimal environment defaults for hermetic unit tests."""

import os

os.environ.setdefault("UPLOADS_ROOT", "/tmp/consorcio-unit-uploads")
