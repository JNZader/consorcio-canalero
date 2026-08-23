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
 * It also renders no portal: a portalled node escapes the container the popup
 * measures and scrolls, and a disclaimer that lands somewhere else on screen is
 * not "with the result".
 *
 * `tests/unit/RoadFlowDisclaimer.test.tsx` asserts all of this in the rendered
 * DOM, on purpose — the same statement living in a docstring or a help page
 * would satisfy a source-text check and satisfy no operator.
 */

import { Text } from '@mantine/core';

export const ROAD_FLOW_DISCLAIMER_TEST_ID = 'road-flow-disclaimer';

/**
 * The copy, verbatim from the spec. Exported so the ranked list and the popup
 * share ONE string: two hand-typed copies drift, and the day they did, two
 * operators would be reading two different promises about the same number.
 */
export const ROAD_FLOW_DISCLAIMER_TEXT =
  'Indica hacia dónde va el agua, no cuánta ni con qué fuerza. ' +
  'El orden es relativo entre los puntos mostrados, no una medición hidráulica.';

/** Where this instance is rendered. Both surfaces mount one (RFA-R4). */
export type RoadFlowDisclaimerSurface = 'lista' | 'popup';

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
