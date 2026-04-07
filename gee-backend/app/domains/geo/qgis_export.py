"""QGIS project export utility.

Generates a minimal `.qgz` file (ZIP containing `project.qgs` XML) using
Python stdlib only — no QGIS installation required.

The `.qgz` is pre-configured with Martin vector tile layers so technicians
can open the live PostGIS data directly in QGIS without manual setup.

Minimum QGIS version: 3.16 LTS (VectorTileLayer became GA in 3.14).
"""

import io
import zipfile
import xml.etree.ElementTree as ET
from uuid import uuid4

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

# Fallback layer list used when Martin catalog is unreachable.
FALLBACK_LAYERS: list[str] = [
    "vt_canales",
    "vt_parcelas",
    "vt_infraestructura",
    "vt_zonas",
]

# Shared WGS 84 SRS block — identical for project CRS and each layer.
_WGS84_WKT = (
    'GEOGCS["WGS 84",DATUM["WGS_1984",'
    'SPHEROID["WGS 84",6378137,298.257223563]],'
    'PRIMEM["Greenwich",0],'
    'UNIT["degree",0.0174532925199433]]'
)


def _make_spatialrefsys() -> ET.Element:
    """Return a <spatialrefsys> element for WGS 84 (EPSG:4326)."""
    srs = ET.Element("spatialrefsys")
    ET.SubElement(srs, "wkt").text = _WGS84_WKT
    ET.SubElement(srs, "proj4").text = "+proj=longlat +datum=WGS84 +no_defs"
    ET.SubElement(srs, "srsid").text = "3452"
    ET.SubElement(srs, "srid").text = "4326"
    ET.SubElement(srs, "authid").text = "EPSG:4326"
    ET.SubElement(srs, "description").text = "WGS 84"
    ET.SubElement(srs, "projectionacronym").text = "longlat"
    ET.SubElement(srs, "ellipsoidacronym").text = "EPSG:7030"
    ET.SubElement(srs, "geographicflag").text = "true"
    return srs


async def fetch_vt_layers(martin_internal_url: str) -> list[str]:
    """Return list of vt_* source IDs from the Martin catalog.

    Fetches ``/catalog`` from *martin_internal_url*, extracts keys that start
    with ``vt_``, and returns them sorted.  Falls back to :data:`FALLBACK_LAYERS`
    on any network or parsing error so the export endpoint always succeeds.
    """
    catalog_url = f"{martin_internal_url.rstrip('/')}/catalog"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(catalog_url)
            response.raise_for_status()
            data = response.json()
        tiles: dict = data.get("tiles", {})
        vt_layers = sorted(k for k in tiles if k.startswith("vt_"))
        if vt_layers:
            return vt_layers
        logger.warning(
            "Martin catalog returned no vt_* layers — using fallback list",
            catalog_url=catalog_url,
        )
        return FALLBACK_LAYERS
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Could not reach Martin catalog — using fallback layer list",
            url=catalog_url,
            error=str(exc),
        )
        return FALLBACK_LAYERS


