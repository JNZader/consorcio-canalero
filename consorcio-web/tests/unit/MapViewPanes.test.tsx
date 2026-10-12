import { fireEvent, render, screen } from '@testing-library/react';
import { useEffect, useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import {
  MapViewPanes,
  notifyMapPaneShown,
  shouldArmThreeD,
} from '../../src/components/map2d/MapViewPanes';

function Harness({ start = '2d' as '2d' | '3d' }) {
  const [mode, setMode] = useState<'2d' | '3d'>(start);
  const [armed, setArmed] = useState(false);
  useEffect(() => {
    setArmed((prev) => shouldArmThreeD(prev, mode));
  }, [mode]);
  return (
    <>
      <button type="button" onClick={() => setMode('3d')}>
        3D
      </button>
      <button type="button" onClick={() => setMode('2d')}>
        2D
      </button>
      <MapViewPanes
        mode={mode}
        threeDArmed={armed}
        twoD={<div>canvas-2d</div>}
        threeD={<div>canvas-3d</div>}
      />
    </>
  );
}

describe('MapViewPanes UX-17', () => {
  it('starts with 2D only', () => {
    render(<Harness />);
    expect(screen.getByTestId('map-2d-keep-alive')).toBeInTheDocument();
    expect(screen.queryByTestId('map-3d-keep-alive')).toBeNull();
    expect(screen.getByText('canvas-2d')).toBeInTheDocument();
  });

  it('keeps 2D mounted after opening 3D', () => {
    render(<Harness />);
    fireEvent.click(screen.getByText('3D'));
    expect(screen.getByTestId('map-2d-keep-alive')).toBeInTheDocument();
    expect(screen.getByTestId('map-3d-keep-alive')).toBeInTheDocument();
    expect(screen.getByTestId('map-2d-keep-alive')).toHaveAttribute('hidden');
    expect(screen.getByTestId('map-3d-keep-alive')).not.toHaveAttribute('hidden');
  });

  it('does not remount 2D when returning from 3D', () => {
    render(<Harness />);
    fireEvent.click(screen.getByText('3D'));
    fireEvent.click(screen.getByText('2D'));
    expect(screen.getByText('canvas-2d')).toBeInTheDocument();
    expect(screen.getByTestId('map-3d-keep-alive')).toBeInTheDocument();
    expect(screen.getByTestId('map-3d-keep-alive')).toHaveAttribute('hidden');
  });

  it('shouldArmThreeD latches', () => {
    expect(shouldArmThreeD(false, '2d')).toBe(false);
    expect(shouldArmThreeD(false, '3d')).toBe(true);
    expect(shouldArmThreeD(true, '2d')).toBe(true);
  });

  it('notifyMapPaneShown dispatches resize', () => {
    const spy = vi.spyOn(window, 'dispatchEvent');
    notifyMapPaneShown();
    expect(spy).toHaveBeenCalledWith(expect.objectContaining({ type: 'resize' }));
    spy.mockRestore();
  });
});
