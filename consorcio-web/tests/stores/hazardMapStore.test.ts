import { beforeEach, describe, expect, it } from 'vitest';

import { useHazardMapStore } from '../../src/stores/hazardMapStore';

describe('hazardMapStore', () => {
  beforeEach(() => {
    useHazardMapStore.setState({
      panelOpen: true,
      mobileExpanded: false,
      pendingBasinZoom: false,
    });
  });

  it('starts with the panel open, mobile collapsed, and no pending basin zoom', () => {
    const state = useHazardMapStore.getState();

    expect(state.panelOpen).toBe(true);
    expect(state.mobileExpanded).toBe(false);
    expect(state.pendingBasinZoom).toBe(false);
  });

  it('minimizes both hazard surfaces when a ficha opens', () => {
    useHazardMapStore.setState({ panelOpen: true, mobileExpanded: true });

    useHazardMapStore.getState().minimizeForFicha();

    expect(useHazardMapStore.getState()).toMatchObject({
      panelOpen: false,
      mobileExpanded: false,
    });
  });

  it('resets every ephemeral value to its defaults', () => {
    useHazardMapStore.setState({
      panelOpen: false,
      mobileExpanded: true,
      pendingBasinZoom: true,
    });

    useHazardMapStore.getState().reset();

    expect(useHazardMapStore.getState()).toMatchObject({
      panelOpen: true,
      mobileExpanded: false,
      pendingBasinZoom: false,
    });
  });

  it('does not persist hazard UI state to localStorage', () => {
    const keysBefore = Object.keys(localStorage).filter((key) =>
      key.toLowerCase().includes('hazardmap')
    );

    useHazardMapStore.getState().setPanelOpen(false);
    useHazardMapStore.getState().setMobileExpanded(true);

    const keysAfter = Object.keys(localStorage).filter((key) =>
      key.toLowerCase().includes('hazardmap')
    );
    expect(keysAfter).toEqual(keysBefore);
  });
});
