"""Annual Sentinel-2 composites and JRC Global Surface Water tiles.

The date math is pure. Earth Engine objects are passed in so tests can
exercise the image chain without a live session.
"""

from __future__ import annotations

from datetime import date, timedelta

S2_YEAR_MIN = 2017
ANNUAL_BUFFER_DAYS = 182
ANNUAL_MAX_CLOUD = 60
ANNUAL_CENTER = (7, 2)

JRC_YEAR_MIN = 1984
JRC_YEAR_MAX = 2021
JRC_OCCURRENCE_ASSET = "JRC/GSW1_4/GlobalSurfaceWater"
JRC_YEARLY_ASSET = "JRC/GSW1_4/YearlyHistory"

OCCURRENCE_VIS = {
    "bands": ["occurrence"],
    "min": 0,
    "max": 100,
    "palette": ["ffffff", "99d9ea", "003366"],
}
YEARLY_VIS = {
    "bands": ["waterClass"],
    "min": 0,
    "max": 3,
    "palette": ["cccccc", "e5e7eb", "60a5fa", "1e3a8a"],
}


class TimeLayerError(ValueError):
    """A year or product the time slider cannot ask Earth Engine for."""


def annual_composite_request(year: int, today: date) -> tuple[date, int, int]:
    """Center an approximate calendar year on 2 July with a 182-day buffer.

    ``build_sentinel2_payload`` searches ``target ± buffer`` and adds one day
    to the end because Earth Engine's ``filterDate`` is end-exclusive.
    In a non-leap year that window is 1 Jan through 1 Jan of the next year.
    In a leap year it starts on 2 Jan: the composite is the calendar year
    shifted by one day, not a hydrological year.
    """
    if year < S2_YEAR_MIN or year > today.year:
        raise TimeLayerError(
            f"El año {year} está fuera de Sentinel-2 ({S2_YEAR_MIN}–{today.year})."
        )
    month, day = ANNUAL_CENTER
    return date(year, month, day), ANNUAL_BUFFER_DAYS, ANNUAL_MAX_CLOUD


MONTHLY_BUFFER_DAYS = 14
MONTHLY_MAX_CLOUD = 40


def monthly_composite_request(year: int, month: int, today: date) -> tuple[date, int, int]:
    """Center a calendar month on the 15th with a 14-day buffer.

    The search window is the month, plus a day on each side when the month
    is shorter or longer than 29 days. A future month is rejected.
    """
    if month < 1 or month > 12:
        raise TimeLayerError(f"El mes {month} no existe.")
    if year < S2_YEAR_MIN or year > today.year:
        raise TimeLayerError(
            f"El año {year} está fuera de Sentinel-2 ({S2_YEAR_MIN}–{today.year})."
        )
    target = date(year, month, 15)
    if target > today:
        raise TimeLayerError("Ese mes todavía no tiene imágenes Sentinel-2.")
    return target, MONTHLY_BUFFER_DAYS, MONTHLY_MAX_CLOUD


def annual_search_window(target: date, buffer_days: int = ANNUAL_BUFFER_DAYS) -> tuple[date, date]:
    """Inclusive start and exclusive end used by the Sentinel-2 payload."""
    start = target - timedelta(days=buffer_days)
    end_exclusive = target + timedelta(days=buffer_days + 1)
    return start, end_exclusive


def jrc_occurrence_image(ee, geometry):
    return ee.Image(JRC_OCCURRENCE_ASSET).select("occurrence").clip(geometry)


def jrc_yearly_image(ee, year: int, geometry):
    if year < JRC_YEAR_MIN or year > JRC_YEAR_MAX:
        raise TimeLayerError(
            f"El año {year} está fuera del histórico JRC ({JRC_YEAR_MIN}–{JRC_YEAR_MAX})."
        )
    return (
        ee.ImageCollection(JRC_YEARLY_ASSET)
        .filterDate(f"{year}-01-01", f"{year + 1}-01-01")
        .select("waterClass")
        .mosaic()
        .clip(geometry)
    )


def jrc_tile_payload(ee, geometry, *, kind: str, year: int | None = None) -> dict:
    if kind == "occurrence":
        image = jrc_occurrence_image(ee, geometry)
        vis = OCCURRENCE_VIS
        target_date = f"{JRC_YEAR_MAX}-01-01"
        description = "Recurrencia histórica de agua superficial (JRC)"
        visualization = "occurrence"
        collection = JRC_OCCURRENCE_ASSET
    elif kind == "year":
        if year is None:
            raise TimeLayerError("Falta el año del histórico JRC.")
        image = jrc_yearly_image(ee, year, geometry)
        vis = YEARLY_VIS
        target_date = f"{year}-01-01"
        description = f"Agua superficial JRC {year}"
        visualization = "waterClass"
        collection = JRC_YEARLY_ASSET
    else:
        raise TimeLayerError(f"Producto JRC desconocido: {kind}.")

    map_id = image.getMapId(vis)
    return {
        "tile_url": map_id["tile_fetcher"].url_format,
        "target_date": target_date,
        "sensor": "JRC",
        "visualization": visualization,
        "visualization_description": description,
        "collection": collection,
        "images_count": 1,
        "days_buffer": 1,
        "max_cloud": None,
        "mode": "composite",
    }
