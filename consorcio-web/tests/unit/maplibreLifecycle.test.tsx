import { render, waitFor } from '@testing-library/react';
import { StrictMode, useEffect, useRef } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { MAP_LOCALE_ES } from '../../src/components/map2d/mapLibreLocale';
import {
  createMapLibreMap,
  destroyMapLibreMap,
  isCoarsePointerDevice,
  resolveCooperativeGestures,
  swapMapStyle,
} from '../../src/lib/maplibreLifecycle';
import * as loader from '../../src/lib/maplibreLoader';

const EMPTY_STYLE = { version: 8 as const, sources: {}, layers: [] };

function stubPointerCoarse(coarse: boolean) {
  const original = window.matchMedia;
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: vi.fn((query: string) => ({
      matches: query.includes('pointer: coarse') ? coarse : false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
  return () => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      configurable: true,
      value: original,
    });
  };
}

interface CapturedMap {
  options: Record<string, unknown>;
  remove: ReturnType<typeof vi.fn>;
}

function createCapturingMap(bucket: CapturedMap[]) {
  class CapturingMap {
    readonly remove = vi.fn();
    constructor(options: Record<string, unknown>) {
      bucket.push({ options, remove: this.remove });
    }
  }
  return CapturingMap;
}

describe('maplibreLifecycle — gestures', () => {
  let restore: (() => void) | null = null;

  afterEach(() => {
    restore?.();
    restore = null;
  });

  it('keeps cooperative gestures on an embedded form even with a coarse pointer', async () => {
    restore = stubPointerCoarse(true);
    const built: CapturedMap[] = [];
    await createMapLibreMap({
      maplibre: { Map: createCapturingMap(built) as never },
      gestures: 'embedded-form',
      options: {
        container: document.createElement('div'),
        style: EMPTY_STYLE,
        center: [-62.3, -32.5],
        zoom: 12,
      },
    });
    expect(resolveCooperativeGestures('embedded-form')).toBe(true);
    expect(built[0]?.options.cooperativeGestures).toBe(true);
    expect(built[0]?.options.attributionControl).toEqual({ compact: true });
    expect(built[0]?.options.locale).toEqual({ ...MAP_LOCALE_ES });
  });

  it('turns cooperative gestures off on a primary surface with a coarse pointer', async () => {
    restore = stubPointerCoarse(true);
    const built: CapturedMap[] = [];
    await createMapLibreMap({
      maplibre: { Map: createCapturingMap(built) as never },
      gestures: 'primary-surface',
      options: {
        container: document.createElement('div'),
        style: EMPTY_STYLE,
        center: [-62.3, -32.5],
        zoom: 10,
        attributionControl: false,
      },
    });
    expect(isCoarsePointerDevice()).toBe(true);
    expect(resolveCooperativeGestures('primary-surface')).toBe(false);
    expect(built[0]?.options.cooperativeGestures).toBe(false);
    expect(built[0]?.options.attributionControl).toBe(false);
  });

  it('enables cooperative gestures on a primary surface with a fine pointer', () => {
    restore = stubPointerCoarse(false);
    expect(resolveCooperativeGestures('primary-surface')).toBe(true);
  });
});

describe('maplibreLifecycle — destroy and style swap', () => {
  it('removes a map once even if destroy runs twice', () => {
    const remove = vi.fn();
    const map = { remove };
    destroyMapLibreMap(map);
    destroyMapLibreMap(map);
    expect(remove).toHaveBeenCalledTimes(1);
  });

  it('swallows a second remove that throws and ignores null', () => {
    const remove = vi.fn(() => {
      throw new Error('already removed');
    });
    const map = { remove };
    expect(() => destroyMapLibreMap(map)).not.toThrow();
    expect(() => destroyMapLibreMap(map)).not.toThrow();
    expect(remove).toHaveBeenCalledTimes(1);
    expect(() => destroyMapLibreMap(null)).not.toThrow();
    expect(() => destroyMapLibreMap(undefined)).not.toThrow();
  });

  it('resolves swapMapStyle on style.load and abandons it if the map is destroyed', async () => {
    const listeners = new Set<() => void>();
    const map = {
      setStyle: vi.fn(() => {
        for (const listener of listeners) listener();
      }),
      once: (_type: string, listener: () => void) => {
        listeners.add(listener);
      },
      off: (_type: string, listener: () => void) => {
        listeners.delete(listener);
      },
      remove: vi.fn(),
    };
    await expect(swapMapStyle(map as never, EMPTY_STYLE)).resolves.toBeUndefined();
    expect(map.setStyle).toHaveBeenCalledWith(EMPTY_STYLE, undefined);

    const hanging = {
      setStyle: vi.fn(),
      once: (_type: string, listener: () => void) => {
        listeners.add(listener);
      },
      off: vi.fn(),
      remove: vi.fn(),
    };
    const pending = swapMapStyle(hanging as never, EMPTY_STYLE);
    destroyMapLibreMap(hanging);
    await expect(pending).resolves.toBeUndefined();
    destroyMapLibreMap(hanging);
    expect(hanging.remove).toHaveBeenCalledTimes(1);
  });

  it('rejects when setStyle throws and still destroys once', async () => {
    const map = {
      setStyle: vi.fn(() => {
        throw new Error('estilo inválido');
      }),
      once: vi.fn(),
      off: vi.fn(),
      remove: vi.fn(),
    };
    await expect(swapMapStyle(map as never, EMPTY_STYLE)).rejects.toThrow('estilo inválido');
    destroyMapLibreMap(map);
    destroyMapLibreMap(map);
    expect(map.remove).toHaveBeenCalledTimes(1);
  });
});

