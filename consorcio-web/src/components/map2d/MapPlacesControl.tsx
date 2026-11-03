import { Box, UnstyledButton } from '@mantine/core';

import { mapColorTokens } from '../../lib/mapColorTokens';
import styles from '../../styles/components/map.module.css';
import { IconHome } from '../ui/icons';
import { MAP_CTRL_GLYPH_SIZE } from './map2dConfig';

interface MapPlacesControlProps {
  readonly onRecenter: () => void;
}

/**
 * Home (UX PDF R9). Quick places live in the search box. The button is BARE
 * (no Tooltip wrapper): Mantine Tooltip inserts a div that breaks the 29px
 * MapLibre control group.
 */
export function MapPlacesControl({ onRecenter }: MapPlacesControlProps) {
  return (
    <Box className={`maplibregl-ctrl maplibregl-ctrl-group ${styles.mapPlacesDock}`}>
      <UnstyledButton
        type="button"
        aria-label="Volver al consorcio"
        title="Inicio"
        className={styles.mapCtrlButton}
        data-testid="map-recenter-consorcio"
        onClick={onRecenter}
        style={{ color: mapColorTokens.h333 }}
      >
        <IconHome size={MAP_CTRL_GLYPH_SIZE} />
      </UnstyledButton>
    </Box>
  );
}
