#!/bin/bash

HOOK=${1:-all}

if [ "$HOOK" = "all" ]; then
  echo "▶️  Running Stryker for ALL hooks..."
  npx stryker run stryker-phase-2.config.json
else
  echo "▶️  Running Stryker for hook: $HOOK"
  
  # Create temporary config for specific hook (no extends - merge directly)
  cat > stryker-$HOOK.config.json << CONFIG
{
  "\$schema": "https://raw.githubusercontent.com/stryker-mutator/stryker-js/master/packages/core/schema/stryker-schema.json",
  "testRunner": "command",
  "commandRunner": {
    "command": "npm run test:run -- tests/hooks/$HOOK.test.ts"
  },
  "coverageAnalysis": "off",
  "mutate": [
    "src/hooks/$HOOK.ts"
  ],
  "reporters": ["html", "json", "clear-text"],
  "htmlReporter": {
    "fileName": "reports/phase-2-mutation/$HOOK/index.html"
  },
  "timeoutMS": 30000,
  "thresholds": {
    "high": 85,
    "low": 70,
    "break": 70
  },
  "concurrency": 2,
  "allowEmpty": false,
  "cleanTempDir": true
}
CONFIG
  
  npx stryker run stryker-$HOOK.config.json
  rm stryker-$HOOK.config.json
fi

