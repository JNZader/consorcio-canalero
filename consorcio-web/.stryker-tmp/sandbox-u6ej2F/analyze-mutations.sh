#!/bin/bash

# Extract mutation analysis from Stryker report
HOOK=$1
REPORT="reports/phase-2-mutation/${HOOK}/index.html"

if [ ! -f "$REPORT" ]; then
  echo "Report not found: $REPORT"
  exit 1
fi

# Extract survived and killed counts
echo "=== Mutation Analysis for $HOOK ==="
echo ""
grep -o "survived\|killed" "$REPORT" | sort | uniq -c | sort -rn
echo ""
echo "=== Top Survived Mutations (first 20 lines mentioning 'survived') ==="
grep -B5 "survived" "$REPORT" | head -50

