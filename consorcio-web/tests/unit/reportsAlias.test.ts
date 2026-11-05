import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

describe('alias /reports y redirects legacy', () => {
  const routeTree = readFileSync(join(import.meta.dirname, '../../src/routeTree.gen.tsx'), 'utf8');

  it('redirige /reports a Participación sin tocar los aliases viejos', () => {
    expect(routeTree).toMatch(/path: '\/reports'/);
    expect(routeTree).toMatch(/path: '\/reportes'/);
    expect(routeTree).toMatch(/path: '\/sugerencias'/);
    const reports = routeTree.slice(routeTree.indexOf("path: '/reports'"));
    expect(reports.slice(0, 280)).toMatch(/redirect\(\{\s*to: '\/participacion'\s*\}\)/);
    expect(routeTree).toMatch(/to: '\/admin\/participacion'/);
    expect(routeTree).toMatch(
      /to: '\/admin\/participacion',\s*search: \{\s*tab: 'sugerencias'\s*\}/
    );
  });
});
