import { act, cleanup, render, renderHook } from '@testing-library/react';
import { createElement, StrictMode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  DRAWER_HISTORY_MARKER,
  useDrawerHistoryClose,
} from '../../src/hooks/useDrawerHistoryClose';

/**
 * AUD-005 — Back must dismiss the mobile layers Drawer instead of leaving the
 * page. `history.back()` is stubbed everywhere: the real one is asynchronous
 * and would make these assertions racy. What matters is WHETHER the hook
 * rewinds, not that the environment implements the rewind.
 */
describe('useDrawerHistoryClose', () => {
  let backSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    window.history.replaceState(null, '');
    backSpy = vi.spyOn(window.history, 'back').mockImplementation(() => {});
  });

  afterEach(async () => {
    cleanup();
    await Promise.resolve();
    vi.restoreAllMocks();
  });

  function markerIsOnTop() {
    const state = window.history.state as Record<string, unknown> | null;
    return Boolean(state && state[DRAWER_HISTORY_MARKER] === true);
  }

  it('pushes a marker entry when the drawer opens', () => {
    const onClose = vi.fn();
    const { rerender } = renderHook(
      ({ opened }: { opened: boolean }) => useDrawerHistoryClose({ opened, onClose }),
      { initialProps: { opened: false } },
    );

    expect(markerIsOnTop()).toBe(false);

    rerender({ opened: true });

    expect(markerIsOnTop()).toBe(true);
    expect(onClose).not.toHaveBeenCalled();
  });

  it('closes the drawer on popstate WITHOUT rewinding again', () => {
    const onClose = vi.fn();
    renderHook(() => useDrawerHistoryClose({ opened: true, onClose }));

    // The browser already consumed the marker entry before firing popstate.
    act(() => {
      window.history.replaceState(null, '');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(backSpy).not.toHaveBeenCalled();
  });

  it('rewinds the marker when the drawer closes by other means', async () => {
    const onClose = vi.fn();
    const { rerender } = renderHook(
      ({ opened }: { opened: boolean }) => useDrawerHistoryClose({ opened, onClose }),
      { initialProps: { opened: true } },
    );

    expect(markerIsOnTop()).toBe(true);

    rerender({ opened: false });
    await Promise.resolve();

    expect(backSpy).toHaveBeenCalledTimes(1);
    expect(onClose).not.toHaveBeenCalled();
  });

  it('does NOT rewind when a real navigation landed on top of the marker', async () => {
    const onClose = vi.fn();
    const { rerender } = renderHook(
      ({ opened }: { opened: boolean }) => useDrawerHistoryClose({ opened, onClose }),
      { initialProps: { opened: true } },
    );

    // A router navigation while the drawer was open.
    act(() => {
      window.history.pushState({ router: 'somewhere-else' }, '');
    });

    rerender({ opened: false });
    await Promise.resolve();

    expect(backSpy).not.toHaveBeenCalled();
  });

  it('rewinds the marker when the component unmounts with the drawer open', async () => {
    const { unmount } = renderHook(() => useDrawerHistoryClose({ opened: true, onClose: vi.fn() }));

    unmount();
    await Promise.resolve();

    expect(backSpy).toHaveBeenCalledTimes(1);
  });

  it('never touches history while disabled (desktop layout)', async () => {
    const onClose = vi.fn();
    const pushSpy = vi.spyOn(window.history, 'pushState');
    const { rerender, unmount } = renderHook(
      ({ opened }: { opened: boolean }) =>
        useDrawerHistoryClose({ opened, onClose, enabled: false }),
      { initialProps: { opened: false } },
    );

    rerender({ opened: true });
    act(() => {
      window.dispatchEvent(new PopStateEvent('popstate'));
    });
    rerender({ opened: false });
    unmount();
    await Promise.resolve();

    expect(pushSpy).not.toHaveBeenCalled();
    expect(backSpy).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
  });

  it('pushes only ONE marker across re-renders while it stays open', () => {
    const pushSpy = vi.spyOn(window.history, 'pushState');
    const { rerender } = renderHook(
      ({ opened }: { opened: boolean }) =>
        // A fresh `onClose` identity per render — the effect must not re-run.
        useDrawerHistoryClose({ opened, onClose: () => {} }),
      { initialProps: { opened: true } },
    );

    rerender({ opened: true });
    rerender({ opened: true });

    expect(pushSpy).toHaveBeenCalledTimes(1);
  });

  it('stops listening after unmount so a later popstate cannot close a dead drawer', () => {
    const onClose = vi.fn();
    const { unmount } = renderHook(() => useDrawerHistoryClose({ opened: true, onClose }));

    unmount();
    act(() => {
      window.dispatchEvent(new PopStateEvent('popstate'));
    });

    expect(onClose).not.toHaveBeenCalled();
  });

  it('re-arms the marker when the drawer is opened a second time', () => {
    const onClose = vi.fn();
    const { rerender } = renderHook(
      ({ opened }: { opened: boolean }) => useDrawerHistoryClose({ opened, onClose }),
      { initialProps: { opened: true } },
    );

    rerender({ opened: false });
    window.history.replaceState(null, '');
    rerender({ opened: true });

    expect(markerIsOnTop()).toBe(true);

    act(() => {
      window.history.replaceState(null, '');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('ignores synthetic popstate events while its own marker entry is still on top', () => {
    const onClose = vi.fn();
    renderHook(() => useDrawerHistoryClose({ opened: true, onClose }));

    expect(markerIsOnTop()).toBe(true);
    act(() => {
      window.dispatchEvent(new PopStateEvent('popstate'));
    });

    expect(onClose).not.toHaveBeenCalled();
  });

  it('does not rewind a sibling drawer marker on unmount (#740)', async () => {
    const first = renderHook(() => useDrawerHistoryClose({ opened: true, onClose: vi.fn() }));
    const second = renderHook(() => useDrawerHistoryClose({ opened: true, onClose: vi.fn() }));

    first.unmount();
    await Promise.resolve();
    expect(backSpy).not.toHaveBeenCalled();

    second.unmount();
    await Promise.resolve();
    expect(backSpy).toHaveBeenCalledTimes(1);
  });

  it('coalesces StrictMode mount-cleanup-remount without calling history.back()', async () => {
    const pushSpy = vi.spyOn(window.history, 'pushState');
    const onClose = vi.fn();

    function Harness() {
      useDrawerHistoryClose({ opened: true, onClose });
      return null;
    }

    render(createElement(StrictMode, null, createElement(Harness)));
    await Promise.resolve();

    expect(pushSpy).toHaveBeenCalledTimes(1);
    expect(backSpy).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
    expect(markerIsOnTop()).toBe(true);

    // Real user Back still dismisses the drawer once.
    act(() => {
      window.history.replaceState(null, '');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('keeps a lower nested drawer open when the upper drawer pops', () => {
    const lowerClose = vi.fn();
    const upperClose = vi.fn();

    renderHook(() => useDrawerHistoryClose({ opened: true, onClose: lowerClose }));
    const lowerState = window.history.state as Record<string, unknown>;

    renderHook(() => useDrawerHistoryClose({ opened: true, onClose: upperClose }));

    // Popping from upper back to lower closes ONLY the upper drawer.
    act(() => {
      window.history.replaceState(lowerState, '');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });

    expect(upperClose).toHaveBeenCalledTimes(1);
    expect(lowerClose).not.toHaveBeenCalled();

    // Popping once more exits the lower drawer.
    act(() => {
      window.history.replaceState(null, '');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });

    expect(lowerClose).toHaveBeenCalledTimes(1);
  });
});
