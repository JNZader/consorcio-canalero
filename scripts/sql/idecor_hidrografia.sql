-- IDECOR hydro layers for Martin.
-- Run by hand against the consorcio database, then restart Martin.
-- The deploy script does not apply schema changes.
--
-- Tables stay empty until scripts/etl_idecor_capas loads a GeoJSON and
-- ogr2ogr appends it. The views publish only id, nombre and the geometry.

CREATE TABLE IF NOT EXISTS idecor_consorcios_canaleros (
    id bigserial PRIMARY KEY,
    nombre text,
    geometria geometry(Geometry, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS idecor_consorcios_canaleros_gix
    ON idecor_consorcios_canaleros USING GIST (geometria);

CREATE TABLE IF NOT EXISTS idecor_cursos_agua (
    id bigserial PRIMARY KEY,
    nombre text,
    geometria geometry(Geometry, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS idecor_cursos_agua_gix
    ON idecor_cursos_agua USING GIST (geometria);

CREATE TABLE IF NOT EXISTS idecor_cuencas (
    id bigserial PRIMARY KEY,
    nombre text,
    geometria geometry(Geometry, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS idecor_cuencas_gix
    ON idecor_cuencas USING GIST (geometria);

CREATE TABLE IF NOT EXISTS idecor_canales_riego (
    id bigserial PRIMARY KEY,
    nombre text,
    geometria geometry(Geometry, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS idecor_canales_riego_gix
    ON idecor_canales_riego USING GIST (geometria);

CREATE OR REPLACE VIEW vt_idecor_consorcios AS
SELECT id, nombre, geometria FROM idecor_consorcios_canaleros;

CREATE OR REPLACE VIEW vt_idecor_cursos AS
SELECT id, nombre, geometria FROM idecor_cursos_agua;

CREATE OR REPLACE VIEW vt_idecor_cuencas AS
SELECT id, nombre, geometria FROM idecor_cuencas;

CREATE OR REPLACE VIEW vt_idecor_canales_riego AS
SELECT id, nombre, geometria FROM idecor_canales_riego;

GRANT SELECT ON vt_idecor_consorcios, vt_idecor_cursos, vt_idecor_cuencas, vt_idecor_canales_riego
    TO PUBLIC;
