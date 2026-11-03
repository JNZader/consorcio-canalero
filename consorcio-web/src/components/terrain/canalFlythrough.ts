export interface FlyFrame {
  readonly lon: number;
  readonly lat: number;
  readonly bearing: number;
  readonly distance_m: number;
}

function rumbo(from: readonly number[], to: readonly number[]): number {
  const lat1 = ((from[1] ?? 0) * Math.PI) / 180;
  const lat2 = ((to[1] ?? 0) * Math.PI) / 180;
  const dLon = (((to[0] ?? 0) - (from[0] ?? 0)) * Math.PI) / 180;
  const y = Math.sin(dLon) * Math.cos(lat2);
  const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLon);
  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
}

/** Camera steps along a canal. Distance is metres from the start, for the profile cursor. */
export function flythroughFrames(
  coordinates: readonly (readonly number[])[],
  stepM = 120
): FlyFrame[] {
  const points = coordinates.filter((pair) => pair.length >= 2);
  if (points.length < 2) return [];
  const frames: FlyFrame[] = [];
  let travelled = 0;
  let since = 0;
  for (let index = 1; index < points.length; index += 1) {
    const prev = points[index - 1]!;
    const next = points[index]!;
    const dx = ((next[0] ?? 0) - (prev[0] ?? 0)) * 111_320 * Math.cos((((next[1] ?? 0) * Math.PI) / 180));
    const dy = ((next[1] ?? 0) - (prev[1] ?? 0)) * 110_540;
    const length = Math.hypot(dx, dy);
    travelled += length;
    since += length;
    if (index === 1 || since >= stepM || index === points.length - 1) {
      frames.push({
        lon: next[0] ?? 0,
        lat: next[1] ?? 0,
        bearing: rumbo(prev, next),
        distance_m: travelled,
      });
      since = 0;
    }
  }
  return frames;
}

export async function playFlythrough(
  map: { easeTo: (options: { center: [number, number]; bearing: number; pitch: number; duration: number }) => void },
  frames: readonly FlyFrame[],
  onFrame: (frame: FlyFrame) => void
): Promise<void> {
  for (const frame of frames) {
    onFrame(frame);
    map.easeTo({
      center: [frame.lon, frame.lat],
      bearing: frame.bearing,
      pitch: 55,
      duration: 450,
    });
    await new Promise((resolve) => {
      window.setTimeout(resolve, 480);
    });
  }
}
