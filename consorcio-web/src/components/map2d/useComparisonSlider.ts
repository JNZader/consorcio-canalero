import { useCallback } from 'react';

interface UseComparisonSliderParams {
  sliderContainerRef: React.RefObject<HTMLDivElement | null>;
  isDraggingSlider: React.RefObject<boolean>;
  setSliderPosition: (value: number) => void;
}

export function useComparisonSlider({
  sliderContainerRef,
  isDraggingSlider,
  setSliderPosition,
}: UseComparisonSliderParams) {
  return useCallback((event: React.MouseEvent) => {
    event.preventDefault();
    isDraggingSlider.current = true;

    const onMouseMove = (moveEvent: MouseEvent) => {
      if (!isDraggingSlider.current || !sliderContainerRef.current) return;
      const rect = sliderContainerRef.current.getBoundingClientRect();
      const pct = Math.max(0, Math.min(100, ((moveEvent.clientX - rect.left) / rect.width) * 100));
      setSliderPosition(pct);
    };

    const onMouseUp = () => {
      isDraggingSlider.current = false;
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  }, [isDraggingSlider, setSliderPosition, sliderContainerRef]);
}
