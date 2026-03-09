-- Agrega orden del dia a reuniones sin romper registros existentes
ALTER TABLE reuniones
ADD COLUMN IF NOT EXISTS orden_del_dia TEXT;
