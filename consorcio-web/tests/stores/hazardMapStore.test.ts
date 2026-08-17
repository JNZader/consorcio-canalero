/**
 * hazardMapStore.test.ts
 *
 * Locks the ephemeral Multi-Hazard UI store: reset behavior, ficha minimization,
 * and the absence of persistence.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { useHazardMapStore } from '../../src/stores/hazardMapStore';

describe('hazardMapStore', () => {
  beforeEach(() => {
    useHazardMapStore.setState({
      panelOpen: true,
      mobileExpanded: false,
      pendingBasinZoom: false,
    });
  });

  it('starts with panel open, mobile collapsed, and no pending zoom', () => {
    const state = useHazardMapStore.getState();

    expect(state.panelOpen).toBe(true);
    expect(state.mobileExpanded).toBe(false);
    expect(state.pendingBasinZoom).toBe(false);
  });

  it('setPanelOpen toggles the desktop panel', () => {
    useHazardMapStore.getState().setPanelOpen(false);
    expect(useHazardMapStore.getState().panelOpen).toBe(false);

    useHazardMapStore.getState().setPanelOpen(true);
    expect(useHazardMapStore.getState().panelOpen).toBe(true);
  });

  it('setMobileExpanded toggles the mobile sheet', () => {
    useHazardMapStore.getState().setMobileExpanded(true);
    expect(useHazardMapStore.getState().mobileExpanded).toBe(true);

    useHazardMapStore.getState().setMobileExpanded(false);
    expect(useHazardMapStore.getState().mobileExpanded).toBe(false);
  });

  it('setPendingBasinZoom tracks basin flyTo state', () => {
    useHazardMapStore.getState().setPendingBasinZoom(true);
    expect(useHazardMapStore.getState().pendingBasinZoom).toBe(true);

    useHazardMapStore.getState().setPendingBasinZoom(false);
    expect(useHazardMapStore.getState().pendingBasinZoom).toBe(false);
  });

  it('minimizeForFicha collapses both desktop panel and mobile sheet', () => {
    useHazardMapStore.setState({ panelOpen: true, mobileExpanded: true });

    useHazardMapStore.getState().minimizeForFicha();

    const state = useHazardMapStore.getState();
    expect(state.panelOpen).toBe(false);
    expect(state.mobileExpanded).toBe(false);
  });

  it('reset restores defaults without persisting anything', () => {
    useHazardMapStore.setState({ panelOpen: false, mobileExpanded: true, pendingBasinZoom: true });

    useHazardMapStore.getState().reset();

    const state = useHazardMapStore.getState();
    expect(state.panelOpen).toBe(true);
    expect(state.mobileExpanded).toBe(false);
    expect(state.pendingBasinZoom).toBe(false);
  });

  it('does not create a localStorage key', () => {
    const keyPrefix = 'hazardMap';
    const before = Object.keys(localStorage).filter((k) => k.toLowerCase().includes(keyPrefix.toLowerCase()));

    // Trigger a state change to exercise any potential persistence side effect.
    useHazardMapStore.getState().setPanelOpen(false);
    useHazardMapStore.getState().reset();

    const after = Object.keys(localStorage).filter((k) => k.toLowerCase().includes(keyPrefix.toLowerCase()));
    expect(after).toEqual(before);
  });
});
