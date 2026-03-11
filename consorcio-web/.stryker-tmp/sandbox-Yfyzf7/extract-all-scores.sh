#!/bin/bash

echo "📊 Re-running Stryker for remaining 4 hooks and extracting scores..."
echo ""

declare -A scores

hooks=("useAuth" "useSelectedImage" "useImageComparison" "useContactVerification")

for hook in "${hooks[@]}"; do
  echo "⏳ Running Stryker for $hook..."
  
  # Run Stryker silently, capture output
  ./run-stryker-for-hook.sh $hook > /tmp/stryker-$hook.log 2>&1
  
  # Extract summary from the clear-text output in the log
  killed=$(grep -oP 'Killed:\s+\K\d+' /tmp/stryker-$hook.log | head -1)
  survived=$(grep -oP 'Survived:\s+\K\d+' /tmp/stryker-$hook.log | head -1)
  
  if [ -n "$killed" ] && [ -n "$survived" ]; then
    total=$((killed + survived))
    rate=$(echo "scale=2; $killed * 100 / $total" | bc)
    scores[$hook]="$killed/$total ($rate%)"
    echo "✅ $hook: $killed/$total = $rate%"
  else
    # Try alternative extraction from mutation.json
    if [ -f "reports/mutation/mutation.json" ]; then
      killed=$(grep -o '"killed":[0-9]*' reports/mutation/mutation.json | head -1 | grep -o '[0-9]*')
      survived=$(grep -o '"survived":[0-9]*' reports/mutation/mutation.json | head -1 | grep -o '[0-9]*')
      
      if [ -n "$killed" ] && [ -n "$survived" ]; then
        total=$((killed + survived))
        rate=$(echo "scale=2; $killed * 100 / $total" | bc)
        scores[$hook]="$killed/$total ($rate%)"
        echo "✅ $hook: $killed/$total = $rate%"
      else
        echo "⏳ $hook: Could not extract from logs or JSON"
        scores[$hook]="EXTRACT_MANUALLY"
      fi
    fi
  fi
  echo ""
done

echo "========================================="
echo "SUMMARY"
echo "========================================="
for hook in "${hooks[@]}"; do
  echo "$hook: ${scores[$hook]}"
done
