import { MantineProvider, Transition } from '@mantine/core';
import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

function TestTransition({ mounted }: Readonly<{ mounted: boolean }>) {
  return (
    <MantineProvider env="test">
      <Transition
        mounted={mounted}
        duration={250}
        exitDuration={250}
        enterDelay={175}
        exitDelay={225}
      >
        {(styles) => <div style={styles}>Transition content</div>}
      </Transition>
    </MantineProvider>
  );
}

describe('Mantine Transition test environment cleanup', () => {
  it('does not schedule delayed transition work when mounted changes', () => {
    vi.useFakeTimers({
      toFake: ['setTimeout', 'clearTimeout', 'requestAnimationFrame', 'cancelAnimationFrame'],
    });
    const requestAnimationFrameSpy = vi.spyOn(window, 'requestAnimationFrame');
    let unmount = () => {};

    try {
      const view = render(<TestTransition mounted={false} />);
      unmount = view.unmount;

      view.rerender(<TestTransition mounted />);

      expect(requestAnimationFrameSpy).not.toHaveBeenCalled();
      expect(vi.getTimerCount()).toBe(0);

      view.rerender(<TestTransition mounted={false} />);

      expect(requestAnimationFrameSpy).not.toHaveBeenCalled();
      expect(vi.getTimerCount()).toBe(0);
    } finally {
      unmount();
      requestAnimationFrameSpy.mockRestore();
      vi.clearAllTimers();
      vi.useRealTimers();
    }
  });
});
