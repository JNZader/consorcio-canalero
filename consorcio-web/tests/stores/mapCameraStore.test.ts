import { beforeEach, describe, expect, it } from 'vitest';

import { useMapCameraStore } from '../../src/stores/mapCameraStore';

describe('mapCameraStore', () => {
  beforeEach(() => {
    useMapCameraStore.setState({ camera: null });
  });

  it('starts empty so first viewer uses its own default', () => {
    expect(useMapCameraStore.getState().camera).toBeNull();
  });

  it('keeps the last 2D/3D camera for the other viewer', () => {
    useMapCameraStore.getState().setCamera({
      lng: -62.68,
      lat: -32.63,
      zoom: 13,
      bearing: 10,
      pitch: 45,
    });
    expect(useMapCameraStore.getState().camera).toEqual({
      lng: -62.68,
      lat: -32.63,
      zoom: 13,
      bearing: 10,
      pitch: 45,
    });
  });
});
