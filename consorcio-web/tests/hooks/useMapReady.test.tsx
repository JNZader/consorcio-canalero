import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { MapReadyHandler, useMapReady } from '../../src/hooks/useMapReady';

describe('useMapReady', () => {
  it('returns null to preserve legacy API compatibility', () => {
    expect(useMapReady()).toBeNull();
  });

  it('keeps MapReadyHandler as a no-op component', () => {
    const { container } = render(<MapReadyHandler />);
    expect(container.firstChild).toBeNull();
  });

  it('can be invoked repeatedly without side effects', () => {
    expect(useMapReady()).toBeNull();
    expect(useMapReady()).toBeNull();
  });
});
