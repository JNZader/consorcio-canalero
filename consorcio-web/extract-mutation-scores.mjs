import fs from 'fs';
import path from 'path';

const hooks = [
  'useAuth',
  'useSelectedImage',
  'useImageComparison',
  'useContactVerification'
];

const resultsDir = 'reports/phase-2-mutation';

console.log('\n📊 Attempting to extract mutation scores from HTML reports...\n');

hooks.forEach(hook => {
  const htmlPath = path.join(resultsDir, hook, 'index.html');
  
  if (!fs.existsSync(htmlPath)) {
    console.log(`❌ ${hook}: File not found`);
    return;
  }

  try {
    const html = fs.readFileSync(htmlPath, 'utf8');
    
    // Strategy: Look for summary statistics in the HTML
    // Stryker reports typically embed data like: {"killed":X,"survived":Y,...}
    
    // Try to find JSON-like data structures
    const jsonMatch = html.match(/\{"killed":\d+[^}]*\}/g);
    
    if (jsonMatch && jsonMatch.length > 0) {
      console.log(`✅ ${hook}: Found potential data (${jsonMatch.length} matches)`);
      console.log(`   Sample: ${jsonMatch[0].substring(0, 100)}`);
    } else {
      // Look for summary text patterns
      const summaryMatch = html.match(/(\d+)\s+killed.*?(\d+)\s+(survived|total)/is);
      if (summaryMatch) {
        const killed = parseInt(summaryMatch[1]);
        const total = parseInt(summaryMatch[2]);
        const rate = ((killed / total) * 100).toFixed(2);
        console.log(`✅ ${hook}: ${killed}/${total} = ${rate}%`);
      } else {
        console.log(`⏳ ${hook}: Could not parse automatically`);
      }
    }
  } catch (err) {
    console.log(`❌ ${hook}: Error reading file - ${err.message}`);
  }
});
