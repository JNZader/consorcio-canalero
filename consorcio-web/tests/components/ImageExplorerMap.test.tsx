import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import { createRef, type ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import {
  EXPLORER_WORKSPACE_MIN_HEIGHT,
  ImageExplorerMap,
} from '../../src/components/admin/images/ImageExplorerMap';

function wrapper({ children }: { children: ReactNode }) {
  return <MantineProvider env="test">{children}</MantineProvider>;
}

describe('ImageExplorerMap fill', () => {
  it('fills the card instead of a clamped viewport strip', () => {
    const mapRef = createRef<HTMLDivElement>();
    render(
      <ImageExplorerMap
        mapRef={mapRef}
        loading={false}
        resultExists
        error={null}
        onFitZona={() => {}}
      />,
      { wrapper },
    );
    const canvas = screen.getByTestId('explorer-map-canvas');
    expect(canvas.style.position).toBe('absolute');
    expect(canvas.style.height).toBe('100%');
    expect(canvas.style.width).toBe('100%');
    expect(canvas.style.height).not.toContain('clamp');
  });

  it('keeps a viewport-tall workspace so the right column has room to grow', () => {
    expect(EXPLORER_WORKSPACE_MIN_HEIGHT).toContain('100dvh');
    expect(EXPLORER_WORKSPACE_MIN_HEIGHT).not.toContain('420px');
  });
});
