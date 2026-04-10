import { createContext, type ReactNode, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { visuallyHiddenStyle } from './shared';

interface LiveRegionContextType {
  announce: (message: string, priority?: 'polite' | 'assertive') => void;
}

const LiveRegionContext = createContext<LiveRegionContextType | null>(null);

export function LiveRegionProvider({ children }: Readonly<{ children: ReactNode }>) {
  const [politeMessage, setPoliteMessage] = useState('');
  const [assertiveMessage, setAssertiveMessage] = useState('');
  const politeTimeoutsRef = useRef<ReturnType<typeof setTimeout>[]>([]);
  const assertiveTimeoutsRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    return () => {
      politeTimeoutsRef.current.forEach(clearTimeout);
      assertiveTimeoutsRef.current.forEach(clearTimeout);
    };
  }, []);

  const announce = useCallback((message: string, priority: 'polite' | 'assertive' = 'polite') => {
    if (priority === 'assertive') {
      setAssertiveMessage('');
      const timeout1 = setTimeout(() => setAssertiveMessage(message), 50);
      const timeout2 = setTimeout(() => setAssertiveMessage(''), 1000);
      assertiveTimeoutsRef.current.push(timeout1, timeout2);
      return;
    }

    setPoliteMessage('');
    const timeout1 = setTimeout(() => setPoliteMessage(message), 50);
    const timeout2 = setTimeout(() => setPoliteMessage(''), 1000);
    politeTimeoutsRef.current.push(timeout1, timeout2);
  }, []);

  return (
    <LiveRegionContext.Provider value={{ announce }}>
      {children}
      <div aria-live="polite" aria-atomic="true" className="sr-only" style={visuallyHiddenStyle}>
        {politeMessage}
      </div>
      <div role="alert" aria-live="assertive" aria-atomic="true" className="sr-only" style={visuallyHiddenStyle}>
        {assertiveMessage}
      </div>
    </LiveRegionContext.Provider>
  );
}

export function useLiveRegion() {
  const context = useContext(LiveRegionContext);
  if (!context) {
    return { announce: (_message: string, _priority?: 'polite' | 'assertive') => {} };
  }
  return context;
}
