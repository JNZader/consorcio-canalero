/**
 * Spanish (Rioplatense) strings for MapLibre control chrome (I18N-01).
 * Keys must match `defaultLocale` in maplibre-gl — a typo leaves English.
 */
export const MAP_LOCALE_ES = {
  'AttributionControl.ToggleAttribution': 'Mostrar u ocultar atribución',
  'AttributionControl.MapFeedback': 'Comentarios del mapa',
  'FullscreenControl.Enter': 'Pantalla completa',
  'FullscreenControl.Exit': 'Salir de pantalla completa',
  'GeolocateControl.FindMyLocation': 'Ir a mi ubicación',
  'GeolocateControl.LocationNotAvailable': 'Ubicación no disponible',
  'LogoControl.Title': 'Logo de MapLibre',
  'Map.Title': 'Mapa',
  'Marker.Title': 'Marcador',
  'NavigationControl.ResetBearing': 'Arrastrá para rotar, clic para volver al norte',
  'NavigationControl.ZoomIn': 'Acercar',
  'NavigationControl.ZoomOut': 'Alejar',
  'Popup.Close': 'Cerrar',
  'ScaleControl.Feet': 'ft',
  'ScaleControl.Meters': 'm',
  'ScaleControl.Kilometers': 'km',
  'ScaleControl.Miles': 'mi',
  'ScaleControl.NauticalMiles': 'nm',
  'GlobeControl.Enable': 'Activar globo',
  'GlobeControl.Disable': 'Desactivar globo',
  'TerrainControl.Enable': 'Activar terreno',
  'TerrainControl.Disable': 'Desactivar terreno',
  'CooperativeGesturesHandler.WindowsHelpText': 'Usá Ctrl + desplazamiento para hacer zoom',
  'CooperativeGesturesHandler.MacHelpText': 'Usá ⌘ + desplazamiento para hacer zoom',
  'CooperativeGesturesHandler.MobileHelpText': 'Usá dos dedos para mover el mapa',
} as const;

export type MapLibreLocaleKey = keyof typeof MAP_LOCALE_ES;
