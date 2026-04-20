"""ETL — Pilar Verde (BPA + Plan Provincial Agroforestal).

Fetches IDECor WFS layers, converts the ZONA CC AMPLIADA KML, clips / joins /
aggregates everything and produces 9 static assets consumed by the frontend.

Run entry point: ``python scripts/etl_pilar_verde.py`` (which imports and calls
``scripts.etl_pilar_verde.main.main``).
"""

from scripts.etl_pilar_verde import constants

__all__ = ["constants"]
