"""Unit tests for app.constants — constant values and types."""

from app.constants import (
    CONSORCIO_AREA_HA,
    CONSORCIO_KM_CAMINOS,
    CUENCA_AREAS_HA,
    CUENCA_COLORS,
    CUENCA_IDS,
    CUENCA_NOMBRES,
    DEFAULT_MAX_CLOUD,
    DEFAULT_DAYS_BACK,
    DEFAULT_PAGE_SIZE,
    MAP_BOUNDS,
    MAP_CENTER_LAT,
    MAP_CENTER_LNG,
    MAP_DEFAULT_ZOOM,
    MAX_PAGE_SIZE,
    MAX_SUGERENCIAS_POR_DIA,
    MAX_DENUNCIAS_POR_TELEFONO_DIA,
    TOTAL_CUENCAS_HA,
)


class TestConsorcioConstants:
    def test_consorcio_area_is_positive_int(self):
        assert isinstance(CONSORCIO_AREA_HA, int)
        assert CONSORCIO_AREA_HA > 0

    def test_consorcio_km_caminos_is_positive_int(self):
        assert isinstance(CONSORCIO_KM_CAMINOS, int)
        assert CONSORCIO_KM_CAMINOS > 0


class TestCuencaConstants:
    def test_cuenca_areas_has_four_entries(self):
        assert len(CUENCA_AREAS_HA) == 4

    def test_cuenca_areas_values_are_positive(self):
        for name, area in CUENCA_AREAS_HA.items():
            assert isinstance(area, int), f"{name} area should be int"
            assert area > 0, f"{name} area should be positive"

    def test_cuenca_colors_match_areas_keys(self):
        assert set(CUENCA_COLORS.keys()) == set(CUENCA_AREAS_HA.keys())

    def test_cuenca_colors_are_hex(self):
        for name, color in CUENCA_COLORS.items():
            assert color.startswith("#"), f"{name} color should be hex"
            assert len(color) == 7, f"{name} color should be #RRGGBB"

    def test_cuenca_nombres_match_areas_keys(self):
        assert set(CUENCA_NOMBRES.keys()) == set(CUENCA_AREAS_HA.keys())

    def test_cuenca_ids_matches_areas_keys(self):
        assert set(CUENCA_IDS) == set(CUENCA_AREAS_HA.keys())

    def test_total_cuencas_is_sum_of_areas(self):
        assert TOTAL_CUENCAS_HA == sum(CUENCA_AREAS_HA.values())


class TestMapConstants:
    def test_map_center_is_in_argentina(self):
        assert -56 < MAP_CENTER_LAT < -22
        assert -74 < MAP_CENTER_LNG < -53

    def test_map_default_zoom_is_reasonable(self):
        assert 1 <= MAP_DEFAULT_ZOOM <= 20

    def test_map_bounds_has_required_keys(self):
        assert set(MAP_BOUNDS.keys()) == {"north", "south", "east", "west"}


class TestPaginationConstants:
    def test_default_page_size(self):
        assert DEFAULT_PAGE_SIZE > 0

    def test_max_page_size_gte_default(self):
        assert MAX_PAGE_SIZE >= DEFAULT_PAGE_SIZE


class TestRateLimitConstants:
    def test_max_sugerencias_positive(self):
        assert MAX_SUGERENCIAS_POR_DIA > 0

    def test_max_denuncias_positive(self):
        assert MAX_DENUNCIAS_POR_TELEFONO_DIA > 0


class TestAnalysisDefaults:
    def test_max_cloud_range(self):
        assert 0 < DEFAULT_MAX_CLOUD <= 100

    def test_days_back_positive(self):
        assert DEFAULT_DAYS_BACK > 0
