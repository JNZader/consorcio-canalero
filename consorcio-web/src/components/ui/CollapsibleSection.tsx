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
 *   - Clicking the title button OR pressing Enter/Space toggles the body.
 *   - The title is a native button carrying `aria-expanded` and
 *     `aria-controls`.
 *   - The body carries `role="region"` and is labelled by the title row.
 *   - A chevron icon on the right swaps between `up` (open) and `down`
 *     (closed). Users can ALSO use the `rightAccessory` slot for a count
 *     badge or another affordance. It is rendered beside, never inside, the
 *     title button so interactive accessories keep valid HTML semantics.
 *
 * Why not Mantine `<Accordion>`? The map panels already carry their own
 * `<Paper>` chrome + custom typography. Accordion would force us to fight
 * its theming for every panel and double-wrap the markup. This primitive
 * gives us the minimum behavior we need, nothing more.
 */

import { Box, Group, Text, UnstyledButton } from '@mantine/core';
import type { CSSProperties, ReactNode } from 'react';
import { useCallback, useId, useState } from 'react';

import { IconChevronDown, IconChevronUp } from './icons';

export interface CollapsibleSectionProps {
  readonly title: string;
  readonly defaultOpen?: boolean;
  readonly children: ReactNode;
  /**
   * Optional node rendered beside the title button. Useful for count badges
   * ("3 visible") or a quick action button without nesting interactive
   * controls inside the collapsible toggle.
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
  const generatedId = useId();
  const sectionId = testId ?? `collapsible-section-${generatedId}`;
  const headerId = `${sectionId}-header`;
  const bodyId = `${sectionId}-body`;

  const toggle = useCallback(() => setOpen((v) => !v), []);

  return (
    <Box data-testid={testId} style={style}>
      <Group justify="space-between" wrap="nowrap" gap={4}>
        <UnstyledButton
          data-testid={testId ? `${testId}-header` : undefined}
          id={headerId}
          type="button"
          aria-expanded={open}
          aria-controls={bodyId}
          onClick={toggle}
          style={{
            alignItems: 'center',
            cursor: 'pointer',
            display: 'flex',
            flex: 1,
            gap: 8,
            justifyContent: 'space-between',
            minWidth: 0,
            userSelect: 'none',
          }}
        >
          <Text component="span" size={titleSize} fw={titleWeight}>
            {title}
          </Text>
          {open ? (
            <IconChevronUp size={14} aria-hidden="true" />
          ) : (
            <IconChevronDown size={14} aria-hidden="true" />
          )}
        </UnstyledButton>
        {rightAccessory && (
          <Group gap={4} wrap="nowrap">
            {rightAccessory}
          </Group>
        )}
      </Group>
      {open && (
        <Box
          data-testid={testId ? `${testId}-body` : undefined}
          id={bodyId}
          role="region"
          aria-labelledby={headerId}
          mt={6}
        >
          {children}
        </Box>
      )}
    </Box>
  );
}
