export interface Reunion {
  id: string;
  titulo: string;
  fecha_reunion: string;
  lugar: string;
  descripcion?: string;
  orden_del_dia_items?: string[];
  estado: string;
}

export interface AgendaReference {
  entidad_tipo: string;
  entidad_id: string;
  metadata?: {
    label?: string;
    [key: string]: unknown;
  };
}

export interface AgendaItem {
  id: string;
  titulo: string;
  descripcion: string;
  referencias: AgendaReference[];
}

export interface EntityOption {
  value: string;
  label: string;
  group: string;
  type: string;
}
