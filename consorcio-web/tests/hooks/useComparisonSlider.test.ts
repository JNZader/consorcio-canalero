import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { useComparisonSlider } from '../../src/components/map2d/useComparisonSlider';

interface HarnessOptions {
  /** Simulate an element without the Pointer Capture API (older WebViews). */
  readonly withPointerCapture?: boolean;
}

function setup({ withPointerCapture = true }: HarnessOptions = {}) {
  const addEventListenerSpy = vi.spyOn(window, 'addEventListener');
  const removeEventListenerSpy = vi.spyOn(window, 'removeEventListener');
  const setSliderPosition = vi.fn();
  const sliderContainerRef = {
    current: {
      getBoundingClientRect: () => ({ left: 10, width: 100 }) as DOMRect,
    },
  };
  const isDraggingSlider = { current: false };

  const setPointerCapture = vi.fn();
  const releasePointerCapture = vi.fn();
  const currentTarget = withPointerCapture ? { setPointerCapture, releasePointerCapture } : {};

  const { result } = renderHook(() =>
    useComparisonSlider({
      sliderContainerRef: sliderContainerRef as never,
      isDraggingSlider: isDraggingSlider as never,
      setSliderPosition,
    })
  );

  function pointerDown(pointerId: number) {
    const preventDefault = vi.fn();
    act(() => {
      result.current({
        preventDefault,
        pointerId,
        currentTarget,
      } as unknown as React.PointerEvent);
    });
    return preventDefault;
  }

  function handlerFor(type: string) {
    return addEventListenerSpy.mock.calls.find(([event]) => event === type)?.[1] as EventListener;
  }

  return {
    addEventListenerSpy,
    removeEventListenerSpy,
    setSliderPosition,
    isDraggingSlider,
    setPointerCapture,
    releasePointerCapture,
    pointerDown,
    handlerFor,
  };
}

