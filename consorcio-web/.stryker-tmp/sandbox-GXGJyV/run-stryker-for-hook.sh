#!/bin/bash

HOOK=${1:-all}

if [ "$HOOK" = "all" ]; then
  echo "▶️  Running Stryker for ALL hooks..."
  npx stryker run stryker-phase-2.config.json
else
  echo "▶️  Running Stryker for hook: $HOOK"
  
  # Create temporary config for specific hook
  cat > stryker-$HOOK.config.json << CONFIG
{
  "extends": "./stryker-phase-2.config.json",
  "files": [
    "src/hooks/$HOOK.ts",
    "tests/hooks/$HOOK.test.ts"
  ]
}
CONFIG
  
  npx stryker run stryker-$HOOK.config.json
  rm stryker-$HOOK.config.json
fi

