/**
 * useLayerHealth — trivial React wrapper over the pure `buildLayerHealth`.
 *
 * Deliberately memo-free: the React Compiler is active in this project, so a
 * manual `useMemo` here would be noise (see the convention note in
 * `LayerControlsPanel.tsx`). Keeping the derivation pure and outside React also
 * lets `layerHealth.test.ts` exercise every rule without rendering anything.
 */

import { buildLayerHealth, type LayerHealth, type LayerHealthInputs } from './layerHealth';

export function useLayerHealth(inputs: LayerHealthInputs): LayerHealth {
  return buildLayerHealth(inputs);
}
