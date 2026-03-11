// @ts-nocheck
const fs = require('fs');
const path = require('path');

const hooks = [
  'useInfrastructure',
  'useJobStatus', 
  'useMapReady',
  'useCaminosColoreados',
  'useGEELayers',
  'useAuth',
  'useSelectedImage',
  'useImageComparison',
  'useContactVerification'
];

const results = [];

hooks.forEach(hook => {
  const reportPath = `reports/phase-2-mutation/${hook}/index.html`;
  if (!fs.existsSync(reportPath)) {
    console.log(`❌ ${hook} - report not found`);
    return;
  }

  const content = fs.readFileSync(reportPath, 'utf-8');
  
  // Look for "X killed out of Y mutations" or similar pattern
  const killMatch = content.match(/(\d+)\s+killed out of\s+(\d+)/i);
  const percentMatch = content.match(/>(\d+(?:\.\d+)?)\%<\/.*?kill/i);
  
  if (killMatch) {
    const killed = parseInt(killMatch[1]);
    const total = parseInt(killMatch[2]);
    const rate = ((killed / total) * 100).toFixed(1);
    
    results.push({
      hook,
      killed,
      total,
      rate: parseFloat(rate),
      status: parseFloat(rate) >= 70 ? '✅ PASS' : '❌ FAIL',
      gap: parseFloat(rate) >= 70 ? 'N/A' : (70 - parseFloat(rate)).toFixed(1) + '%'
    });
  } else {
    console.log(`⚠️ ${hook} - could not parse`);
  }
});

// Sort by rate (lowest first)
results.sort((a, b) => a.rate - b.rate);

console.log('\n=== COMPLETE BASELINE SCORES (All 9 Hooks) ===\n');
console.log('| Hook | Killed | Total | Rate | Status | Gap |');
console.log('|------|--------|-------|------|--------|-----|');

results.forEach(r => {
  console.log(`| ${r.hook.padEnd(23)} | ${r.killed.toString().padEnd(6)} | ${r.total.toString().padEnd(5)} | **${r.rate}%** | ${r.status} | ${r.gap} |`);
});

// Summary
const passCount = results.filter(r => r.rate >= 70).length;
const failCount = results.filter(r => r.rate < 70).length;

console.log(`\n**Summary**: ${passCount} pass, ${failCount} fail\n`);

// Hooks that need work
const needWork = results.filter(r => r.rate < 70);
console.log('**Hooks below 70% (need test strengthening):**');
needWork.forEach(r => {
  console.log(`- ${r.hook}: ${r.rate}% (gap: ${r.gap})`);
});

process.exit(0);
