#!/bin/bash

echo "=== COMPLETE BASELINE SCORES (All 9 Hooks) ==="
echo ""
echo "| Hook | Killed | Total | Rate | Status | Gap |"
echo "|------|--------|-------|------|--------|-----|"

declare -a hooks=("useInfrastructure" "useJobStatus" "useMapReady" "useCaminosColoreados" "useGEELayers" "useAuth" "useSelectedImage" "useImageComparison" "useContactVerification")
declare -a rates
declare -i pass_count=0
declare -i fail_count=0

for hook in "${hooks[@]}"; do
  report="reports/phase-2-mutation/$hook/index.html"
  
  if [ ! -f "$report" ]; then
    echo "| $hook | ERROR | - | - | ❌ NOT FOUND | - |"
    continue
  fi
  
  # Extract killed and total from HTML
  killed=$(grep -oP '(\d+)(?=\s+killed out of)' "$report" | head -1)
  total=$(grep -oP '(?<=killed out of\s+)\d+' "$report" | head -1)
  
  if [ -z "$killed" ] || [ -z "$total" ]; then
    # Try alternative pattern
    killed=$(grep -oP '\d+(?=\s+killed)' "$report" | head -1)
    total=$(grep -oP '(?<= out of )\d+' "$report" | head -1)
  fi
  
  if [ -n "$killed" ] && [ -n "$total" ]; then
    rate=$(echo "scale=1; ($killed * 100) / $total" | bc)
    
    if (( $(echo "$rate >= 70" | bc -l) )); then
      status="✅ PASS"
      gap="N/A"
      ((pass_count++))
    else
      status="❌ FAIL"
      gap=$(echo "scale=1; 70 - $rate" | bc)%
      ((fail_count++))
    fi
    
    rates+=("$rate:$hook")
    echo "| $(printf '%-23s' "$hook") | $killed | $total | **${rate}%** | $status | $gap |"
  else
    echo "| $(printf '%-23s' "$hook") | PARSE_ERROR | - | - | ❌ ERROR | - |"
  fi
done

echo ""
echo "**Summary**: $pass_count pass, $fail_count fail"
echo ""
echo "**Hooks below 70% (sorted by score, lowest first):**"

# Sort by rate
IFS=$'\n' sorted=($(sort -t: -k1 -n <<<"${rates[*]}"))
unset IFS

for item in "${sorted[@]}"; do
  rate=$(echo "$item" | cut -d: -f1)
  hook=$(echo "$item" | cut -d: -f2)
  if (( $(echo "$rate < 70" | bc -l) )); then
    gap=$(echo "scale=1; 70 - $rate" | bc)
    echo "- **$hook**: ${rate}% (gap: ${gap}%)"
  fi
done
