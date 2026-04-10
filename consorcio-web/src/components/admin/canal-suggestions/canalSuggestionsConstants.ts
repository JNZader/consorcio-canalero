import type { SuggestionTipo } from '../../../lib/api';

export const TIPO_LABELS: Record<SuggestionTipo, string> = {
  hotspot: 'Punto critico',
  gap: 'Brecha de cobertura',
  route: 'Ruta sugerida',
  bottleneck: 'Cuello de botella',
  maintenance: 'Prioridad de mantenimiento',
};

export const TIPO_COLORS: Record<SuggestionTipo, string> = {
  hotspot: '#e8590c',
  gap: '#e03131',
  route: '#1971c2',
  bottleneck: '#c92a2a',
  maintenance: '#2f9e44',
};

export const TIPO_OPTIONS = [
  { value: '', label: 'Todos los tipos' },
  { value: 'hotspot', label: 'Puntos criticos' },
  { value: 'gap', label: 'Brechas de cobertura' },
  { value: 'route', label: 'Rutas sugeridas' },
  { value: 'bottleneck', label: 'Cuellos de botella' },
  { value: 'maintenance', label: 'Prioridad de mantenimiento' },
];

export const ALL_SUGGESTION_TYPES: SuggestionTipo[] = [
  'hotspot',
  'gap',
  'route',
  'bottleneck',
  'maintenance',
];
