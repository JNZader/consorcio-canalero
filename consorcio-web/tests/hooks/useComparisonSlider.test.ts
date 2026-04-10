import { renderHook, act } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { useComparisonSlider } from '../../src/components/map2d/useComparisonSlider';

describe('useComparisonSlider', () => {
  it('updates slider position while dragging and cleans up listeners on mouseup', () => {
    const addEventListenerSpy = vi.spyOn(window, 'addEventListener');
    const removeEventListenerSpy = vi.spyOn(window, 'removeEventListener');
    const setSliderPosition = vi.fn();
    const sliderContainerRef = {
      current: {
        getBoundingClientRect: () => ({ left: 10, width: 100 } as DOMRect),
      },
    };
    const isDraggingSlider = { current: false };

    const { result } = renderHook(() =>
      useComparisonSlider({
        sliderContainerRef: sliderContainerRef as any,
        isDraggingSlider: isDraggingSlider as any,
        setSliderPosition,
      }),
    );

    const preventDefault = vi.fn();
    act(() => {
      result.current({ preventDefault } as unknown as React.MouseEvent);
    });

    expect(preventDefault).toHaveBeenCalledTimes(1);
    expect(addEventListenerSpy).toHaveBeenCalledWith('mousemove', expect.any(Function));
    expect(addEventListenerSpy).toHaveBeenCalledWith('mouseup', expect.any(Function));

    const moveHandler = addEventListenerSpy.mock.calls.find(([event]) => event === 'mousemove')?.[1] as EventListener;
    const upHandler = addEventListenerSpy.mock.calls.find(([event]) => event === 'mouseup')?.[1] as EventListener;

    act(() => {
      moveHandler({ clientX: 60 } as MouseEvent);
    });
    expect(setSliderPosition).toHaveBeenCalledWith(50);

    act(() => {
      upHandler(new MouseEvent('mouseup'));
    });
    expect(removeEventListenerSpy).toHaveBeenCalledWith('mousemove', moveHandler);
    expect(removeEventListenerSpy).toHaveBeenCalledWith('mouseup', upHandler);

    addEventListenerSpy.mockRestore();
    removeEventListenerSpy.mockRestore();
  });
});
