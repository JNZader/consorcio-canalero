import { Box, Menu, Tooltip, UnstyledButton } from '@mantine/core';

import { MAP_QUICK_PLACES } from '../../constants';
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
 */
export function MapPlacesControl({ onRecenter, onFlyToPlace, onGeolocate }: MapPlacesControlProps) {
  return (
    <Box
      className={`maplibregl-ctrl maplibregl-ctrl-group ${styles.mapPlacesDock}`}
    >
      <Tooltip label="Volver al consorcio" position="left" withArrow>
        <UnstyledButton
          type="button"
          aria-label="Volver al consorcio"
          className={styles.mapCtrlButton}
          data-testid="map-recenter-consorcio"
          onClick={onRecenter}
          style={{ color: '#333' }}
        >
          <IconHome size={MAP_CTRL_GLYPH_SIZE} />
        </UnstyledButton>
      </Tooltip>
      {onGeolocate ? (
        <Tooltip label="Ubicarme" position="left" withArrow>
          <UnstyledButton
            type="button"
            aria-label="Ubicarme"
            className={styles.mapCtrlButton}
            data-testid="map-geolocate"
            onClick={onGeolocate}
            style={{ color: '#333' }}
          >
            <IconCurrentLocation size={MAP_CTRL_GLYPH_SIZE} />
          </UnstyledButton>
        </Tooltip>
      ) : null}
      <Menu shadow="md" position="left-start" width={180}>
        <Menu.Target>
          <Tooltip label="Lugares rápidos" position="left" withArrow>
            <UnstyledButton
              type="button"
              aria-label="Lugares rápidos"
              className={styles.mapCtrlButton}
              data-testid="map-quick-places"
              style={{ color: '#333' }}
            >
              <IconMapPin size={MAP_CTRL_GLYPH_SIZE} />
            </UnstyledButton>
          </Tooltip>
        </Menu.Target>
        <Menu.Dropdown>
          {MAP_QUICK_PLACES.map((place) => (
            <Menu.Item
              key={place.id}
              onClick={() => onFlyToPlace(place.id)}
            >
              {place.label}
            </Menu.Item>
          ))}
        </Menu.Dropdown>
      </Menu>
    </Box>
  );
}
