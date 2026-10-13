import { Box, Menu, UnstyledButton } from '@mantine/core';

import { MAP_QUICK_PLACES } from '../../constants';
import { mapColorTokens } from '../../lib/mapColorTokens';
import styles from '../../styles/components/map.module.css';
import { IconCurrentLocation, IconHome, IconMapPin } from '../ui/icons';
import { MAP_CTRL_GLYPH_SIZE } from './map2dConfig';

interface MapPlacesControlProps {
  readonly onRecenter: () => void;
  readonly onFlyToPlace: (placeId: (typeof MAP_QUICK_PLACES)[number]['id']) => void;
  readonly onGeolocate?: () => void;
}

/**
 * Home + quick places (UX PDF R9). Styled like MapLibre ctrl-group.
 * Buttons are BARE (no Tooltip wrappers): Mantine Tooltip inserts a div
 * that breaks `button + button` dividers and the 29px group, so hover
 * looked like overlapping/broken chrome.
 */
export function MapPlacesControl({ onRecenter, onFlyToPlace, onGeolocate }: MapPlacesControlProps) {
  return (
    <Box className={`maplibregl-ctrl maplibregl-ctrl-group ${styles.mapPlacesDock}`}>
      <UnstyledButton
        type="button"
        aria-label="Volver al consorcio"
        title="Volver al consorcio"
        className={styles.mapCtrlButton}
        data-testid="map-recenter-consorcio"
        onClick={onRecenter}
        style={{ color: mapColorTokens.h333 }}
      >
        <IconHome size={MAP_CTRL_GLYPH_SIZE} />
      </UnstyledButton>
      <Menu shadow="md" position="left-start" width={180}>
        <Menu.Target>
          <UnstyledButton
            type="button"
            aria-label="Lugares rápidos"
            title="Lugares rápidos"
            className={styles.mapCtrlButton}
            data-testid="map-quick-places"
            style={{ color: mapColorTokens.h333 }}
          >
            <IconMapPin size={MAP_CTRL_GLYPH_SIZE} />
          </UnstyledButton>
        </Menu.Target>
        <Menu.Dropdown>
          {onGeolocate ? (
            <Menu.Item
              leftSection={<IconCurrentLocation size={14} />}
              onClick={onGeolocate}
              data-testid="map-geolocate"
            >
              Ubicarme
            </Menu.Item>
          ) : null}
          {MAP_QUICK_PLACES.map((place) => (
            <Menu.Item key={place.id} onClick={() => onFlyToPlace(place.id)}>
              {place.label}
            </Menu.Item>
          ))}
        </Menu.Dropdown>
      </Menu>
    </Box>
  );
}
