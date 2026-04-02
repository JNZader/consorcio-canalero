/**
 * Zustand store for flood calibration state management.
 *
 * Manages: selected date, labeled zones, flood events list,
 * training results, rainfall data, and loading flags for the calibration page.
 */

import { create } from 'zustand';

import type { RainfallEvent, RainfallSuggestion } from '../lib/api/floodCalibration';

// ============================================
// TYPES
// ============================================

/** Zone label state: true = flooded, false = not flooded */
export type ZoneLabelState = boolean;

export interface FloodEventListItem {
  id: string;
  event_date: string;
  label_count: number;
  created_at: string;
  description?: string | null;
}

export interface FloodEventDetail {
  id: string;
  event_date: string;
  description: string | null;
  satellite_source: string;
  label_count: number;
  features_extracted: boolean;
  created_at: string;
  labels: FloodLabelItem[];
}

export interface FloodLabelItem {
  id: string;
  zona_id: string;
  is_flooded: boolean;
  ndwi_value: number | null;
  extracted_features: Record<string, number> | null;
}

export interface TrainingResult {
  events_used: number;
  epochs: number;
  initial_loss: number;
  final_loss: number;
  weights: Record<string, number>;
  bias: number;
  backup_path: string;
}

// ============================================
// STATE & ACTIONS
// ============================================

interface FloodCalibrationState {
  selectedDate: string | null;
  labeledZones: Record<string, ZoneLabelState>;
  events: FloodEventListItem[];
  eventsLoading: boolean;
  trainingResult: TrainingResult | null;
  trainingLoading: boolean;
  savingEvent: boolean;
  eventDescription: string;

  // Rainfall state
  /** Map of date string (YYYY-MM-DD) to precipitation in mm */
  rainfallByDate: Record<string, number>;
  rainfallLoading: boolean;
  rainfallEvents: RainfallEvent[];
  rainfallEventsLoading: boolean;
  suggestions: RainfallSuggestion[];
  suggestionsLoading: boolean;
}

interface FloodCalibrationActions {
  setSelectedDate: (date: string | null) => void;
  toggleZoneLabel: (zonaId: string) => void;
  clearLabels: () => void;
  setEvents: (events: FloodEventListItem[]) => void;
  setEventsLoading: (loading: boolean) => void;
  removeEvent: (id: string) => void;
  setTrainingResult: (result: TrainingResult | null) => void;
  setTrainingLoading: (loading: boolean) => void;
  setSavingEvent: (saving: boolean) => void;
  setEventDescription: (description: string) => void;

  // Rainfall actions
  setRainfallByDate: (data: Record<string, number>) => void;
  setRainfallLoading: (loading: boolean) => void;
  setRainfallEvents: (events: RainfallEvent[]) => void;
  setRainfallEventsLoading: (loading: boolean) => void;
  setSuggestions: (suggestions: RainfallSuggestion[]) => void;
  setSuggestionsLoading: (loading: boolean) => void;

  reset: () => void;
}

const initialState: FloodCalibrationState = {
  selectedDate: null,
  labeledZones: {},
  events: [],
  eventsLoading: false,
  trainingResult: null,
  trainingLoading: false,
  savingEvent: false,
  eventDescription: '',

  // Rainfall initial state
  rainfallByDate: {},
  rainfallLoading: false,
  rainfallEvents: [],
  rainfallEventsLoading: false,
  suggestions: [],
  suggestionsLoading: false,
};

// ============================================
// STORE
// ============================================

export const useFloodCalibrationStore = create<FloodCalibrationState & FloodCalibrationActions>()(
  (set) => ({
    ...initialState,

    setSelectedDate: (date) => set({ selectedDate: date }),

    /**
     * Toggle zone flood label: unlabeled -> flooded -> not-flooded -> unlabeled.
     * State cycle: undefined -> true -> false -> delete
     */
    toggleZoneLabel: (zonaId) =>
      set((state) => {
        const current = state.labeledZones[zonaId];
        const next = { ...state.labeledZones };

        if (current === undefined) {
          // unlabeled -> flooded
          next[zonaId] = true;
        } else if (current === true) {
          // flooded -> not-flooded
          next[zonaId] = false;
        } else {
          // not-flooded -> unlabeled (remove)
          delete next[zonaId];
        }

        return { labeledZones: next };
      }),

    clearLabels: () => set({ labeledZones: {}, eventDescription: '' }),

    setEvents: (events) => set({ events }),
    setEventsLoading: (loading) => set({ eventsLoading: loading }),

    removeEvent: (id) =>
      set((state) => ({
        events: state.events.filter((e) => e.id !== id),
      })),

    setTrainingResult: (result) => set({ trainingResult: result }),
    setTrainingLoading: (loading) => set({ trainingLoading: loading }),
    setSavingEvent: (saving) => set({ savingEvent: saving }),
    setEventDescription: (description) => set({ eventDescription: description }),

    // Rainfall actions
    setRainfallByDate: (data) => set({ rainfallByDate: data }),
    setRainfallLoading: (loading) => set({ rainfallLoading: loading }),
    setRainfallEvents: (events) => set({ rainfallEvents: events }),
    setRainfallEventsLoading: (loading) => set({ rainfallEventsLoading: loading }),
    setSuggestions: (suggestions) => set({ suggestions }),
    setSuggestionsLoading: (loading) => set({ suggestionsLoading: loading }),

    reset: () => set(initialState),
  }),
);

// ============================================
// SELECTORS
// ============================================

/** Number of labeled zones in current session */
export const selectLabeledCount = (state: FloodCalibrationState) =>
  Object.keys(state.labeledZones).length;

/** Whether any zones are labeled (enables save button) */
export const selectHasLabels = (state: FloodCalibrationState) =>
  Object.keys(state.labeledZones).length > 0;

/** Whether a date is selected and zones are labeled (enables save) */
export const selectCanSave = (state: FloodCalibrationState) =>
  state.selectedDate !== null && Object.keys(state.labeledZones).length > 0;

/** Count of rainfall suggestions available */
export const selectSuggestionsCount = (state: FloodCalibrationState) =>
  state.suggestions.length;

/** Get rainfall mm for a specific date */
export const selectRainfallForDate = (date: string) => (state: FloodCalibrationState) =>
  state.rainfallByDate[date] ?? null;