class QGISProjectGenerator:
    """Builds a network-connected QGIS project file (.qgz) in memory.

    The generated file references Martin vector tile layers via XYZ URLs.
    No embedded geodata — tiles are fetched live from Martin when the project
    is opened in QGIS.

    Usage::

        layers = ["vt_canales", "vt_parcelas"]
        zip_bytes = QGISProjectGenerator.build(layers, "https://tiles.example.com")
        # zip_bytes is a valid .qgz that QGIS 3.16+ can open directly.
    """

    @staticmethod
    def build(source_ids: list[str], martin_public_url: str) -> bytes:
        """Return raw bytes of a valid .qgz file.

        The .qgz is a standard ZIP archive containing a single entry named
        ``project.qgs`` (UTF-8 XML).

        Args:
            source_ids: Martin source IDs to include (e.g. ``["vt_canales"]``).
            martin_public_url: Public-facing base URL for tile requests
                (e.g. ``"https://tiles.example.com"``).  Must NOT end with a slash.

        Returns:
            Raw ZIP bytes that can be streamed directly as an HTTP response.

        Note:
            ``{z}/{x}/{y}`` appear as **literal strings** in the datasource URI —
            QGIS substitutes them at tile-fetch time.  Do not format them as
            Python variables.  ``xml.etree.ElementTree`` serialises ``&`` as
            ``&amp;`` automatically, producing the correct escaped URI.

            ``zmax=14`` is a safe default for PostGIS polygon layers; Martin
            serves up to zoom 22 but QGIS performance degrades above 14 for
            dense polygon layers.
        """
        public_base = martin_public_url.rstrip("/")
        xml_bytes = QGISProjectGenerator._build_qgs_xml(source_ids, public_base)

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("project.qgs", xml_bytes)

        return buffer.getvalue()

    @staticmethod
    def _build_qgs_xml(source_ids: list[str], public_base: str) -> bytes:
        """Return UTF-8 encoded bytes for the project.qgs XML document."""
        # Root element
        qgis = ET.Element(
            "qgis",
            attrib={
                "version": "3.28.0",
                "projectname": "Consorcio Canalero 10 de Mayo",
            },
        )

        ET.SubElement(qgis, "title").text = "Consorcio Canalero 10 de Mayo"

        # Project CRS
        project_crs = ET.SubElement(qgis, "projectCrs")
        project_crs.append(_make_spatialrefsys())

        # Map layers
        project_layers = ET.SubElement(qgis, "projectlayers")

        # Layer tree group (required for layers to appear in the QGIS panel)
        layer_tree_group = ET.Element("layertree-group")
        ET.SubElement(layer_tree_group, "custom-order", attrib={"enabled": "0"})

        for source_id in source_ids:
            layer_id = f"{source_id}_{uuid4().hex[:8]}"
            layer_name = source_id.replace("vt_", "").replace("_", " ").title()

            # <maplayer type="vectortile">
            maplayer = ET.SubElement(
                project_layers,
                "maplayer",
                attrib={
                    "type": "vectortile",
                    "autoRefreshEnabled": "0",
                    "autoRefreshTime": "0",
                    "refreshOnNotifyEnabled": "0",
                    "hasScaleBasedVisibilityFlag": "0",
                    "maxScale": "0",
                    "minScale": "1e+08",
                },
            )
            ET.SubElement(maplayer, "id").text = layer_id

            # Datasource URI — ET serialises & as &amp; automatically.
            # {z}/{x}/{y} are LITERAL placeholders that QGIS substitutes at
            # tile-fetch time.  We build the string with explicit braces so
            # Python does NOT interpolate them as format placeholders.
            datasource_uri = (
                "type=xyz"
                f"&url={public_base}/{source_id}/{{z}}/{{x}}/{{y}}"
                "&zmin=0"
                "&zmax=14"
            )
            ET.SubElement(maplayer, "datasource").text = datasource_uri
            ET.SubElement(maplayer, "layername").text = layer_name

            srs_el = ET.SubElement(maplayer, "srs")
            srs_el.append(_make_spatialrefsys())

            ET.SubElement(maplayer, "blendMode").text = "0"
            ET.SubElement(maplayer, "layerOpacity").text = "1"
            ET.SubElement(maplayer, "provider").text = "xyzvectortiles"

            # Layer tree entry
            ET.SubElement(
                layer_tree_group,
                "layer-tree-layer",
                attrib={
                    "expanded": "1",
                    "checked": "Qt::Checked",
                    "id": layer_id,
                    "name": layer_name,
                },
            )

        qgis.append(layer_tree_group)

        # Snapping utils — prevents "project settings incomplete" warning in QGIS.
        ET.SubElement(
            qgis,
            "snapping-utils",
            attrib={
                "maxScale": "0",
                "mode": "2",
                "enabled": "0",
                "tolerance": "12",
                "intersection": "0",
                "scaleDependencyMode": "0",
                "minScale": "0",
                "self-snapping": "0",
                "maxAllowed": "-1",
                "unit": "1",
            },
        ).append(ET.Element("individual-layer-settings"))

        # Serialise with XML declaration
        tree = ET.ElementTree(qgis)
        ET.indent(tree, space="  ")

        out = io.BytesIO()
        tree.write(out, encoding="utf-8", xml_declaration=True)
        return out.getvalue()
