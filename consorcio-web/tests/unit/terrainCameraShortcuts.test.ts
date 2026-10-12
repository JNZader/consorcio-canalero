import { describe, expect, it } from 'vitest';

import { terrainCameraShortcutFromEvent } from '../../src/components/terrain/terrainCameraShortcuts';

function keyEvent(
  key: string,
  extras: Partial<KeyboardEvent> & { target?: EventTarget } = {}
): KeyboardEvent {
  return {
    key,
    ctrlKey: false,
    metaKey: false,
    altKey: false,
    target: document.body,
    ...extras,
  } as KeyboardEvent;
}

describe('terrainCameraShortcutFromEvent', () => {
  it('maps n/u/r without modifiers', () => {
    expect(terrainCameraShortcutFromEvent(keyEvent('n'))).toBe('n');
    expect(terrainCameraShortcutFromEvent(keyEvent('U'))).toBe('u');
    expect(terrainCameraShortcutFromEvent(keyEvent('r'))).toBe('r');
  });

  it('ignores Ctrl/Meta/Alt so Ctrl+R does not reset the camera', () => {
    expect(terrainCameraShortcutFromEvent(keyEvent('r', { ctrlKey: true }))).toBeNull();
    expect(terrainCameraShortcutFromEvent(keyEvent('r', { metaKey: true }))).toBeNull();
    expect(terrainCameraShortcutFromEvent(keyEvent('n', { altKey: true }))).toBeNull();
  });

  it('ignores typing in inputs', () => {
    const input = document.createElement('input');
    expect(terrainCameraShortcutFromEvent(keyEvent('n', { target: input }))).toBeNull();
  });
});
