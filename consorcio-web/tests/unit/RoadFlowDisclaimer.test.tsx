/**
 * RoadFlowDisclaimer.test.tsx — flujo-caminos S4, task 4.6.
 *
 * RFA-R4 requires the non-hydraulic disclaimer be readable WITHOUT operating a
 * disclosure control, wherever the result is read. This suite asserts the
 * COMPONENT's own contract, structurally, in the rendered DOM:
 *
 *   - the exact copy is present, in every surface;
 *   - it is NOT inside a `CollapsibleSection`, whose body unmounts when closed;
 *   - the floating chip is a plain box with nothing to operate.
 *
 * ⚠️ WHERE IT IS MOUNTED IS ASSERTED ELSEWHERE, ON PURPOSE. ⚠️
 * The "it is present on every surface" claim lives in
 * `tests/unit/roadFlowWiring.test.tsx`, against the REAL call sites (panel
 * open, panel minimized with the layer on, survey sheet open on a narrow
 * viewport). A test that mounts two instances itself proves only that the
 * component can be mounted twice — it would stay green with nothing rendering
 * it at all, which is the failure the owner ratification of 2026-08-23 closed.
 *
 * A docstring, a help page or a tooltip cannot satisfy any of these. That is
 * the whole point: the requirement is about what an operator SEES, and a test
 * that reads source text instead of the DOM would pass on a comment.
 */

import { MantineProvider } from '@mantine/core';
import { render, screen, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import {
  ROAD_FLOW_DISCLAIMER_CHIP_TEST_ID,
  ROAD_FLOW_DISCLAIMER_TEST_ID,
  ROAD_FLOW_DISCLAIMER_TEXT,
  RoadFlowDisclaimer,
  RoadFlowDisclaimerChip,
} from '../../src/components/map2d/RoadFlowDisclaimer';

function renderWithMantine(ui: ReactNode) {
  return render(<MantineProvider env="test">{ui}</MantineProvider>);
}

/** The copy, spelled out here rather than imported, so a silent edit is caught. */
const EXPECTED =
  'Indica hacia dónde va el agua, no cuánta ni con qué fuerza. ' +
  'El orden es relativo entre los puntos mostrados, no una medición hidráulica.';

/** Collapse the DOM's text to compare across the `<strong>` around "hacia dónde". */
function flatten(text: string | null): string {
  return (text ?? '').replace(/\s+/g, ' ').trim();
}

describe('RoadFlowDisclaimer', () => {
  it('renders the EXACT copy the spec names', () => {
    renderWithMantine(<RoadFlowDisclaimer surface="lista" />);
    const node = screen.getByTestId(`${ROAD_FLOW_DISCLAIMER_TEST_ID}-lista`);
    expect(flatten(node.textContent)).toBe(EXPECTED);
  });

  it('the exported constant matches what is rendered (no second copy)', () => {
    expect(flatten(ROAD_FLOW_DISCLAIMER_TEXT)).toBe(EXPECTED);
  });

  it('emphasises "hacia dónde" — the whole distinction the sentence makes', () => {
    renderWithMantine(<RoadFlowDisclaimer surface="lista" />);
    const node = screen.getByTestId(`${ROAD_FLOW_DISCLAIMER_TEST_ID}-lista`);
    expect(within(node).getByText('hacia dónde')).toBeTruthy();
  });

  it('renders the SAME sentence in every surface — one string, no copies', () => {
    for (const surface of ['lista', 'hoja', 'chip'] as const) {
      const { unmount } = renderWithMantine(<RoadFlowDisclaimer surface={surface} />);
      const node = screen.getByTestId(`${ROAD_FLOW_DISCLAIMER_TEST_ID}-${surface}`);
      expect(flatten(node.textContent)).toBe(EXPECTED);
      unmount();
    }
  });

  it('is NOT inside any disclosure control — no fold, no toggle, no summary', () => {
    const { container } = renderWithMantine(<RoadFlowDisclaimer surface="lista" />);
    const node = screen.getByTestId(`${ROAD_FLOW_DISCLAIMER_TEST_ID}-lista`);

    // Nothing to open: no <details>, no expand/collapse button, no aria-expanded
    // ancestor anywhere between the disclaimer and the root.
    expect(container.querySelector('details')).toBeNull();
    expect(container.querySelector('button')).toBeNull();
    expect(container.querySelector('[aria-expanded]')).toBeNull();

    let ancestor: HTMLElement | null = node.parentElement;
    while (ancestor && ancestor !== container) {
      expect(ancestor.getAttribute('aria-expanded')).toBeNull();
      expect(ancestor.tagName.toLowerCase()).not.toBe('details');
      expect(ancestor.tagName.toLowerCase()).not.toBe('summary');
      ancestor = ancestor.parentElement;
    }
  });

  it('is visible immediately: no hidden attribute, no display:none', () => {
    renderWithMantine(<RoadFlowDisclaimer surface="hoja" />);
    const node = screen.getByTestId(`${ROAD_FLOW_DISCLAIMER_TEST_ID}-hoja`);
    expect(node.hasAttribute('hidden')).toBe(false);
    expect(node.getAttribute('aria-hidden')).toBeNull();
    expect(node.style.display).not.toBe('none');
  });
});

describe('RoadFlowDisclaimerChip — the floating minimum', () => {
  it('carries the WHOLE sentence, not an abbreviation of it', () => {
    renderWithMantine(<RoadFlowDisclaimerChip />);
    const host = screen.getByTestId(ROAD_FLOW_DISCLAIMER_CHIP_TEST_ID);
    expect(flatten(host.textContent)).toBe(EXPECTED);
    expect(within(host).getByTestId(`${ROAD_FLOW_DISCLAIMER_TEST_ID}-chip`)).toBeTruthy();
  });

  it('has nothing to operate — no dismiss, no fold, no link', () => {
    const { container } = renderWithMantine(<RoadFlowDisclaimerChip />);
    expect(container.querySelector('button')).toBeNull();
    expect(container.querySelector('a')).toBeNull();
    expect(container.querySelector('[aria-expanded]')).toBeNull();
    expect(container.querySelector('details')).toBeNull();
  });
});
