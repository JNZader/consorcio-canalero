import { create } from 'zustand';

/** Punto elegido en el mapa para precargar una denuncia. No es el GPS silencioso. */
interface ReportAnchorState {
  readonly anchor: { lat: number; lng: number } | null;
  readonly geolocatePin: { lat: number; lng: number } | null;
  setAnchor: (anchor: { lat: number; lng: number } | null) => void;
  setGeolocatePin: (pin: { lat: number; lng: number } | null) => void;
}

export const useReportAnchorStore = create<ReportAnchorState>((set) => ({
  anchor: null,
  geolocatePin: null,
  setAnchor: (anchor) => set({ anchor }),
  setGeolocatePin: (pin) => set({ geolocatePin: pin }),
}));
