"""keep the drawn direction of a piece that does not meet the cursor

``caminos_soldar_ruta`` walks parts from a free end. When the far end of
the next part is closer to the cursor than its start, the walk reverses
that part. The turn is right when the chosen end meets the cursor: a weld
must not walk backwards. Across a gap it is wrong. The piece stays
disconnected, and reversing it sends the elevation cursor in at the far
tip, against the direction the piece was drawn.

This revision flips a part only when the chosen endpoint is within 8 m of
the cursor. A wider gap keeps the stored direction. The gap is not filled
and the 8 m snap is not widened. The seed is unchanged: the first part
still starts at the westernmost free end.

``red_vial`` is not touched. Length and the legend do not change, because
the decision is made after the line merge.

Revision ID: 0032_keep_gap_direction
Revises: 0031_drop_covered_caminos
Create Date: 2026-10-18
"""

import importlib
from typing import Sequence, Union

from alembic import op

revision: str = "0032_keep_gap_direction"
down_revision: Union[str, None] = "0031_drop_covered_caminos"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PREVIOUS = importlib.import_module("app.db.migrations.versions.0031_drop_covered_caminos")

CREATE_FUNCTION = """
CREATE OR REPLACE FUNCTION caminos_soldar_ruta(entrada geometry)
RETURNS geometry
LANGUAGE plpgsql
IMMUTABLE
STRICT
AS $soldar$
DECLARE
    tol double precision := 8.0 / 111320.0;
    eps double precision := 1e-8;
    piezas geometry[];
    n_piezas integer;
    viva boolean[];
    otros geometry;
    cubre boolean;
    largo_i double precision;
    mejor_largo double precision;
    guard integer;
    quedan geometry[];
    i integer;
    j integer;
    n_ext integer;
    px double precision[];
    py double precision[];
    target_x double precision[];
    target_y double precision[];
    parte_de integer[];
    es_fin boolean[];
    nearest integer[];
    nearest_d double precision[];
    d double precision;
    d0 double precision;
    d1 double precision;
    ax double precision;
    ay double precision;
    sx double precision;
    sy double precision;
    ex double precision;
    ey double precision;
    elegido_x double precision;
    elegido_y double precision;
    repx double precision;
    repy double precision;
    cursorx double precision;
    cursory double precision;
    seed integer;
    seed_x double precision;
    seed_y double precision;
    seed_fin boolean;
    grado integer;
    extremo integer;
    pass_n integer;
    partes geometry[];
    usadas boolean[];
    secuencia geometry[];
    n_out integer;
    soldada geometry;
    mejor integer;
    mejor_d double precision;
    mejor_x double precision;
    mejor_y double precision;
    mejor_flip boolean;
    flip boolean;
BEGIN
    SELECT COALESCE(array_agg(ST_SetSRID(d.geom, 4326) ORDER BY d.path),
                    ARRAY[]::geometry[])
      INTO piezas
      FROM ST_Dump(ST_CollectionExtract(entrada, 2)) AS d
     WHERE NOT ST_IsEmpty(d.geom)
       AND ST_NPoints(d.geom) >= 2;

    n_piezas := COALESCE(cardinality(piezas), 0);
    IF n_piezas = 0 THEN
        RETURN NULL;
    END IF;
    IF n_piezas = 1 THEN
        RETURN ST_SetSRID(piezas[1], 4326);
    END IF;

    -- Before the snap, and against ONE other part. The union of the rest
    -- would cover a 6 m bridge sitting in two 3 m gaps and the chain would
    -- not weld. A twin a few metres off is covered by its partner. It has
    -- to go now: once the ends snap, ST_LineMerge folds the pair into one
    -- line that walks out and back, and a later drop never sees two parts.
    viva := array_fill(true, ARRAY[n_piezas]);
    guard := 0;
    WHILE guard < n_piezas LOOP
        guard := guard + 1;
        mejor := NULL;
        mejor_largo := NULL;
        FOR i IN 1..n_piezas LOOP
            IF NOT viva[i] THEN
                CONTINUE;
            END IF;
            cubre := false;
            FOR j IN 1..n_piezas LOOP
                IF j = i OR NOT viva[j] THEN
                    CONTINUE;
                END IF;
                IF ST_Covers(
                    ST_Buffer(piezas[j]::geography, 8.0),
                    piezas[i]::geography
                ) THEN
                    cubre := true;
                    EXIT;
                END IF;
            END LOOP;
            IF cubre IS NOT TRUE THEN
                CONTINUE;
            END IF;
            largo_i := ST_Length(piezas[i]::geography);
            IF mejor IS NULL
               OR largo_i < mejor_largo
               OR (largo_i = mejor_largo AND i > mejor) THEN
                mejor := i;
                mejor_largo := largo_i;
            END IF;
        END LOOP;
        EXIT WHEN mejor IS NULL;
        viva[mejor] := false;
    END LOOP;

    SELECT COALESCE(array_agg(p.geom ORDER BY p.ord), ARRAY[]::geometry[])
      INTO quedan
      FROM unnest(piezas) WITH ORDINALITY AS p(geom, ord)
     WHERE viva[p.ord::integer];
    piezas := quedan;
    n_piezas := COALESCE(cardinality(piezas), 0);
    IF n_piezas = 0 THEN
        RETURN NULL;
    END IF;
    IF n_piezas = 1 THEN
        RETURN ST_SetSRID(piezas[1], 4326);
    END IF;

    px := ARRAY[]::double precision[];
    py := ARRAY[]::double precision[];
    parte_de := ARRAY[]::integer[];
    es_fin := ARRAY[]::boolean[];
    FOR i IN 1..n_piezas LOOP
        px := array_append(px, ST_X(ST_StartPoint(piezas[i])));
        py := array_append(py, ST_Y(ST_StartPoint(piezas[i])));
        parte_de := array_append(parte_de, i);
        es_fin := array_append(es_fin, false);
        px := array_append(px, ST_X(ST_EndPoint(piezas[i])));
        py := array_append(py, ST_Y(ST_EndPoint(piezas[i])));
        parte_de := array_append(parte_de, i);
        es_fin := array_append(es_fin, true);
    END LOOP;

    n_ext := n_piezas * 2;
    nearest := array_fill(0, ARRAY[n_ext]);
    nearest_d := array_fill(1e300::double precision, ARRAY[n_ext]);
    FOR i IN 1..n_ext LOOP
        FOR j IN 1..n_ext LOOP
            IF i = j OR parte_de[i] = parte_de[j] THEN
                CONTINUE;
            END IF;
            d := sqrt((px[i] - px[j]) ^ 2 + (py[i] - py[j]) ^ 2);
            IF d <= tol AND (
                nearest[i] = 0
                OR d < nearest_d[i]
                OR (d = nearest_d[i] AND (
                    px[j] < px[nearest[i]]
                    OR (px[j] = px[nearest[i]] AND py[j] < py[nearest[i]])
                    OR (px[j] = px[nearest[i]] AND py[j] = py[nearest[i]]
                        AND j < nearest[i])
                ))
            ) THEN
                nearest[i] := j;
                nearest_d[i] := d;
            END IF;
        END LOOP;
    END LOOP;

    target_x := px;
    target_y := py;
    FOR i IN 1..n_ext LOOP
        j := nearest[i];
        IF j > 0 AND nearest[j] = i AND i < j THEN
            IF px[i] < px[j] OR (px[i] = px[j] AND py[i] <= py[j]) THEN
                repx := px[i];
                repy := py[i];
            ELSE
                repx := px[j];
                repy := py[j];
            END IF;
            target_x[i] := repx;
            target_y[i] := repy;
            target_x[j] := repx;
            target_y[j] := repy;
        END IF;
    END LOOP;

    FOR i IN 1..n_ext LOOP
        IF es_fin[i] THEN
            piezas[parte_de[i]] := ST_SetPoint(
                piezas[parte_de[i]],
                ST_NPoints(piezas[parte_de[i]]) - 1,
                ST_SetSRID(ST_MakePoint(target_x[i], target_y[i]), 4326)
            );
        ELSE
            piezas[parte_de[i]] := ST_SetPoint(
                piezas[parte_de[i]],
                0,
                ST_SetSRID(ST_MakePoint(target_x[i], target_y[i]), 4326)
            );
        END IF;
    END LOOP;

    SELECT COALESCE(array_agg(p.geom), ARRAY[]::geometry[])
      INTO piezas
      FROM unnest(piezas) AS p(geom)
     WHERE p.geom IS NOT NULL
       AND NOT ST_IsEmpty(p.geom)
       AND ST_NPoints(p.geom) >= 2
       AND ST_Length(p.geom) > 0;

    n_piezas := COALESCE(cardinality(piezas), 0);
    IF n_piezas = 0 THEN
        RETURN NULL;
    END IF;
    IF n_piezas = 1 THEN
        RETURN ST_SetSRID(piezas[1], 4326);
    END IF;

    soldada := ST_LineMerge(ST_UnaryUnion(ST_Collect(piezas)));
    soldada := ST_SetSRID(ST_CollectionExtract(soldada, 2), 4326);
    IF soldada IS NULL OR ST_IsEmpty(soldada) THEN
        RETURN NULL;
    END IF;

    n_out := COALESCE(ST_NumGeometries(soldada), 0);
    IF n_out <= 1 THEN
        RETURN ST_SetSRID(ST_GeometryN(soldada, 1), 4326);
    END IF;

    -- Same walk as geometria_ordenada: westernmost free end, then the
    -- nearest unused end. A branch still returns once to the junction.
    SELECT COALESCE(array_agg(ST_GeometryN(soldada, gs) ORDER BY gs),
                    ARRAY[]::geometry[])
      INTO partes
      FROM generate_series(1, n_out) AS gs;

    -- Second pass, now against the union. The bridge is already inside the
    -- merged line. What is still its own part and lies inside the buffer is
    -- a second drawing that no single input piece covered, so the first pass
    -- kept it. Shortest first. A real gap is not covered and is not filled.
    viva := array_fill(true, ARRAY[n_out]);
    guard := 0;
    WHILE guard < n_out LOOP
        guard := guard + 1;
        mejor := NULL;
        mejor_largo := NULL;
        FOR i IN 1..n_out LOOP
            IF NOT viva[i] THEN
                CONTINUE;
            END IF;
            SELECT ST_UnaryUnion(ST_Collect(p.geom))
              INTO otros
              FROM unnest(partes) WITH ORDINALITY AS p(geom, ord)
             WHERE p.ord::integer <> i
               AND viva[p.ord::integer];
            IF otros IS NULL THEN
                CONTINUE;
            END IF;
            cubre := ST_Covers(
                ST_Buffer(otros::geography, 8.0),
                partes[i]::geography
            );
            IF cubre IS NOT TRUE THEN
                CONTINUE;
            END IF;
            largo_i := ST_Length(partes[i]::geography);
            IF mejor IS NULL
               OR largo_i < mejor_largo
               OR (largo_i = mejor_largo AND i > mejor) THEN
                mejor := i;
                mejor_largo := largo_i;
            END IF;
        END LOOP;
        EXIT WHEN mejor IS NULL;
        viva[mejor] := false;
    END LOOP;

    SELECT COALESCE(array_agg(p.geom ORDER BY p.ord), ARRAY[]::geometry[])
      INTO quedan
      FROM unnest(partes) WITH ORDINALITY AS p(geom, ord)
     WHERE viva[p.ord::integer];
    partes := quedan;
    n_out := COALESCE(cardinality(partes), 0);
    IF n_out = 0 THEN
        RETURN NULL;
    END IF;
    IF n_out = 1 THEN
        RETURN ST_SetSRID(partes[1], 4326);
    END IF;

    usadas := array_fill(false, ARRAY[n_out]);
    seed := NULL;
    seed_x := NULL;
    seed_y := NULL;
    seed_fin := false;
    FOR pass_n IN 1..2 LOOP
        EXIT WHEN seed IS NOT NULL;
        FOR i IN 1..n_out LOOP
            FOR extremo IN 0..1 LOOP
                IF extremo = 0 THEN
                    ax := ST_X(ST_StartPoint(partes[i]));
                    ay := ST_Y(ST_StartPoint(partes[i]));
                ELSE
                    ax := ST_X(ST_EndPoint(partes[i]));
                    ay := ST_Y(ST_EndPoint(partes[i]));
                END IF;
                grado := 0;
                FOR j IN 1..n_out LOOP
                    IF sqrt((ax - ST_X(ST_StartPoint(partes[j]))) ^ 2
                          + (ay - ST_Y(ST_StartPoint(partes[j]))) ^ 2) <= eps THEN
                        grado := grado + 1;
                    END IF;
                    IF sqrt((ax - ST_X(ST_EndPoint(partes[j]))) ^ 2
                          + (ay - ST_Y(ST_EndPoint(partes[j]))) ^ 2) <= eps THEN
                        grado := grado + 1;
                    END IF;
                END LOOP;
                IF pass_n = 1 AND grado > 1 THEN
                    CONTINUE;
                END IF;
                IF seed IS NULL
                   OR ax < seed_x
                   OR (ax = seed_x AND ay < seed_y)
                   OR (ax = seed_x AND ay = seed_y AND i < seed) THEN
                    seed := i;
                    seed_x := ax;
                    seed_y := ay;
                    seed_fin := extremo = 1;
                END IF;
            END LOOP;
        END LOOP;
    END LOOP;

    IF seed_fin THEN
        partes[seed] := ST_Reverse(partes[seed]);
    END IF;
    secuencia := ARRAY[partes[seed]];
    usadas[seed] := true;
    cursorx := ST_X(ST_EndPoint(partes[seed]));
    cursory := ST_Y(ST_EndPoint(partes[seed]));

    WHILE COALESCE(array_length(secuencia, 1), 0) < n_out LOOP
        mejor := NULL;
        mejor_d := NULL;
        mejor_x := NULL;
        mejor_y := NULL;
        mejor_flip := false;
        FOR i IN 1..n_out LOOP
            IF usadas[i] THEN
                CONTINUE;
            END IF;
            sx := ST_X(ST_StartPoint(partes[i]));
            sy := ST_Y(ST_StartPoint(partes[i]));
            ex := ST_X(ST_EndPoint(partes[i]));
            ey := ST_Y(ST_EndPoint(partes[i]));
            d0 := sqrt((cursorx - sx) ^ 2 + (cursory - sy) ^ 2);
            d1 := sqrt((cursorx - ex) ^ 2 + (cursory - ey) ^ 2);
            IF d0 <= d1 THEN
                d := d0;
                flip := false;
                elegido_x := sx;
                elegido_y := sy;
            ELSE
                d := d1;
                flip := true;
                elegido_x := ex;
                elegido_y := ey;
            END IF;
            -- Spheroid metres, not tol. A wider gap keeps the drawn direction.
            IF ST_Distance(
                ST_SetSRID(ST_MakePoint(cursorx, cursory), 4326)::geography,
                ST_SetSRID(ST_MakePoint(elegido_x, elegido_y), 4326)::geography
            ) > 8.0 THEN
                flip := false;
            END IF;
            IF mejor IS NULL
               OR d < mejor_d
               OR (d = mejor_d AND (
                    elegido_x < mejor_x
                    OR (elegido_x = mejor_x AND elegido_y < mejor_y)
                    OR (elegido_x = mejor_x AND elegido_y = mejor_y AND i < mejor)
               )) THEN
                mejor := i;
                mejor_d := d;
                mejor_flip := flip;
                mejor_x := elegido_x;
                mejor_y := elegido_y;
            END IF;
        END LOOP;
        IF mejor IS NULL THEN
            EXIT;
        END IF;
        IF mejor_flip THEN
            partes[mejor] := ST_Reverse(partes[mejor]);
        END IF;
        secuencia := array_append(secuencia, partes[mejor]);
        usadas[mejor] := true;
        cursorx := ST_X(ST_EndPoint(partes[mejor]));
        cursory := ST_Y(ST_EndPoint(partes[mejor]));
    END LOOP;

    SELECT ST_SetSRID(ST_Collect(u.geom ORDER BY u.ord), 4326)
      INTO soldada
      FROM unnest(secuencia) WITH ORDINALITY AS u(geom, ord);
    RETURN soldada;
END;
$soldar$;
"""

SET_FUNCTION_SEARCH_PATH = _PREVIOUS.SET_FUNCTION_SEARCH_PATH
REFRESH_MV = "REFRESH MATERIALIZED VIEW mv_caminos_unificados;"

UPGRADE_STATEMENTS: tuple[str, ...] = (
    CREATE_FUNCTION,
    SET_FUNCTION_SEARCH_PATH,
    REFRESH_MV,
)

DOWNGRADE_STATEMENTS: tuple[str, ...] = (
    _PREVIOUS.CREATE_FUNCTION,
    SET_FUNCTION_SEARCH_PATH,
    REFRESH_MV,
)


def upgrade() -> None:
    for stmt in UPGRADE_STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE_STATEMENTS:
        op.execute(stmt)
