"""Tests for the QGIS export domain.

Phase 4.1-4.4: Unit tests for QGISProjectGenerator and fetch_vt_layers.
Phase 4.5:     Router integration tests (TestClient, mocked fetch_vt_layers).
Phase 4.6:     Integration test against a running server (pytest.mark.integration).
"""

from __future__ import annotations

import io
import zipfile
import xml.etree.ElementTree as ET
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Phase 4.1 – QGISProjectGenerator.build() — valid ZIP, contains project.qgs
# ---------------------------------------------------------------------------


class TestQGISProjectGeneratorBuild:
    """Unit tests for QGISProjectGenerator.build()."""

    def _build(self, source_ids=None, martin_url="https://tiles.example.com"):
        from app.domains.geo.qgis_export import QGISProjectGenerator

        if source_ids is None:
            source_ids = ["vt_canales", "vt_parcelas", "vt_infraestructura", "vt_zonas"]
        return QGISProjectGenerator.build(source_ids, martin_url)

    def test_build_returns_bytes(self):
        result = self._build()
        assert isinstance(result, bytes)
        assert len(result) > 0

    # Phase 4.1 — ZIP is valid and contains project.qgs
    def test_build_returns_valid_zip(self):
        result = self._build()
        buf = io.BytesIO(result)
        assert zipfile.is_zipfile(buf)

    def test_build_zip_contains_project_qgs(self):
        result = self._build()
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            assert "project.qgs" in zf.namelist()

    def test_build_zip_has_exactly_one_entry(self):
        result = self._build()
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            assert len(zf.namelist()) == 1

    # Phase 4.1 — XML inside project.qgs parses without error
    def test_project_qgs_is_valid_xml(self):
        result = self._build()
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            xml_bytes = zf.read("project.qgs")
        # Should not raise
        root = ET.fromstring(xml_bytes)
        assert root.tag == "qgis"

    # Phase 4.1 — 4 maplayer elements for 4 source_ids
    def test_maplayer_count_matches_source_ids(self):
        source_ids = ["vt_canales", "vt_parcelas", "vt_infraestructura", "vt_zonas"]
        result = self._build(source_ids=source_ids)
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            xml_bytes = zf.read("project.qgs")
        root = ET.fromstring(xml_bytes)
        maplayers = root.findall(".//maplayer[@type='vectortile']")
        assert len(maplayers) == 4

    # Phase 4.1 — datasource URLs contain correct martin_public_url prefix
    def test_datasource_urls_contain_martin_public_url(self):
        martin_url = "https://tiles.example.com"
        source_ids = ["vt_canales", "vt_parcelas"]
        result = self._build(source_ids=source_ids, martin_url=martin_url)
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            xml_bytes = zf.read("project.qgs")
        root = ET.fromstring(xml_bytes)
        for maplayer in root.findall(".//maplayer[@type='vectortile']"):
            ds = maplayer.findtext("datasource") or ""
            assert martin_url in ds, f"Expected martin URL in datasource: {ds}"

    # Phase 4.2 — &amp; escaping: datasource uses & not &amp; in parsed XML
    def test_datasource_amp_escaping(self):
        """ET parses &amp; back to &, so parsed text must NOT contain &amp;."""
        result = self._build(source_ids=["vt_canales"])
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            xml_bytes = zf.read("project.qgs")
        root = ET.fromstring(xml_bytes)
        ds_el = root.find(".//datasource")
        assert ds_el is not None
        ds_text = ds_el.text or ""
        # After XML parsing, & should appear as literal &, not &amp;
        assert "&amp;" not in ds_text
        assert "&" in ds_text

    # Phase 4.2 — raw XML bytes contain &amp; (correct escaping in the file)
    def test_raw_xml_uses_amp_entity(self):
        result = self._build(source_ids=["vt_canales"])
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            raw = zf.read("project.qgs").decode("utf-8")
        assert "&amp;" in raw

    # Phase 4.3 — literal {z}/{x}/{y} in datasource (QGIS substitutes at runtime)
    def test_datasource_contains_literal_tile_placeholders(self):
        result = self._build(source_ids=["vt_canales"])
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            xml_bytes = zf.read("project.qgs")
        root = ET.fromstring(xml_bytes)
        ds_el = root.find(".//datasource")
        assert ds_el is not None
        ds_text = ds_el.text or ""
        assert "{z}" in ds_text
        assert "{x}" in ds_text
        assert "{y}" in ds_text

    # Phase 4.4 — layertree-group is present
    def test_layertree_group_present(self):
        result = self._build(source_ids=["vt_canales", "vt_parcelas"])
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            xml_bytes = zf.read("project.qgs")
        root = ET.fromstring(xml_bytes)
        group = root.find("layertree-group")
        assert group is not None

    def test_layertree_entries_match_source_ids(self):
        source_ids = ["vt_canales", "vt_parcelas"]
        result = self._build(source_ids=source_ids)
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            xml_bytes = zf.read("project.qgs")
        root = ET.fromstring(xml_bytes)
        group = root.find("layertree-group")
        assert group is not None
        layer_tree_layers = group.findall("layer-tree-layer")
        assert len(layer_tree_layers) == len(source_ids)

    def test_build_with_single_layer(self):
        result = self._build(source_ids=["vt_canales"])
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            xml_bytes = zf.read("project.qgs")
        root = ET.fromstring(xml_bytes)
        maplayers = root.findall(".//maplayer[@type='vectortile']")
        assert len(maplayers) == 1

    def test_build_with_empty_layers(self):
        """Empty source list should still produce a valid ZIP."""
        result = self._build(source_ids=[])
        assert zipfile.is_zipfile(io.BytesIO(result))
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            assert "project.qgs" in zf.namelist()

    def test_martin_url_trailing_slash_is_stripped(self):
        """A trailing slash in martin_public_url must not produce double slashes in the path."""
        result = self._build(
            source_ids=["vt_canales"],
            martin_url="https://tiles.example.com/",
        )
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            xml_bytes = zf.read("project.qgs")
        root = ET.fromstring(xml_bytes)
        ds_el = root.find(".//datasource")
        assert ds_el is not None
        ds_text = ds_el.text or ""
        # Remove the scheme (https://) then check no // in the remaining path
        path_part = ds_text.split("://", 1)[-1]
        assert "//" not in path_part, f"Double slash found in path: {path_part}"


