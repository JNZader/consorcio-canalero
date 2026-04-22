/**
 * CollapsibleSection.tsx
 *
 * Small shared primitive for collapsible UI blocks — used across the map
 * chrome (2D + 3D Capas / Leyenda panels) so every collapsible section
 * shares the same behavior, keyboard support, and ARIA semantics.
 *
 * Contract:
 *   - Default state: expanded (`defaultOpen={true}`).
 *   - State is LOCAL (`useState`). No persistence, no Zustand.
 *   - Clicking the title row OR pressing Enter/Space toggles the body.
 *   - The title row carries `role="button"`, `aria-expanded`, `tabIndex=0`.
 *   - A chevron icon on the right swaps between `up` (open) and `down`
 *     (closed). Users can ALSO use the `rightAccessory` slot for a count
 *     badge or another affordance; clicks on the accessory bubble up unless
 *     the consumer calls `stopPropagation()`.
 *
 * Why not Mantine `<Accordion>`? The map panels already carry their own
 * `<Paper>` chrome + custom typography. Accordion would force us to fight
 * its theming for every panel and double-wrap the markup. This primitive
 * gives us the minimum behavior we need, nothing more.
 */

import { Box, Group, Text } from '@mantine/core';
import type { CSSProperties, KeyboardEvent, ReactNode } from 'react';
import { useCallback, useState } from 'react';

import { IconChevronDown, IconChevronUp } from './icons';

export interface CollapsibleSectionProps {
  readonly title: string;
  readonly defaultOpen?: boolean;
  readonly children: ReactNode;
  /**
   * Optional node rendered in the title row, to the left of the chevron.
   * Useful for count badges ("3 visible") or a quick action button. Clicks
   * on accessory children propagate to the header toggle unless the child
   * calls `stopPropagation()`.
   */
  readonly rightAccessory?: ReactNode;
  /**
   * Test id ROOT — the component derives:
   *   - `${testId}` on the outer wrapper
   *   - `${testId}-header` on the clickable title row
   *   - `${testId}-body` on the body container when open
   */
  readonly testId?: string;
  /**
   * Override for the title typography weight / size — default matches the
   * 2D + 3D map panels ("sm" + 600).
   */
  readonly titleSize?: 'xs' | 'sm' | 'md' | 'lg';
  readonly titleWeight?: 400 | 500 | 600 | 700;
  /** Optional extra style for the outer Box wrapper. */
  readonly style?: CSSProperties;
}

export function CollapsibleSection({
  title,
  defaultOpen = true,
  children,
  rightAccessory,
  testId,
  titleSize = 'sm',
  titleWeight = 600,
  style,
}: CollapsibleSectionProps) {
  const [open, setOpen] = useState(defaultOpen);

  const toggle = useCallback(() => setOpen((v) => !v), []);

  const handleKeyDown = useCallback(
    (event: KeyboardEvent<HTMLDivElement>) => {
      if (event.key === 'Enter' || event.key === ' ' || event.key === 'Spacebar') {
        event.preventDefault();
        toggle();
      }
    },
    [toggle]
  );

  return (
    <Box data-testid={testId} style={style}>
      <Group
        data-testid={testId ? `${testId}-header` : undefined}
        role="button"
        aria-expanded={open}
        tabIndex={0}
        onClick={toggle}
        onKeyDown={handleKeyDown}
        justify="space-between"
        wrap="nowrap"
        style={{ cursor: 'pointer', userSelect: 'none' }}
      >
        <Text size={titleSize} fw={titleWeight}>
          {title}
        </Text>
        <Group gap={4} wrap="nowrap">
          {rightAccessory}
          {open ? (
            <IconChevronUp size={14} aria-hidden="true" />
          ) : (
            <IconChevronDown size={14} aria-hidden="true" />
          )}
        </Group>
      </Group>
      {open && (
        <Box data-testid={testId ? `${testId}-body` : undefined} mt={6}>
          {children}
        </Box>
      )}
    </Box>
  );
}
