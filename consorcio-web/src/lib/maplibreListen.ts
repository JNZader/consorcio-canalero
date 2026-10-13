/**
 * MapLibre v6 types `Map.on` as `keyof MapEventType`. Draw plugin events and
 * some WebGL context events are custom strings and need a typed escape hatch.
 */
export function listenMapEvent(
  map: { on: (type: never, listener: never) => unknown },
  type: string,
  listener: (...args: never[]) => void,
): void {
  map.on(type as never, listener as never);
}

export function unlistenMapEvent(
  map: { off: (type: never, listener: never) => unknown },
  type: string,
  listener: (...args: never[]) => void,
): void {
  map.off(type as never, listener as never);
}
