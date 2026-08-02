import { useCallback } from 'react';

interface UseComparisonSliderParams {
  sliderContainerRef: React.RefObject<HTMLDivElement | null>;
  isDraggingSlider: React.RefObject<boolean>;
  setSliderPosition: (value: number) => void;
}

/**
 * Drag handler for the before/after comparison divider.
 *
 * POINTER events, not mouse events (map-fluidity T2, fix 3). The previous
 * implementation wired `mousedown` + `mousemove`/`mouseup`, which a touch
 * browser never synthesises while dragging — the divider was completely dead on
 * a phone or tablet. Pointer events cover mouse, touch and pen with ONE code
 * path, and `setPointerCapture` keeps the gesture bound to the divider even when
 * the finger leaves it (no lost `pointerup`, no stuck drag).
 *
 * `pointercancel` is handled alongside `pointerup`: the browser fires it when it
 * steals the gesture (e.g. a scroll takes over), and without it `isDragging`
 * would stay true forever.
 *
 * The window listeners filter on the ORIGINATING `pointerId` (fix R4-002).
 * `setPointerCapture` only redirects events for the captured pointer; every
 * other pointer keeps dispatching normally, so on a multi-touch screen a second
 * finger anywhere on the page used to drive the divider (`pointermove`) or end
 * the drag outright (`pointerup`). Ignoring foreign ids makes the gesture belong
 * to exactly one pointer from `pointerdown` to `pointerup`.
 */
export function useComparisonSlider({
  sliderContainerRef,
  isDraggingSlider,
  setSliderPosition,
}: UseComparisonSliderParams) {
  return useCallback(
    (event: React.PointerEvent) => {
      event.preventDefault();
      isDraggingSlider.current = true;

      const target = event.currentTarget as Element | null;
      const pointerId = event.pointerId;
      // Guarded: happy-dom/jsdom elements may not implement pointer capture, and
      // a capture failure must never abort the drag.
      try {
        target?.setPointerCapture?.(pointerId);
      } catch {
        // no-op — capture is an optimisation, the window listeners still work.
      }

      const onPointerMove = (moveEvent: PointerEvent) => {
        if (moveEvent.pointerId !== pointerId) return;
        if (!isDraggingSlider.current || !sliderContainerRef.current) return;
        const rect = sliderContainerRef.current.getBoundingClientRect();
        const pct = Math.max(
          0,
          Math.min(100, ((moveEvent.clientX - rect.left) / rect.width) * 100)
        );
        setSliderPosition(pct);
      };

      const onPointerUp = (upEvent: PointerEvent) => {
        if (upEvent.pointerId !== pointerId) return;
        isDraggingSlider.current = false;
        try {
          target?.releasePointerCapture?.(pointerId);
        } catch {
          // no-op — the capture may already be released by the browser.
        }
        window.removeEventListener('pointermove', onPointerMove);
        window.removeEventListener('pointerup', onPointerUp);
        window.removeEventListener('pointercancel', onPointerUp);
      };

      window.addEventListener('pointermove', onPointerMove);
      window.addEventListener('pointerup', onPointerUp);
      window.addEventListener('pointercancel', onPointerUp);
    },
    [isDraggingSlider, setSliderPosition, sliderContainerRef]
  );
}
