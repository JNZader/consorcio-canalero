import { Paper, Text, TextInput } from '@mantine/core';
import type { Feature, GeoJsonProperties, Geometry } from 'geojson';
import { useState } from 'react';
import type { IndexFile } from '../../types/canales';
import { parseCoordinateQuery } from './mapCoordinates';
import { searchCanales, searchParcelas } from './mapSearch';
import { readRecentSearches, rememberSearch } from './mapSearchHistory';
import { MapShareLink } from './MapShareLink';

export interface MapSearchModel {
  readonly query: string;
  readonly onQueryChange: (query: string) => void;
  readonly canalIndex: IndexFile | null;
  readonly parcels: readonly Feature<Geometry, GeoJsonProperties>[] | null;
  readonly parcelsLoading: boolean;
  readonly onPickCanal: (id: string) => void;
  readonly onPickParcel: (feature: Feature<Geometry, GeoJsonProperties>) => void;
  readonly onPickCoordinate?: (lat: number, lon: number) => void;
}

export function MapSearchBox({
  query,
  onQueryChange,
  canalIndex,
  parcels,
  parcelsLoading,
  onPickCanal,
  onPickParcel,
  onPickCoordinate,
}: MapSearchModel) {
  const [recent, setRecent] = useState<string[]>(() => readRecentSearches());
  const canals = searchCanales(canalIndex, query);
  const parcelHits = searchParcelas(parcels, query);
  const coordinate = parseCoordinateQuery(query);
  const showParcelsPending = query.trim().length >= 3 && parcelsLoading && parcelHits.length === 0;
  const remember = (value: string) => setRecent(rememberSearch(value));

  return (
    <Paper
      shadow="sm"
      p="xs"
      radius="md"
      data-testid="map-search"
      style={{
        position: 'absolute',
        top: 12,
        left: 12,
        zIndex: 12,
        width: 'min(320px, calc(100% - 24px))',
      }}
    >
      <TextInput
        size="xs"
        label="Buscar canal o cuenta"
        placeholder="Nombre, código o cuenta"
        value={query}
        onChange={(event) => onQueryChange(event.currentTarget.value)}
        autoComplete="off"
      />
      {canals.length > 0 || parcelHits.length > 0 || showParcelsPending ? (
        <ul
          aria-label="Resultados de búsqueda"
          style={{ listStyle: 'none', margin: '8px 0 0', padding: 0 }}
        >
          {canals.map((hit) => (
            <li key={`${hit.estado}:${hit.id}`}>
              <button
                type="button"
                onClick={() => {
                  remember(query);
                  onPickCanal(hit.id);
                }}
                style={{
                  display: 'block',
                  width: '100%',
                  textAlign: 'left',
                  background: 'transparent',
                  border: 0,
                  padding: '4px 0',
                  cursor: 'pointer',
                }}
              >
                <Text size="xs">{hit.nombre}</Text>
                <Text size="xs" c="dimmed">
                  {hit.estado === 'relevado' ? 'Canal relevado' : 'Canal propuesto'}
                  {hit.codigo ? ` · ${hit.codigo}` : ''}
                </Text>
              </button>
            </li>
          ))}
          {parcelHits.map((hit) => (
            <li key={hit.key}>
              <button
                type="button"
                onClick={() => {
                  remember(query);
                  onPickParcel(hit.feature);
                }}
                style={{
                  display: 'block',
                  width: '100%',
                  textAlign: 'left',
                  background: 'transparent',
                  border: 0,
                  padding: '4px 0',
                  cursor: 'pointer',
                }}
              >
                <Text size="xs">Cuenta {hit.label}</Text>
                {hit.detail ? (
                  <Text size="xs" c="dimmed">
                    {hit.detail}
                  </Text>
                ) : null}
              </button>
            </li>
          ))}
          {coordinate?.ok ? (
            <li>
              <button
                type="button"
                data-testid="map-search-coordinate"
                onClick={() => {
                  remember(query);
                  onPickCoordinate?.(coordinate.point.lat, coordinate.point.lon);
                }}
                style={{
                  display: 'block',
                  width: '100%',
                  textAlign: 'left',
                  background: 'transparent',
                  border: 0,
                  padding: '4px 0',
                  cursor: 'pointer',
                }}
              >
                <Text size="xs">Ir a estas coordenadas</Text>
                <Text size="xs" c="dimmed">
                  {coordinate.point.lat.toFixed(5)}, {coordinate.point.lon.toFixed(5)}
                </Text>
              </button>
            </li>
          ) : null}
          {coordinate && !coordinate.ok ? (
            <li>
              <Text size="xs" c="red" data-testid="map-search-coordinate-bounds">
                Esas coordenadas quedan fuera de Córdoba.
              </Text>
            </li>
          ) : null}
          {showParcelsPending ? (
            <li>
              <Text size="xs" c="dimmed">
                Buscando parcelas…
              </Text>
            </li>
          ) : null}
        </ul>
      ) : null}
      {query.trim().length === 0 && recent.length > 0 ? (
        <ul aria-label="Búsquedas recientes" style={{ listStyle: 'none', margin: '8px 0 0', padding: 0 }}>
          {recent.map((item) => (
            <li key={item}>
              <button
                type="button"
                onClick={() => onQueryChange(item)}
                style={{
                  display: 'block',
                  width: '100%',
                  textAlign: 'left',
                  background: 'transparent',
                  border: 0,
                  padding: '4px 0',
                  cursor: 'pointer',
                }}
              >
                <Text size="xs">{item}</Text>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      <MapShareLink />
    </Paper>
  );
}