describe('useComparisonSlider', () => {
  it('registers POINTER listeners (mouse + touch + pen) and captures the pointer', () => {
    const harness = setup();
    const preventDefault = harness.pointerDown(7);

    expect(preventDefault).toHaveBeenCalledTimes(1);
    expect(harness.setPointerCapture).toHaveBeenCalledWith(7);
    expect(harness.addEventListenerSpy).toHaveBeenCalledWith('pointermove', expect.any(Function));
    expect(harness.addEventListenerSpy).toHaveBeenCalledWith('pointerup', expect.any(Function));
    expect(harness.addEventListenerSpy).toHaveBeenCalledWith('pointercancel', expect.any(Function));
    // Regression guard: the old mouse-only wiring is gone (dead on touch).
    expect(harness.addEventListenerSpy).not.toHaveBeenCalledWith('mousemove', expect.any(Function));
    expect(harness.addEventListenerSpy).not.toHaveBeenCalledWith('mouseup', expect.any(Function));

    harness.addEventListenerSpy.mockRestore();
    harness.removeEventListenerSpy.mockRestore();
  });

  it('updates the position while dragging and cleans up on pointerup', () => {
    const harness = setup();
    harness.pointerDown(1);

    const moveHandler = harness.handlerFor('pointermove');
    const upHandler = harness.handlerFor('pointerup');

    act(() => {
      moveHandler({ clientX: 60, pointerId: 1 } as PointerEvent);
    });
    expect(harness.setSliderPosition).toHaveBeenCalledWith(50);

    act(() => {
      upHandler({ pointerId: 1 } as PointerEvent);
    });
    expect(harness.isDraggingSlider.current).toBe(false);
    expect(harness.releasePointerCapture).toHaveBeenCalledWith(1);
    expect(harness.removeEventListenerSpy).toHaveBeenCalledWith('pointermove', moveHandler);
    expect(harness.removeEventListenerSpy).toHaveBeenCalledWith('pointerup', upHandler);
    expect(harness.removeEventListenerSpy).toHaveBeenCalledWith('pointercancel', upHandler);

    harness.addEventListenerSpy.mockRestore();
    harness.removeEventListenerSpy.mockRestore();
  });

  it('drives the same path for a TOUCH pointer and clamps to [0, 100]', () => {
    const harness = setup();
    // A touch pointer id — identical code path, which is the whole point of
    // migrating off mouse events.
    harness.pointerDown(42);
    const moveHandler = harness.handlerFor('pointermove');

    act(() => {
      moveHandler({ clientX: 35, pointerId: 42, pointerType: 'touch' } as PointerEvent);
    });
    expect(harness.setSliderPosition).toHaveBeenLastCalledWith(25);

    // Finger dragged past both edges of the container.
    act(() => {
      moveHandler({ clientX: -500, pointerId: 42, pointerType: 'touch' } as PointerEvent);
    });
    expect(harness.setSliderPosition).toHaveBeenLastCalledWith(0);

    act(() => {
      moveHandler({ clientX: 5000, pointerId: 42, pointerType: 'touch' } as PointerEvent);
    });
    expect(harness.setSliderPosition).toHaveBeenLastCalledWith(100);

    harness.addEventListenerSpy.mockRestore();
    harness.removeEventListenerSpy.mockRestore();
  });

  it('pointercancel ends the drag (the browser can steal the gesture)', () => {
    const harness = setup();
    harness.pointerDown(3);
    const cancelHandler = harness.handlerFor('pointercancel');

    act(() => {
      cancelHandler({ pointerId: 3 } as PointerEvent);
    });
    expect(harness.isDraggingSlider.current).toBe(false);

    harness.addEventListenerSpy.mockRestore();
    harness.removeEventListenerSpy.mockRestore();
  });

  it('still drags when the element has no Pointer Capture API', () => {
    const harness = setup({ withPointerCapture: false });
    expect(() => harness.pointerDown(9)).not.toThrow();

    const moveHandler = harness.handlerFor('pointermove');
    act(() => {
      moveHandler({ clientX: 60, pointerId: 9 } as PointerEvent);
    });
    expect(harness.setSliderPosition).toHaveBeenCalledWith(50);

    harness.addEventListenerSpy.mockRestore();
    harness.removeEventListenerSpy.mockRestore();
  });

  // Multi-touch hardening (fix R4-002). `setPointerCapture` only redirects the
  // captured pointer; every other pointer keeps dispatching to the window, so a
  // second finger used to be able to drive — or terminate — someone else's drag.
  describe('pointerId isolation', () => {
    it('ignores pointermove from a DIFFERENT pointer (a second finger cannot hijack)', () => {
      const harness = setup();
      harness.pointerDown(1);
      const moveHandler = harness.handlerFor('pointermove');

      act(() => {
        moveHandler({ clientX: 60, pointerId: 2, pointerType: 'touch' } as PointerEvent);
      });
      expect(harness.setSliderPosition).not.toHaveBeenCalled();

      // The originating pointer still drives it.
      act(() => {
        moveHandler({ clientX: 60, pointerId: 1, pointerType: 'touch' } as PointerEvent);
      });
      expect(harness.setSliderPosition).toHaveBeenCalledWith(50);

      harness.addEventListenerSpy.mockRestore();
      harness.removeEventListenerSpy.mockRestore();
    });

    it('ignores pointerup from a DIFFERENT pointer (a second finger cannot end the drag)', () => {
      const harness = setup();
      harness.pointerDown(1);
      const moveHandler = harness.handlerFor('pointermove');
      const upHandler = harness.handlerFor('pointerup');

      act(() => {
        upHandler({ pointerId: 2 } as PointerEvent);
      });
      expect(harness.isDraggingSlider.current).toBe(true);
      expect(harness.releasePointerCapture).not.toHaveBeenCalled();
      expect(harness.removeEventListenerSpy).not.toHaveBeenCalledWith('pointermove', moveHandler);

      // The originating pointer still ends it and tears the listeners down.
      act(() => {
        upHandler({ pointerId: 1 } as PointerEvent);
      });
      expect(harness.isDraggingSlider.current).toBe(false);
      expect(harness.releasePointerCapture).toHaveBeenCalledWith(1);
      expect(harness.removeEventListenerSpy).toHaveBeenCalledWith('pointermove', moveHandler);

      harness.addEventListenerSpy.mockRestore();
      harness.removeEventListenerSpy.mockRestore();
    });

    it('ignores pointercancel from a DIFFERENT pointer', () => {
      const harness = setup();
      harness.pointerDown(3);
      const cancelHandler = harness.handlerFor('pointercancel');

      act(() => {
        cancelHandler({ pointerId: 8 } as PointerEvent);
      });
      expect(harness.isDraggingSlider.current).toBe(true);

      act(() => {
        cancelHandler({ pointerId: 3 } as PointerEvent);
      });
      expect(harness.isDraggingSlider.current).toBe(false);

      harness.addEventListenerSpy.mockRestore();
      harness.removeEventListenerSpy.mockRestore();
    });
  });
});
