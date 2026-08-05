/**
 * TerrainViewer3DNoJargonAlert.test.ts
 *
 * NEGATIVE CONTRACT — the public 3D view must not surface the "Subcuencas GEE no
 * disponibles en el mapa publico" Alert (owner request 2026-08-04).
 *
 * The banner named internal machinery ("subcuencas GEE", "superficie publica
 * permitida") at an ANONYMOUS visitor, who has no way to act on it and no idea
 * what a GEE sub-basin is. It also advertised the existence of layers the public
 * view deliberately withholds. `useGEELayers` still filters them out — that is a
 * security boundary and is NOT what was removed; only the disclosure went.
 *
 * Why a source-text contract and not a render: `TerrainViewer3D` mounts a WebGL
 * scene, so a rendering assertion here would need the whole 3D stack stood up
 * just to prove a string is absent. Absence is exactly what source text proves
 * cheaply and without flake — the same technique `mapDockSheetClearance` and
 * `MapPanelBottomSheet` use for contracts the DOM cannot show.
 *
 * This is a REGRESSION GUARD, not a style rule: the Alert is one destructure and
 * six JSX lines away from coming back, and nothing else would fail if it did.
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const VIEWER = readFileSync(
  resolve(process.cwd(), 'src/components/terrain/TerrainViewer3D.tsx'),
  'utf-8'
);

const HOOK = readFileSync(resolve(process.cwd(), 'src/hooks/useGEELayers.ts'), 'utf-8');

/**
 * The file with comments removed.
 *
 * LOAD-BEARING. The removal left a comment explaining what used to be here, and
 * that comment quotes the banner verbatim — so a raw `not.toContain('Subcuencas
 * GEE')` fails against PROSE while the UI is perfectly clean. What this contract
 * is about is what ships to the visitor, which is code, not commentary.
 */
const VIEWER_CODE = VIEWER.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '');

describe('TerrainViewer3D does not leak GEE jargon to public visitors', () => {
  it('renders no "Subcuencas GEE no disponibles" banner', () => {
    expect(VIEWER_CODE).not.toContain('Subcuencas GEE');
    expect(VIEWER_CODE).not.toContain('superficie publica permitida');
    expect(VIEWER_CODE).not.toMatch(/no disponibles en el mapa publico/i);
  });

  it('does not even read the unavailable-layer list off the hook', () => {
    // The disclosure cannot come back by accident while this name is unused: the
    // banner needed it, and nothing else in the viewer does.
    expect(VIEWER_CODE).not.toContain('unavailableLayers');
    expect(VIEWER_CODE).not.toContain('unavailableGeeLayers');
  });

  it('the comment-stripping itself works (guards this suite against a false pass)', () => {
    // If the regex ever stopped stripping, every negative assertion above would
    // start failing loudly rather than silently — but if it stripped too much
    // (e.g. ate the whole file) they would all pass vacuously. Pin both ends.
    expect(VIEWER_CODE).toContain('useGEELayers');
    expect(VIEWER_CODE.length).toBeGreaterThan(VIEWER.length / 2);
    expect(VIEWER).toContain('Subcuencas GEE'); // still present, in prose only
  });

  it('still FILTERS the non-public layers — only the disclosure was removed', () => {
    // The load-bearing half. If a refactor ever "simplified" the filtering away
    // along with the banner, the public view would start serving the very layers
    // this boundary exists to withhold, and the test above would still pass.
    expect(HOOK).toContain('unavailableLayers');
    expect(HOOK).toMatch(/filter\(\(name\) => !isPublicGEELayerName\(name\)\)/);
    // …and the viewer is still wired to the filtered accessor.
    expect(VIEWER).toMatch(/const \{ layers: geeLayers \} = useGEELayers\(/);
  });

  it('keeps the genuinely actionable alerts (DEM missing, terrain error)', () => {
    // Scope check: this contract removes ONE banner, not the component's ability
    // to report real failures the visitor can act on.
    expect(VIEWER).toContain('Sin capa DEM');
    expect(VIEWER).toContain('Error cargando terreno 3D');
  });
});
