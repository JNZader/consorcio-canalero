import { describe, expect, it } from 'vitest';
import {
  canalSlopeNotes,
  crossingsOnProfile,
  DEFAULT_SLOPE_THRESHOLDS,
} from '../../src/components/map2d/canalProfile';

const climb = [
  { distance_m: 0, elevation_m: 100 },
  { distance_m: 100, elevation_m: 100.2 },
  { distance_m: 200, elevation_m: 100.2 },
];

describe('canalSlopeNotes', () => {
  it('warns when the digitized flow climbs', () => {
    const notes = canalSlopeNotes(climb, 'digitizado');
    expect(notes.some((note) => note.kind === 'adverse')).toBe(true);
    const adverse = notes.find((note) => note.kind === 'adverse');
    expect(adverse?.slope_pct).toBeCloseTo(0.2);
  });

  it('treats the reverse sense as downhill on the same climb', () => {
    const notes = canalSlopeNotes(climb, 'inverso');
    expect(notes.some((note) => note.kind === 'adverse')).toBe(false);
  });

  it('flags a flat reach as sediment risk', () => {
    const notes = canalSlopeNotes(
      [
        { distance_m: 0, elevation_m: 100 },
        { distance_m: 200, elevation_m: 100.02 },
      ],
      'digitizado',
      DEFAULT_SLOPE_THRESHOLDS
    );
    expect(notes).toEqual([expect.objectContaining({ kind: 'sediment', from_m: 0, to_m: 200 })]);
  });

  it('honours a stricter sediment threshold', () => {
    const notes = canalSlopeNotes(
      [
        { distance_m: 0, elevation_m: 100 },
        { distance_m: 100, elevation_m: 100.08 },
      ],
      'digitizado',
      { sedimentPct: 0.05, adversePct: 0.2 }
    );
    expect(notes).toEqual([]);
  });

  it('does not invent a slope across a gap', () => {
    const notes = canalSlopeNotes(
      [
        { distance_m: 0, elevation_m: 100 },
        { distance_m: 50, elevation_m: null },
        { distance_m: 100, elevation_m: 110 },
      ],
      'digitizado'
    );
    expect(notes).toEqual([]);
  });
});

describe('crossingsOnProfile', () => {
  const samples = [
    { distance_m: 0, lon: -62.7, lat: -32.6 },
    { distance_m: 400, lon: -62.71, lat: -32.6 },
  ];

  it('keeps a crossing that sits on the trace', () => {
    const hits = crossingsOnProfile(samples, [
      { lon: -62.71, lat: -32.6, label: 'Cruce de camino' },
    ]);
    expect(hits).toEqual([{ distance_m: 400, label: 'Cruce de camino' }]);
  });

  it('drops a crossing far from the trace', () => {
    const hits = crossingsOnProfile(samples, [{ lon: -62.8, lat: -32.7, label: 'Cruce de canal' }]);
    expect(hits).toEqual([]);
  });
});
