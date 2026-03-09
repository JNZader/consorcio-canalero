-- Reemplaza texto libre por checklist estructurado para reuniones
ALTER TABLE reuniones
ADD COLUMN IF NOT EXISTS orden_del_dia_items JSONB NOT NULL DEFAULT '[]'::jsonb;

WITH migrated_items AS (
    SELECT
        r.id,
        jsonb_agg(normalized.trimmed_item) FILTER (WHERE normalized.trimmed_item <> '') AS items
    FROM reuniones r
    CROSS JOIN LATERAL unnest(
        regexp_split_to_array(COALESCE(r.orden_del_dia, ''), E'\\r?\\n+')
    ) AS raw_item
    CROSS JOIN LATERAL (
        SELECT trim(raw_item) AS trimmed_item
    ) normalized
    GROUP BY r.id
)
UPDATE reuniones r
SET orden_del_dia_items = COALESCE(m.items, '[]'::jsonb)
FROM migrated_items m
WHERE r.id = m.id;

ALTER TABLE reuniones
DROP COLUMN IF EXISTS orden_del_dia;
