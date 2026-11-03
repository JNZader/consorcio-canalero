import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { CoordinatesInput, LiveRegionProvider } from '../../src/components/ui/accessibility';

describe('<CoordinatesInput /> valid aria-describedby targets (A11Y-05)', () => {
  it('resolves both lat-format-help and lng-format-help aria-describedby IDs to existing DOM nodes', () => {
    render(
      <MantineProvider env="test">
        <LiveRegionProvider>
          <CoordinatesInput onCoordinatesChange={vi.fn()} />
        </LiveRegionProvider>
      </MantineProvider>
    );

    const latInput = screen.getByLabelText(/latitud/i);
    const lngInput = screen.getByLabelText(/longitud/i);

    const latHelpId = latInput.getAttribute('aria-describedby');
    const lngHelpId = lngInput.getAttribute('aria-describedby');

    expect(latHelpId).toBe('lat-format-help');
    expect(lngHelpId).toBe('lng-format-help');
    expect(document.getElementById(latHelpId!)).toBeInTheDocument();
    expect(document.getElementById(lngHelpId!)).toBeInTheDocument();
  });
});
