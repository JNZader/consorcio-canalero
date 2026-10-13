# audit-v6-wave-j

Wave J: MAP-11 remount. Stacked on `feat/audit-v6-wave-i` (#490).

## In

- [x] Keep one `controls` tree across desktop sidebar ↔ mobile overlay.
- [x] Crossing 48em must not remount LayerControlsPanel (search/accordion/local state).
- [x] Mobile still 75% overlay, burger, Back dismiss, closed overlay on desktop round-trip.

## Out

A11Y-10, UI-04/05/06/11, DB-04, CI-05, CODE-02, Mantine Drawer dependency for this shell.
