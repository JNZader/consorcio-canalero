/**
 * RoadFlowDisclaimer — the non-hydraulic disclaimer (flujo-caminos, RFA-R4).
 *
 * ⚠️ THIS COMPONENT IS ALWAYS MOUNTED. ⚠️
 * It takes no `open`, no `collapsed`, no `showDisclaimer` prop, and it must
 * never be wrapped in a `CollapsibleSection` — that component's body UNMOUNTS
 * when closed, so a reader who never opened it would read a ranking with no
 * statement of what the ranking is not. RFA-R4 requires the sentence be
 * readable *without operating a disclosure control*, and a component that can
 * be switched off does not satisfy a requirement about what is always visible.
 *
 * It also renders no portal: a portalled node escapes the container that
 * measures and scrolls it, and a disclaimer that lands somewhere else on screen
 * is not "with the result".
 *
 * ⚠️ OWNER RATIFICATION (2026-08-23): "el disclaimer acompaña SIEMPRE". ⚠️
 * The circles stay painted on the map while the surface that explains them can
 * be pushed off screen — the survey sheet displaces the panel on a phone, and
 * the panel itself minimizes to a pill. So the sentence has THREE call sites,
 * not one:
 *
 *   · `lista` — above the ranked list inside `RoadFlowPanel`;
 *   · `hoja`  — a compact instance inside `TramoSurveySheet`, the field case:
 *               the sheet is what the operator is looking at while the ranked
 *               circles are still drawn behind it;
 *   · `chip`  — the floating minimum, rendered by `MapUiPanels` exactly while
 *               the layer is ON and neither other surface is on screen.
 *
 * Every one of them renders THIS component: the sentence exists once in the
 * codebase, so three surfaces cannot drift into three different promises about
 * the same number. `tests/unit/roadFlowWiring.test.tsx` asserts the three CALL
 * SITES (a test that mounts two instances itself proves only that the component
 * can be mounted twice), and `tests/unit/RoadFlowDisclaimer.test.tsx` asserts
 * the copy and the no-disclosure-control structure in the rendered DOM — on
 * purpose, because the same statement living in a docstring or a help page
 * would satisfy a source-text check and satisfy no operator.
 */

import { Box, Text } from '@mantine/core';

import styles from '../../styles/components/map.module.css';

export const ROAD_FLOW_DISCLAIMER_TEST_ID = 'road-flow-disclaimer';

/** Test id of the floating host the `chip` surface is rendered inside. */
export const ROAD_FLOW_DISCLAIMER_CHIP_TEST_ID = 'road-flow-disclaimer-chip-host';

/**
 * The copy, verbatim from the spec. Exported so every surface shares ONE
 * string: two hand-typed copies drift, and the day they did, two operators
 * would be reading two different promises about the same number.
 */
export const ROAD_FLOW_DISCLAIMER_TEXT =
  'Indica hacia dónde va el agua, no cuánta ni con qué fuerza. ' +
  'El orden es relativo entre los puntos mostrados, no una medición hidráulica.';

/**
 * Where this instance is rendered. The three surfaces are the three places the
 * ranking can be read from (owner ratification 2026-08-23) — see the header.
 */
export type RoadFlowDisclaimerSurface = 'lista' | 'hoja' | 'chip';

interface RoadFlowDisclaimerProps {
  readonly surface: RoadFlowDisclaimerSurface;
}

export function RoadFlowDisclaimer({ surface }: RoadFlowDisclaimerProps) {
  return (
    <Text
      size="xs"
      c="dimmed"
      data-testid={`${ROAD_FLOW_DISCLAIMER_TEST_ID}-${surface}`}
      role="note"
    >
      Indica <strong>hacia dónde</strong> va el agua, no cuánta ni con qué fuerza. El orden es
      relativo entre los puntos mostrados, no una medición hidráulica.
    </Text>
  );
}

/**
 * The floating minimum: the whole sentence in a small anchored card, rendered
 * while the layer paints circles that no other surface is currently explaining
 * (the panel minimized to a pill, or displaced by the survey sheet).
 *
 * It is deliberately NOT a notification, a toast or a portal — this repository
 * has no toast system for map state and inventing one for a sentence that must
 * never expire would be the wrong tool: a toast is dismissible and timed, and
 * both of those are disclosure controls in disguise. It is a plain positioned
 * box, the same shape as the panel pill it sits next to, with no close button
 * and nothing to open.
 */
export function RoadFlowDisclaimerChip() {
  return (
    <Box className={styles.roadFlowDisclaimerChip} data-testid={ROAD_FLOW_DISCLAIMER_CHIP_TEST_ID}>
      <RoadFlowDisclaimer surface="chip" />
    </Box>
  );
}
