import { beforeEach, describe, expect, it } from 'vitest';

import { useReportAnchorStore } from '../../src/stores/reportAnchorStore';

describe('reportAnchorStore', () => {
  beforeEach(() => {
    useReportAnchorStore.setState({ anchor: null, geolocatePin: null });
  });

  it('starts with no anchor and no geolocate pin', () => {
    expect(useReportAnchorStore.getState().anchor).toBeNull();
    expect(useReportAnchorStore.getState().geolocatePin).toBeNull();
  });

  it('sets and clears the report anchor chosen on the map', () => {
    useReportAnchorStore.getState().setAnchor({ lat: -32.63, lng: -62.688 });
    expect(useReportAnchorStore.getState().anchor).toEqual({ lat: -32.63, lng: -62.688 });

    useReportAnchorStore.getState().setAnchor(null);
    expect(useReportAnchorStore.getState().anchor).toBeNull();
  });

  it('sets and clears the geolocate pin independently of the anchor', () => {
    useReportAnchorStore.getState().setGeolocatePin({ lat: -32.63, lng: -62.688 });
    expect(useReportAnchorStore.getState().geolocatePin).toEqual({ lat: -32.63, lng: -62.688 });
    expect(useReportAnchorStore.getState().anchor).toBeNull();

    useReportAnchorStore.getState().setGeolocatePin(null);
    expect(useReportAnchorStore.getState().geolocatePin).toBeNull();
  });
});
