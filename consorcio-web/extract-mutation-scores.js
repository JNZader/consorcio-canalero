const fs = require('fs');
const path = require('path');

const hooks = [
  'useAuth',
  'useSelectedImage',
  'useImageComparison',
  'useContactVerification'
];

const resultsDir = 'reports/phase-2-mutation';

hooks.forEach(hook => {
  const htmlPath = path.join(resultsDir, hook, 'index.html');
  
  if (!fs.existsSync(htmlPath)) {
    console.log(`❌ ${hook}: File not found at ${htmlPath}`);
    return;
  }

  const html = fs.readFileSync(htmlPath, 'utf8');
  
  // Try multiple regex patterns to find mutation counts
  const patterns = [
    /killed["\']?\s*:\s*(\d+).*?total["\']?\s*:\s*(\d+)/is,
    /(\d+)\s+killed.*?(\d+)\s+total/is,
    /Killed:\s*(\d+).*?Total:\s*(\d+)/is,
    /(\d+)\s+\/\s+(\d+)/,
    /killed["\']?\s*:\s*(\d+).*?survived["\']?\s*:\s*(\d+)/is
  ];

  let killed = null;
  let total = null;

  for (const pattern of patterns) {
    const match = html.match(pattern);
    if (match && match[1] && match[2]) {
      killed = parseInt(match[1]);
      total = parseInt(match[2]);
      break;
    }
  }

  if (killed !== null && total !== null) {
    const rate = ((killed / total) * 100).toFixed(2);
    const status = rate >= 70 ? '✅' : '❌';
    console.log(`${status} ${hook}: ${killed}/${total} = ${rate}%`);
  } else {
    // Try to find any numbers in the HTML that might be counts
    const numbers = html.match(/\d+/g);
    if (numbers) {
      console.log(`⏳ ${hook}: Could not parse automatically. Sample numbers found: ${numbers.slice(0, 10).join(', ')}`);
    } else {
      console.log(`❌ ${hook}: No meaningful data found in HTML`);
    }
  }
});