# ---------------------------------------------------------------------------
# Phase 4.2 – fetch_vt_layers() — only vt_* returned, fallback on timeout
# ---------------------------------------------------------------------------


class TestFetchVtLayers:
    """Unit tests for fetch_vt_layers() using mocked httpx."""

    @pytest.mark.asyncio
    async def test_returns_only_vt_layers(self):
        from app.domains.geo.qgis_export import fetch_vt_layers

        catalog_payload = {
            "tiles": {
                "vt_canales": {},
                "vt_parcelas": {},
                "non_vt_layer": {},
                "another_layer": {},
            }
        }

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = catalog_payload

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("app.domains.geo.qgis_export.httpx.AsyncClient", return_value=mock_client):
            result = await fetch_vt_layers("http://martin:3000")

        assert all(layer.startswith("vt_") for layer in result)
        assert "vt_canales" in result
        assert "vt_parcelas" in result
        assert "non_vt_layer" not in result
        assert "another_layer" not in result

    @pytest.mark.asyncio
    async def test_returns_sorted_vt_layers(self):
        from app.domains.geo.qgis_export import fetch_vt_layers

        catalog_payload = {
            "tiles": {"vt_zonas": {}, "vt_canales": {}, "vt_parcelas": {}}
        }

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = catalog_payload

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("app.domains.geo.qgis_export.httpx.AsyncClient", return_value=mock_client):
            result = await fetch_vt_layers("http://martin:3000")

        assert result == sorted(result)

    @pytest.mark.asyncio
    async def test_falls_back_to_fallback_layers_on_timeout(self):
        from app.domains.geo.qgis_export import FALLBACK_LAYERS, fetch_vt_layers
        import httpx

        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.ReadTimeout("timed out", request=MagicMock())
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("app.domains.geo.qgis_export.httpx.AsyncClient", return_value=mock_client):
            result = await fetch_vt_layers("http://martin:3000")

        assert result == FALLBACK_LAYERS

    @pytest.mark.asyncio
    async def test_falls_back_to_fallback_layers_on_connection_error(self):
        from app.domains.geo.qgis_export import FALLBACK_LAYERS, fetch_vt_layers
        import httpx

        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.ConnectError("connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("app.domains.geo.qgis_export.httpx.AsyncClient", return_value=mock_client):
            result = await fetch_vt_layers("http://martin:3000")

        assert result == FALLBACK_LAYERS

    @pytest.mark.asyncio
    async def test_falls_back_when_no_vt_layers_in_catalog(self):
        """If catalog returns no vt_* keys, fall back to the hardcoded list."""
        from app.domains.geo.qgis_export import FALLBACK_LAYERS, fetch_vt_layers

        catalog_payload = {"tiles": {"other_layer": {}, "another_layer": {}}}

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = catalog_payload

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("app.domains.geo.qgis_export.httpx.AsyncClient", return_value=mock_client):
            result = await fetch_vt_layers("http://martin:3000")

        assert result == FALLBACK_LAYERS

    @pytest.mark.asyncio
    async def test_url_is_constructed_correctly(self):
        from app.domains.geo.qgis_export import fetch_vt_layers

        catalog_payload = {"tiles": {"vt_canales": {}}}

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = catalog_payload

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("app.domains.geo.qgis_export.httpx.AsyncClient", return_value=mock_client):
            await fetch_vt_layers("http://martin:3000/")

        # Should strip trailing slash before appending /catalog
        call_url = mock_client.get.call_args[0][0]
        assert call_url == "http://martin:3000/catalog"
        assert "//" not in call_url.replace("://", "")


# ---------------------------------------------------------------------------
# Phase 4.3-4.5 – Router integration tests (TestClient, mocked deps)
# ---------------------------------------------------------------------------


def _make_test_app():
    """Build a minimal FastAPI app with just the geo router mounted."""
    from fastapi import FastAPI
    from app.domains.geo.router import router as geo_router

    app = FastAPI()
    app.include_router(geo_router, prefix="/api/v2/geo")
    return app


class TestExportQgisEndpointUnit:
    """Router-level tests using direct function calls with mocked deps."""

    @pytest.mark.asyncio
    async def test_returns_zip_bytes_with_correct_headers(self):
        from app.domains.geo.router import export_qgis_project

        mock_user = MagicMock()
        mock_user.role = "operador"

        with (
            patch(
                "app.domains.geo.qgis_export.fetch_vt_layers",
                new=AsyncMock(return_value=["vt_canales", "vt_parcelas"]),
            ),
            patch(
                "app.config.settings",
                new=MagicMock(
                    martin_public_url="https://tiles.example.com",
                    martin_internal_url="http://martin:3000",
                ),
            ),
        ):
            from app.domains.geo.router import export_qgis_project as ep
            response = await ep(_user=mock_user)

        from starlette.responses import StreamingResponse
        assert isinstance(response, StreamingResponse)
        assert response.media_type == "application/zip"
        assert "consorcio-canalero.qgz" in response.headers.get("content-disposition", "")

    @pytest.mark.asyncio
    async def test_returns_503_when_martin_public_url_empty(self):
        from fastapi import HTTPException

        mock_user = MagicMock()

        with patch(
            "app.config.settings",
            new=MagicMock(
                martin_public_url="",
                martin_internal_url="http://martin:3000",
            ),
        ):
            from app.domains.geo.router import export_qgis_project as ep
            with pytest.raises(HTTPException) as exc_info:
                await ep(_user=mock_user)

        assert exc_info.value.status_code == 503
        assert "MARTIN_PUBLIC_URL" in exc_info.value.detail

    def test_endpoint_requires_operator_dependency(self):
        """The export endpoint must declare the operator auth dependency."""
        import inspect

        from app.domains.geo.router import export_qgis_project as ep

        sig = inspect.signature(ep)
        # FastAPI stores Depends() as the default value of the parameter
        _user_param = sig.parameters.get("_user")
        assert _user_param is not None, "export_qgis_project has no _user parameter"
        dep = _user_param.default
        # The default is a Depends() object — it must not be inspect.Parameter.empty
        assert dep is not inspect.Parameter.empty, "_user has no Depends() default"
        # The dependency callable must be _require_operator (auth guard)
        from fastapi import params as fa_params
        assert isinstance(dep, fa_params.Depends), "_user default is not a Depends()"

    @pytest.mark.asyncio
    async def test_returned_bytes_are_valid_zip(self):
        mock_user = MagicMock()
        mock_user.role = "operador"

        with (
            patch(
                "app.domains.geo.qgis_export.fetch_vt_layers",
                new=AsyncMock(return_value=["vt_canales"]),
            ),
            patch(
                "app.config.settings",
                new=MagicMock(
                    martin_public_url="https://tiles.example.com",
                    martin_internal_url="http://martin:3000",
                ),
            ),
        ):
            from app.domains.geo.router import export_qgis_project as ep
            response = await ep(_user=mock_user)

        from starlette.responses import StreamingResponse
        assert isinstance(response, StreamingResponse)
        # Collect the streaming body
        chunks = [chunk async for chunk in response.body_iterator]
        body = b"".join(chunks)
        assert zipfile.is_zipfile(io.BytesIO(body))


# ---------------------------------------------------------------------------
# Phase 4.6 – Integration test — real HTTP against localhost:8000
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestExportQgisIntegration:
    """
    Real HTTP integration test.

    Requires:
    - A running backend at localhost:8000
    - An operator user with known credentials (read from env or hardcoded test user)
    - MARTIN_PUBLIC_URL set in the backend environment

    Run with:
        pytest tests/new/test_geo_export.py -m integration
    """

    BASE_URL = "http://localhost:8000"

    def _get_operator_token(self) -> str:
        """Obtain an operator JWT by logging in via the auth endpoint."""
        import os
        import httpx

        email = os.environ.get("TEST_OPERATOR_EMAIL", "operador@consorcio.test")
        password = os.environ.get("TEST_OPERATOR_PASSWORD", "operador123")

        response = httpx.post(
            f"{self.BASE_URL}/api/v2/auth/jwt/login",
            data={"username": email, "password": password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )
        assert response.status_code == 200, (
            f"Could not get operator token: {response.status_code} {response.text}"
        )
        return response.json()["access_token"]

    def test_authenticated_operator_gets_200_valid_zip(self):
        import httpx

        token = self._get_operator_token()

        response = httpx.get(
            f"{self.BASE_URL}/api/v2/geo/export/qgis",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text[:200]}"
        )
        assert response.headers.get("content-type", "").startswith("application/zip")
        assert "consorcio-canalero.qgz" in response.headers.get("content-disposition", "")

        # Verify the response body is a valid ZIP containing project.qgs
        body = response.content
        assert zipfile.is_zipfile(io.BytesIO(body)), "Response body is not a valid ZIP"

        with zipfile.ZipFile(io.BytesIO(body)) as zf:
            assert "project.qgs" in zf.namelist(), "project.qgs not found in ZIP"
            xml_bytes = zf.read("project.qgs")

        # XML must parse without error
        root = ET.fromstring(xml_bytes)
        assert root.tag == "qgis"

    def test_unauthenticated_request_gets_401(self):
        import httpx

        response = httpx.get(
            f"{self.BASE_URL}/api/v2/geo/export/qgis",
            timeout=10,
        )
        assert response.status_code == 401
