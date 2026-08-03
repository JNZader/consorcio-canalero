/**
 * DrawControlReplaceSemantics.test.tsx — T3c final round, R2-001.
 *
 * The "Otro" toolbar button re-enters `draw_polygon` through
 * `DrawControlHandle.startDrawing`. It used to ONLY `changeMode`, so polygon A
 * stayed rendered on the map while the ficha analysed polygon B, and "Borrar"
 * then wiped both at once.
 *
 * The contract pinned here:
 *   - `startDrawing` deletes the existing feature(s) BEFORE switching mode →
 *     the map holds exactly ONE polygon after a redraw.
 *   - that delete is SILENT: MapboxDraw's programmatic `deleteAll()` emits no
 *     `draw.delete`, and `startDrawing` does not call `onPolygonDeleted` by
 *     hand either, so the ficha state survives until the new polygon completes
 *     (`draw.create` → `onPolygonCreated`).
 *   - `clearDrawing` keeps the OPPOSITE behaviour: it deletes AND notifies.
 */

import { render } from '@testing-library/react';
import { createRef } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// ── MapboxDraw double: a tiny in-memory feature store ───────────────────────
const drawState: {
  features: Array<{
    id: string;
    geometry: { type: string; coordinates: number[][][] };
  }>;
  mode: string;
  calls: string[];
} = { features: [], mode: 'simple_select', calls: [] };

vi.mock('@mapbox/mapbox-gl-draw', () => {
  class MapboxDrawMock {
    getAll() {
      return { type: 'FeatureCollection', features: drawState.features };
    }
    deleteAll() {
      drawState.calls.push('deleteAll');
      drawState.features = [];
      // Deliberately emits NO event — this mirrors the real programmatic API
      // and is exactly why `clearDrawing` has to notify by hand.
      return this;
    }
    delete(ids: string[]) {
      drawState.features = drawState.features.filter((f) => !ids.includes(f.id));
      return this;
    }
    changeMode(mode: string) {
      drawState.calls.push(`changeMode:${mode}`);
      drawState.mode = mode;
      return this;
    }
    onAdd() {
      return document.createElement('div');
    }
    onRemove() {}
  }
  return { default: MapboxDrawMock };
});

vi.mock('@/components/map/mapboxDrawCompatibility', () => ({
  ensureMapboxDrawCompatibility: () => {},
}));
vi.mock('@/components/map/mapboxDrawShared', () => ({
  removeMapboxDrawArtifacts: () => {},
}));

import DrawControl, { type DrawControlHandle } from '@/components/map/DrawControl';

function createFakeMap() {
  const handlers = new Map<string, Array<(...args: unknown[]) => void>>();
  return {
    handlers,
    on(event: string, cb: (...args: unknown[]) => void) {
      const list = handlers.get(event) ?? [];
      list.push(cb);
      handlers.set(event, list);
    },
    off() {},
    addControl() {},
    removeControl() {},
    hasControl() {
      return false;
    },
    emit(event: string) {
      for (const cb of handlers.get(event) ?? []) cb();
    },
  };
}

function polygon(id: string) {
  return {
    id,
    geometry: {
      type: 'Polygon',
      coordinates: [
        [
          [0, 0],
          [1, 0],
          [1, 1],
          [0, 0],
        ],
      ],
    },
  };
}

beforeEach(() => {
  drawState.features = [];
  drawState.mode = 'simple_select';
  drawState.calls = [];
});

describe('DrawControl — redraw replaces instead of accumulating (R2-001)', () => {
  it('wipes the previous polygon BEFORE re-entering draw_polygon', () => {
    const ref = createRef<DrawControlHandle>();
    const map = createFakeMap();
    render(
      <DrawControl
        ref={ref}
        // biome-ignore lint/suspicious/noExplicitAny: minimal map double
        map={map as any}
        onPolygonCreated={() => {}}
        onPolygonDeleted={() => {}}
      />
    );

    drawState.features = [polygon('A')];
    ref.current?.startDrawing();

    // Order matters: deleting AFTER changeMode would wipe the in-progress draw.
    expect(drawState.calls).toEqual(['deleteAll', 'changeMode:draw_polygon']);
    expect(drawState.features).toHaveLength(0);
  });

  it('leaves exactly ONE polygon on the map after a redraw completes', () => {
    const ref = createRef<DrawControlHandle>();
    const map = createFakeMap();
    render(
      <DrawControl
        ref={ref}
        // biome-ignore lint/suspicious/noExplicitAny: minimal map double
        map={map as any}
        onPolygonCreated={() => {}}
        onPolygonDeleted={() => {}}
      />
    );

    drawState.features = [polygon('A')];
    ref.current?.startDrawing();
    drawState.features = [polygon('B')];
    map.emit('draw.create');

    expect(drawState.features.map((f) => f.id)).toEqual(['B']);
  });

  it('does NOT clear the ficha while redrawing (silent delete)', () => {
    const onPolygonDeleted = vi.fn();
    const onPolygonCreated = vi.fn();
    const ref = createRef<DrawControlHandle>();
    const map = createFakeMap();
    render(
      <DrawControl
        ref={ref}
        // biome-ignore lint/suspicious/noExplicitAny: minimal map double
        map={map as any}
        onPolygonCreated={onPolygonCreated}
        onPolygonDeleted={onPolygonDeleted}
      />
    );

    drawState.features = [polygon('A')];
    ref.current?.startDrawing();

    // Nothing told the ficha to drop its result mid-draw…
    expect(onPolygonDeleted).not.toHaveBeenCalled();
    expect(onPolygonCreated).not.toHaveBeenCalled();

    // …the replacement lands only when the new polygon completes.
    drawState.features = [polygon('B')];
    map.emit('draw.create');
    expect(onPolygonCreated).toHaveBeenCalledTimes(1);
    expect(onPolygonDeleted).not.toHaveBeenCalled();
  });

  it('clearDrawing still deletes AND notifies (the "Borrar" button)', () => {
    const onPolygonDeleted = vi.fn();
    const ref = createRef<DrawControlHandle>();
    const map = createFakeMap();
    render(
      <DrawControl
        ref={ref}
        // biome-ignore lint/suspicious/noExplicitAny: minimal map double
        map={map as any}
        onPolygonCreated={() => {}}
        onPolygonDeleted={onPolygonDeleted}
      />
    );

    drawState.features = [polygon('A')];
    ref.current?.clearDrawing();

    expect(drawState.features).toHaveLength(0);
    expect(onPolygonDeleted).toHaveBeenCalledTimes(1);
  });
});
