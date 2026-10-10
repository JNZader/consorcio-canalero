import { ActionIcon, Group, Paper, Text } from '@mantine/core';
import { useState } from 'react';

import { IconChevronDown, IconChevronUp } from '../ui/icons';

interface MapTimeBarProps {
  readonly imageDate?: string | null;
  readonly imageSensor?: string | null;
  readonly compareLeftDate?: string | null;
  readonly compareRightDate?: string | null;
}

/**
 * Collapsible time strip (UX PDF R8 first slice).
 * Only mounts when a temporal layer is on (selected image or swipe pair).
 * No play/pause and no full date catalog — those need the image explorer API.
 */
export function MapTimeBar({
  imageDate,
  imageSensor,
  compareLeftDate,
  compareRightDate,
}: MapTimeBarProps) {
  const [open, setOpen] = useState(true);
  const compare =
    compareLeftDate && compareRightDate ? `${compareLeftDate} → ${compareRightDate}` : null;
  const single = imageDate
    ? `${imageSensor ? `${imageSensor} · ` : ''}${imageDate}`
    : null;
  const label = compare ?? single;
  if (!label) return null;

  return (
    <Paper
      shadow="md"
      p="xs"
      radius="md"
      data-testid="map-time-bar"
      style={{
        position: 'absolute',
        left: '50%',
        bottom: 12,
        transform: 'translateX(-50%)',
        zIndex: 14,
        minWidth: 220,
        maxWidth: 'min(420px, 90%)',
      }}
    >
      <Group justify="space-between" wrap="nowrap" gap="xs">
        <Text size="xs" fw={600}>
          Tiempo
        </Text>
        <ActionIcon
          size="sm"
          variant="subtle"
          aria-label={open ? 'Contraer barra de tiempo' : 'Ampliar barra de tiempo'}
          onClick={() => setOpen((value) => !value)}
        >
          {open ? <IconChevronDown size={14} /> : <IconChevronUp size={14} />}
        </ActionIcon>
      </Group>
      {open && (
        <Text size="xs" c="dimmed" mt={4} data-testid="map-time-bar-label">
          {label}
        </Text>
      )}
    </Paper>
  );
}
