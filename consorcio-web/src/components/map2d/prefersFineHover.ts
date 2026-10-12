/** MOB-02: coarse / no-hover devices skip map hover tooltips. Re-check on change. */

export function prefersFineHover(
  media: Pick<Window, 'matchMedia'> | null | undefined = typeof window === 'undefined' ? null : window
): boolean {
  if (!media) return false;
  if (typeof media.matchMedia !== 'function') return true;
  try {
    return media.matchMedia('(hover: hover)').matches && media.matchMedia('(pointer: fine)').matches;
  } catch {
    return true;
  }
}

export function subscribePrefersFineHover(
  onChange: (ok: boolean) => void,
  media: Pick<Window, 'matchMedia'> | null | undefined = typeof window === 'undefined' ? null : window
): () => void {
  if (!media?.matchMedia) return () => undefined;
  let hover: MediaQueryList;
  let pointer: MediaQueryList;
  try {
    hover = media.matchMedia('(hover: hover)');
    pointer = media.matchMedia('(pointer: fine)');
  } catch {
    return () => undefined;
  }
  const emit = () => onChange(hover.matches && pointer.matches);
  hover.addEventListener('change', emit);
  pointer.addEventListener('change', emit);
  return () => {
    hover.removeEventListener('change', emit);
    pointer.removeEventListener('change', emit);
  };
}