describe('maplibreLifecycle — worker policy', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('skips new Map when the signal aborts during worker boot', async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const spy = vi.spyOn(loader, 'bootMapLibreWorker').mockImplementation(() => gate);
    const Map = vi.fn(function Map() {
      return { remove: vi.fn() };
    });
    const abort = new AbortController();
    const pending = createMapLibreMap({
      maplibre: { Map: Map as never },
      gestures: 'embedded-form',
      signal: abort.signal,
      options: {
        container: document.createElement('div'),
        style: EMPTY_STYLE,
        center: [-62.3, -32.5],
        zoom: 10,
      },
    });
    abort.abort();
    release();
    await expect(pending).resolves.toBeNull();
    expect(Map).not.toHaveBeenCalled();
    spy.mockRestore();
  });

  it('sends every create through the same worker boot promise', async () => {
    const spy = vi.spyOn(loader, 'bootMapLibreWorker');
    const Map = vi.fn(function Map() {
      return { remove() {} };
    });
    const options = {
      container: document.createElement('div'),
      style: EMPTY_STYLE,
      center: [-62.3, -32.5] as [number, number],
      zoom: 10,
    };
    await Promise.all([
      createMapLibreMap({
        maplibre: { Map: Map as never },
        gestures: 'embedded-form',
        options,
      }),
      createMapLibreMap({
        maplibre: { Map: Map as never },
        gestures: 'primary-surface',
        options,
      }),
    ]);
    expect(spy).toHaveBeenCalledTimes(2);
    expect(spy.mock.results[0]?.value).toBe(spy.mock.results[1]?.value);
    expect(spy.mock.results[0]?.value).toBeInstanceOf(Promise);
  });
});

describe('maplibreLifecycle — mount and unmount', () => {
  const maps: Array<{ remove: ReturnType<typeof vi.fn> }> = [];

  class HostMap {
    readonly remove = vi.fn();
    constructor() {
      maps.push(this);
    }
  }

  afterEach(() => {
    maps.length = 0;
  });

  function Host() {
    const ref = useRef<HTMLDivElement>(null);
    useEffect(() => {
      const container = ref.current;
      if (!container) return;
      let cancelled = false;
      let map: HostMap | undefined;
      void (async () => {
        const created = await createMapLibreMap({
          maplibre: { Map: HostMap as never },
          gestures: 'embedded-form',
          options: {
            container,
            style: EMPTY_STYLE,
            center: [-62.3, -32.5],
            zoom: 11,
          },
        });
        if (cancelled) {
          destroyMapLibreMap(created);
          return;
        }
        map = created as unknown as HostMap;
      })();
      return () => {
        cancelled = true;
        destroyMapLibreMap(map);
      };
    }, []);
    return <div ref={ref} />;
  }

  it('destroys each map once under StrictMode and on unmount', async () => {
    const view = render(
      <StrictMode>
        <Host />
      </StrictMode>
    );
    await waitFor(() => expect(maps.length).toBeGreaterThan(0));
    view.unmount();
    await waitFor(() => {
      expect(maps.length).toBeGreaterThan(0);
      for (const map of maps) {
        expect(map.remove).toHaveBeenCalledTimes(1);
      }
    });
  });
});
