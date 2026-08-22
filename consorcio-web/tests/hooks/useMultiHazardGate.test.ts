import { describe, expect, it } from 'vitest';

import { canUseMultiHazardViewer } from '../../src/hooks/useMultiHazardGate';

describe('canUseMultiHazardViewer', () => {
  it.each(['admin', 'operador'])('allows %s when the feature flag is enabled', (role) => {
    expect(canUseMultiHazardViewer('true', role)).toBe(true);
  });

  it.each(['ciudadano', null, undefined, 'other'])('denies %s even when the feature flag is enabled', (role) => {
    expect(canUseMultiHazardViewer('1', role)).toBe(false);
  });

  it.each([undefined, false, 'false', '0'])('denies an operator when the feature flag is %s', (flag) => {
    expect(canUseMultiHazardViewer(flag, 'operador')).toBe(false);
  });
});
