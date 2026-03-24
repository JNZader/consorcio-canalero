import { isCanonicalTramiteEstado, type TramiteEstadoCanonico } from '../../../constants/tramites';

export interface RawTramiteItem {
  id: string;
  titulo: string;
  numero_expediente: string;
  estado: string;
  ultima_actualizacion: string;
}

export interface CanonicalTramiteItem extends Omit<RawTramiteItem, 'estado'> {
  estado: TramiteEstadoCanonico;
}

export function filterCanonicalTramites(items: RawTramiteItem[]): {
  canonical: CanonicalTramiteItem[];
  discarded: RawTramiteItem[];
} {
  const canonical: CanonicalTramiteItem[] = [];
  const discarded: RawTramiteItem[] = [];

  for (const item of items) {
    if (isCanonicalTramiteEstado(item.estado)) {
      canonical.push(item as CanonicalTramiteItem);
    } else {
      discarded.push(item);
    }
  }

  return { canonical, discarded };
}
