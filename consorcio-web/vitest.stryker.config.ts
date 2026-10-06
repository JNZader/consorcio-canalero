import config from './vitest.config';

const test = config.test ?? {};

/**
 * Vitest 5 + Stryker 10 mis-attributes perTest coverage (wrong tests run,
 * ~13% on formatters). `vitest.related` + sandbox path finds ~7 tests.
 * Restrict the graph to tests that import the shard's mutate files, and
 * skip tests that cannot run inside Stryker's sandbox.
 */
const HOSTILE = [
  'tests/unit/patchesApplied.test.ts',
  'tests/unit/martinSourcesContract.test.ts',
  'tests/components/mantine-transition-cleanup.test.tsx',
];

const SHARD_TESTS: Record<string, string[]> = {
  a: [
    'tests/unit/formatters.test.ts',
    'tests/unit/lib/formatters.test.ts',
    'tests/unit/lib/utils/formatters.test.ts',
    'tests/unit/rainfallFormat.test.ts',
    'tests/unit/RainfallAnswerCard.test.tsx',
    'tests/hooks/useRainfallAnalysis.test.tsx',
    'tests/stores/configStore.test.ts',
    'tests/stores/configStoreMerge.test.ts',
    'tests/unit/authLib.test.ts',
    'tests/unit/lib/auth.test.ts',
    'tests/unit/authRecoveryFlows.test.ts',
    'tests/unit/bpaPracticas.test.ts',
    'tests/unit/CanalCard.test.tsx',
    'tests/unit/canalesFormat.test.ts',
  ],
  b: [
    'tests/unit/RainfallDetailPanel.test.tsx',
    'tests/unit/RainfallMetricList.test.tsx',
    'tests/unit/apiCore.test.ts',
    'tests/unit/apiCoreHelpers.test.ts',
    'tests/unit/validators.test.ts',
    'tests/unit/lib/validators.test.ts',
    'tests/unit/typeGuards.test.ts',
    'tests/unit/typeGuardsBoundaries.test.ts',
    'tests/unit/errorHandler.test.ts',
    'tests/unit/lib/errorHandler.test.ts',
    'tests/unit/errorHandler-gaps.test.ts',
    'tests/unit/fmt.test.ts',
    'tests/unit/pilarVerdeKpis.test.ts',
    'tests/unit/rainfallApi.test.ts',
  ],
  auth1: [
    'tests/stores/authStore.test.ts',
    'tests/stores/authStoreInitialize.test.ts',
    'tests/unit/authLib.test.ts',
    'tests/unit/lib/auth.test.ts',
    'tests/unit/authRecoveryFlows.test.ts',
  ],
  auth2: [
    'tests/stores/authStore.test.ts',
    'tests/stores/authStoreInitialize.test.ts',
    'tests/unit/authLib.test.ts',
    'tests/unit/lib/auth.test.ts',
    'tests/unit/authRecoveryFlows.test.ts',
  ],
};

const shard = process.env.STRYKER_SHARD ?? '';
const include = SHARD_TESTS[shard] ?? Object.values(SHARD_TESTS).flat();

export default {
  ...config,
  test: {
    ...test,
    include,
    exclude: [...(test.exclude ?? []), ...HOSTILE],
  },
};
