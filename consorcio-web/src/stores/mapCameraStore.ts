import { create } from 'zustand';

export interface MapCamera {
  lng: number;
  lat: number;
  zoom: number;
  bearing: number;
  pitch: number;
}

interface MapCameraStore {
  camera: MapCamera | null;
  setCamera: (camera: MapCamera) => void;
}

/** In-memory 2D↔3D camera handoff (UX PDF T1). Not persisted. */
export const useMapCameraStore = create<MapCameraStore>((set) => ({
  camera: null,
  setCamera: (camera) => set({ camera }),
}));
