import { Paper, Text, TextInput } from '@mantine/core';
import type { Feature, GeoJsonProperties, Geometry } from 'geojson';
import { type ReactNode, useEffect, useState } from 'react';
import styles from '../../styles/components/map.module.css';
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

interface SearchOptionItem {
  readonly id: string;
  readonly key: string;
  readonly testId?: string;
  readonly content: ReactNode;
  readonly onSelect: () => void;
}

const LISTBOX_ID = 'map-search-listbox';

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
  const [activeIndex, setActiveIndex] = useState<number>(-1);
  const [dismissed, setDismissed] = useState<boolean>(false);

  const canals = searchCanales(canalIndex, query);
  const parcelHits = searchParcelas(parcels, query);
  const coordinate = parseCoordinateQuery(query);
  const showParcelsPending = query.trim().length >= 3 && parcelsLoading && parcelHits.length === 0;
  const remember = (value: string) => setRecent(rememberSearch(value));

  useEffect(() => {
    setDismissed(false);
    setActiveIndex(-1);
  }, [query]);

  const isRecentMode = query.trim().length === 0;

  const options: SearchOptionItem[] = [];
  if (!isRecentMode) {
    for (const hit of canals) {
      const idx = options.length;
      options.push({
        id: `map-search-option-${idx}`,
        key: `${hit.estado}:${hit.id}`,
        content: (
          <>
            <Text size="xs">{hit.nombre}</Text>
            <Text size="xs" c="dimmed">
              {hit.estado === 'relevado' ? 'Canal relevado' : 'Canal propuesto'}
              {hit.codigo ? ` · ${hit.codigo}` : ''}
            </Text>
          </>
        ),
        onSelect: () => {
          remember(query);
          onPickCanal(hit.id);
          setDismissed(true);
          setActiveIndex(-1);
        },
      });
    }

    for (const hit of parcelHits) {
      const idx = options.length;
      options.push({
        id: `map-search-option-${idx}`,
        key: hit.key,
        content: (
          <>
            <Text size="xs">Cuenta {hit.label}</Text>
            {hit.detail ? (
              <Text size="xs" c="dimmed">
                {hit.detail}
              </Text>
            ) : null}
          </>
        ),
        onSelect: () => {
          remember(query);
          onPickParcel(hit.feature);
          setDismissed(true);
          setActiveIndex(-1);
        },
      });
    }

    if (coordinate?.ok) {
      const idx = options.length;
      options.push({
        id: `map-search-option-${idx}`,
        key: 'coordinate-hit',
        testId: 'map-search-coordinate',
        content: (
          <>
            <Text size="xs">Ir a estas coordenadas</Text>
            <Text size="xs" c="dimmed">
              {coordinate.point.lat.toFixed(5)}, {coordinate.point.lon.toFixed(5)}
            </Text>
          </>
        ),
        onSelect: () => {
          remember(query);
          onPickCoordinate?.(coordinate.point.lat, coordinate.point.lon);
          setDismissed(true);
          setActiveIndex(-1);
        },
      });
    }
  } else {
    for (const item of recent) {
      const idx = options.length;
      options.push({
        id: `map-search-option-${idx}`,
        key: `recent:${item}`,
        content: <Text size="xs">{item}</Text>,
        onSelect: () => {
          onQueryChange(item);
          setDismissed(false);
          setActiveIndex(-1);
        },
      });
    }
  }

  const isOpen = !dismissed && options.length > 0;
  const activeOption = isOpen && activeIndex >= 0 && activeIndex < options.length ? options[activeIndex] : undefined;

  return (
    <Paper
      shadow="sm"
      p="xs"
      radius="md"
      data-testid="map-search"
      className={styles.mapSearchBox}
    >
      <TextInput
        size="xs"
        label="Buscar canal o cuenta"
        placeholder="Nombre, código o cuenta"
        value={query}
        onChange={(event) => {
          setDismissed(false);
          setActiveIndex(-1);
          onQueryChange(event.currentTarget.value);
        }}
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown') {
            if (options.length === 0) return;
            event.preventDefault();
            if (dismissed) {
              setDismissed(false);
              setActiveIndex(0);
            } else {
              setActiveIndex((prev) => (prev + 1) % options.length);
            }
          } else if (event.key === 'ArrowUp') {
            if (options.length === 0) return;
            event.preventDefault();
            if (dismissed) {
              setDismissed(false);
              setActiveIndex(options.length - 1);
            } else {
              setActiveIndex((prev) => (prev <= 0 ? options.length - 1 : prev - 1));
            }
          } else if (event.key === 'Enter') {
            if (isOpen && activeOption) {
              event.preventDefault();
              activeOption.onSelect();
            }
          } else if (event.key === 'Escape') {
            if (isOpen || !dismissed) {
              event.preventDefault();
              setDismissed(true);
              setActiveIndex(-1);
            }
          }
        }}
        role="combobox"
        aria-expanded={isOpen}
        aria-controls={isOpen ? LISTBOX_ID : undefined}
        aria-autocomplete="list"
        aria-activedescendant={activeOption?.id}
        autoComplete="off"
      />
      {isOpen ? (
        <div
          id={LISTBOX_ID}
          role="listbox"
          aria-label={isRecentMode ? 'Búsquedas recientes' : 'Resultados de búsqueda'}
          style={{ listStyle: 'none', margin: '8px 0 0', padding: 0 }}
        >
          {options.map((opt, idx) => {
            const isSelected = idx === activeIndex;
            return (
              <div
                key={opt.key}
                id={opt.id}
                role="option"
                tabIndex={-1}
                aria-selected={isSelected}
                data-testid={opt.testId}
                onMouseEnter={() => setActiveIndex(idx)}
                onClick={() => opt.onSelect()}
                style={{
                  display: 'block',
                  width: '100%',
                  textAlign: 'left',
                  background: isSelected ? 'var(--mantine-color-blue-light)' : 'transparent',
                  borderRadius: 4,
                  padding: '4px 6px',
                  cursor: 'pointer',
                }}
              >
                {opt.content}
              </div>
            );
          })}
        </div>
      ) : null}
      {!dismissed && !isRecentMode && coordinate && !coordinate.ok ? (
        <Text size="xs" c="red" mt={6} data-testid="map-search-coordinate-bounds">
          Esas coordenadas quedan fuera de Córdoba.
        </Text>
      ) : null}
      {!dismissed && !isRecentMode && showParcelsPending ? (
        <Text size="xs" c="dimmed" mt={6}>
          Buscando parcelas…
        </Text>
      ) : null}
      <MapShareLink />
    </Paper>
  );
}
